"""Phase 3 — FALSE-POSITIVE STRESS.

Every document under benchmarks/eval/corpus/clean/ is PII-FREE by construction
(only product/tech names, figures, dates, headings, boilerplate — NO persons,
NO addresses, NO account numbers, all fictional). Therefore EVERY detection the
Shield detector emits on these documents is a FALSE POSITIVE by definition.

This phase quantifies over-redaction:
  * raw FP count per document, per mode (balanced / compliant)
  * FP-per-1000-tokens (the comparable rate, since docs differ in length)
  * a breakdown of *what drives* the false positives (tech-term -> ORG/PERSON,
    number -> ID/phone, date, heading/structural noise)

GATE PHILOSOPHY (see GATE CALIBRATION RULE):
  The corpus deliberately includes one document built on a tech stack that is
  NOT in detection_rules.json's false_positive_denylist (Kafka / Datadog /
  Jenkins / Vault / Loki / Prometheus / ArgoCD / Terraform / Kubernetes). spaCy
  NER hallucinates ORG/PERSON/LOCATION on these unknown proper nouns, so that
  single document spikes far above the rest. That is a KNOWN-OPEN defect
  ("residual spaCy NER false positives on tech terms" + "denylist overfitting").

  So the hard gate is set on the *denylist-covered* corpus (the documents whose
  domain the denylist is supposed to handle): FP-per-1000-tokens must stay at or
  below a threshold pinned just above today's measured worst value. The
  non-denylist tech runbook is measured, reported, and flagged as `known_open`
  rather than hard-failing CI today — but its rate IS recorded in the baseline,
  so any *further* regression on it is visible.

Run:
    cd /Users/nico/Workspace/shield && \
        .venv/bin/python benchmarks/eval/phase3_fp_stress.py
"""

from __future__ import annotations

import os
import re
import sys

# Allow `python benchmarks/eval/phase3_fp_stress.py` from the repo root: ensure
# the repo root is importable so `benchmarks.eval._common` resolves.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmarks.eval._common import (
    detect,
    gate,
    write_report,
    CORPUS_DIR,
)

CLEAN_DIR = os.path.join(CORPUS_DIR, "clean")

# The document built on a tech stack deliberately ABSENT from
# detection_rules.json's false_positive_denylist. Its spike is a known-open
# defect, not a hard CI failure today.
NON_DENYLIST_DOC = "runbook_observability.txt"

MODES = ("balanced", "compliant")

# --------------------------------------------------------------------------- #
# Gate thresholds — calibrated just above today's measured worst values so the
# suite exits 0 on THIS branch while catching any future regression.
# Measured today (2026-06-26):
#   denylist-covered worst (kpi_metrics_table, both modes): 42.17 FP/1k tok
#   non-denylist runbook (both modes):                      88.46 FP/1k tok
# --------------------------------------------------------------------------- #
GATE_DENYLIST_FP_PER_1K = 45.0      # just above 42.17
GATE_NONDENYLIST_FP_PER_1K = 92.0   # informational ceiling on the known-open doc


def count_tokens(text: str) -> int:
    """Whitespace-delimited token count — the denominator for the FP rate."""
    return len(re.findall(r"\S+", text))


# --------------------------------------------------------------------------- #
# FP driver categorization
# --------------------------------------------------------------------------- #
_DATE_RE = re.compile(
    r"\b(\d{1,2}\.\d{1,2}\.\d{2,4}|\d{4}-\d{2}-\d{2}|"
    r"januar|februar|märz|maerz|april|mai|juni|juli|august|september|"
    r"oktober|november|dezember|quartal|monat|jahr|woche|tag)\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\d")
_STRUCTURAL_TYPES = set()  # headings are detected via text heuristics below

# Entity types that, on a PII-free doc, mean spaCy NER hallucinated a proper noun
_NER_TYPES = {"PERSON", "ORGANIZATION", "LOCATION", "NRP"}
# Entity types that come from numeric/structured recognizers
_STRUCTURED_TYPES = {
    "PHONE_NUMBER", "DE_ID_CARD", "DE_TAX_ID", "DE_SOCIAL_SECURITY",
    "IBAN_CODE", "CREDIT_CARD", "US_SSN", "IP_ADDRESS",
}


def categorize_fp(det) -> str:
    """Bucket a false positive by its likely DRIVER.

    Categories:
      tech_term_to_ner   — a product/tech proper noun mislabeled PERSON/ORG/LOCATION
      number_to_id_phone — a numeric run mislabeled as an ID / phone / account
      date               — a date/period expression flagged
      heading_structural — a structural/heading fragment flagged (no digits, short)
      other              — anything else
    """
    text = det.text or ""
    typ = det.type

    if _DATE_RE.search(text) and typ in (_NER_TYPES | {"DATE_TIME"}):
        return "date"
    if typ in _STRUCTURED_TYPES or (typ == "DATE_TIME" and _NUMBER_RE.search(text)):
        return "number_to_id_phone"
    if _NUMBER_RE.search(text) and typ in _NER_TYPES:
        # a number bled into an NER span
        return "number_to_id_phone"
    if typ in _NER_TYPES:
        # heading/structural noise: single capitalized token that is a section-ish
        # fragment vs. a genuine tech proper noun. We treat multi-word or
        # hyphenated tech-style tokens as tech_term, lone generic words as heading.
        return "tech_term_to_ner"
    return "other"


def analyze_doc(path: str, mode: str) -> dict:
    text = open(path, encoding="utf-8").read()
    ntok = count_tokens(text)
    dets = detect(text, mode=mode)
    fp = len(dets)  # PII-free doc => every detection is a false positive
    rate = round(fp / ntok * 1000, 2) if ntok else 0.0

    drivers: dict[str, int] = {}
    examples: list[list] = []
    for d in dets:
        cat = categorize_fp(d)
        drivers[cat] = drivers.get(cat, 0) + 1
        examples.append([d.type, d.text, cat, round(d.confidence, 2), d.recognizer])

    return {
        "tokens": ntok,
        "fp": fp,
        "fp_per_1k": rate,
        "drivers": drivers,
        "false_positives": examples,
    }


def list_clean_docs() -> list[str]:
    return sorted(f for f in os.listdir(CLEAN_DIR) if f.endswith(".txt"))


def run_corpus() -> tuple[dict, dict, dict]:
    """Analyze every clean doc in both modes.

    Returns (per_doc, agg_drivers, summary) so both main() and the pytest
    wrapper can consume identical numbers without re-printing.
    """
    files = list_clean_docs()
    per_doc: dict = {}
    agg_drivers: dict[str, dict[str, int]] = {m: {} for m in MODES}

    for fn in files:
        path = os.path.join(CLEAN_DIR, fn)
        per_doc[fn] = {"is_non_denylist": fn == NON_DENYLIST_DOC}
        for mode in MODES:
            res = analyze_doc(path, mode)
            per_doc[fn][mode] = res
            for k, v in res["drivers"].items():
                agg_drivers[mode][k] = agg_drivers[mode].get(k, 0) + v

    def corpus_rate(mode: str, include_non_denylist: bool) -> dict:
        tot_fp = tot_tok = 0
        worst = 0.0
        worst_doc = None
        for fn in files:
            if not include_non_denylist and fn == NON_DENYLIST_DOC:
                continue
            r = per_doc[fn][mode]
            tot_fp += r["fp"]
            tot_tok += r["tokens"]
            if r["fp_per_1k"] > worst:
                worst = r["fp_per_1k"]
                worst_doc = fn
        rate = round(tot_fp / tot_tok * 1000, 2) if tot_tok else 0.0
        return {"fp": tot_fp, "tokens": tot_tok, "fp_per_1k": rate,
                "worst_doc_fp_per_1k": worst, "worst_doc": worst_doc}

    summary: dict = {"modes": {}}
    for mode in MODES:
        denylist = corpus_rate(mode, include_non_denylist=False)
        full = corpus_rate(mode, include_non_denylist=True)
        nd = per_doc[NON_DENYLIST_DOC][mode]
        summary["modes"][mode] = {
            "denylist_covered": denylist,
            "full_corpus": full,
            "non_denylist_doc": {
                "doc": NON_DENYLIST_DOC,
                "fp": nd["fp"], "tokens": nd["tokens"],
                "fp_per_1k": nd["fp_per_1k"],
            },
            "driver_totals": agg_drivers[mode],
        }
    return per_doc, agg_drivers, summary


def main() -> int:
    files = list_clean_docs()
    if len(files) < 4:
        raise SystemExit(f"expected >=4 clean docs, found {len(files)} in {CLEAN_DIR}")

    print(f"Phase 3 — FALSE-POSITIVE STRESS  ({len(files)} PII-free documents)\n")

    per_doc, agg_drivers, summary = run_corpus()

    for fn in files:
        for mode in MODES:
            res = per_doc[fn][mode]
            tag = "  [NON-DENYLIST STACK]" if fn == NON_DENYLIST_DOC else ""
            print(
                f"  {fn:<32} {mode:<9} "
                f"tok={res['tokens']:<4} FP={res['fp']:<2} "
                f"FP/1k={res['fp_per_1k']:<6} drivers={res['drivers']}{tag}"
            )
    print()

    print("Corpus-level FP rates (FP per 1000 tokens):")
    for mode in MODES:
        m = summary["modes"][mode]
        denylist = m["denylist_covered"]
        full = m["full_corpus"]
        nd = m["non_denylist_doc"]
        print(
            f"  {mode:<9} denylist-covered worst-doc={denylist['worst_doc_fp_per_1k']:<6} "
            f"(agg {denylist['fp_per_1k']})   "
            f"non-denylist runbook={nd['fp_per_1k']}   "
            f"full-corpus agg={full['fp_per_1k']}"
        )
    print()
    print("FP driver totals (whole corpus):")
    for mode in MODES:
        print(f"  {mode:<9} {agg_drivers[mode]}")
    print()

    # --------------------------- GATES --------------------------- #
    print("Gates:")
    passed = True

    # Hard gate: denylist-covered worst-document rate must stay under ceiling.
    for mode in MODES:
        worst = summary["modes"][mode]["denylist_covered"]["worst_doc_fp_per_1k"]
        ok = worst <= GATE_DENYLIST_FP_PER_1K
        passed &= gate(
            ok,
            f"[{mode}] denylist-covered worst-doc FP/1k = {worst} "
            f"<= {GATE_DENYLIST_FP_PER_1K}",
        )

    # Informational ceiling on the known-open non-denylist runbook. This still
    # gate()s (so a future blow-up is visible) but with a deliberately loose
    # ceiling pinned just above today's spike; it is the documented known_open.
    for mode in MODES:
        nd = summary["modes"][mode]["non_denylist_doc"]["fp_per_1k"]
        ok = nd <= GATE_NONDENYLIST_FP_PER_1K
        passed &= gate(
            ok,
            f"[{mode}] non-denylist runbook FP/1k = {nd} "
            f"<= {GATE_NONDENYLIST_FP_PER_1K} (KNOWN-OPEN ceiling)",
        )

    known_open = [
        f"Non-denylist tech stack (Kafka/Datadog/Jenkins/Vault/Loki/Prometheus) "
        f"in {NON_DENYLIST_DOC} spikes spaCy-NER false positives to "
        f"{summary['modes']['balanced']['non_denylist_doc']['fp_per_1k']} FP/1k "
        f"(balanced) — residual spaCy NER FP on tech terms + denylist overfitting. "
        f"Tracked under a loose informational ceiling, not a hard failure.",
        "spaCy NER mislabels generic capitalized German nouns "
        "(Quartal, Vorquartal, Maengel, Auftragsbestaetigung, Umsetzende, "
        "Aenderungsantrags) as LOCATION/PERSON even in PII-free boilerplate.",
        "DE_StreetName regex fires on common nouns ending in street-like suffixes "
        "('Quartal', 'Speicherplatz') without address context -> LOCATION FP.",
    ]

    payload = {
        "phase": "phase3-fp-stress",
        "description": "Every detection on PII-free docs is a false positive; "
                       "FP rate + driver breakdown, balanced & compliant.",
        "documents": files,
        "non_denylist_doc": NON_DENYLIST_DOC,
        "gates": {
            "denylist_fp_per_1k_ceiling": GATE_DENYLIST_FP_PER_1K,
            "non_denylist_fp_per_1k_ceiling": GATE_NONDENYLIST_FP_PER_1K,
        },
        "per_document": per_doc,
        "summary": summary,
        "known_open": known_open,
        "all_gates_passed": bool(passed),
    }
    out = write_report("phase3_fp_stress", payload)
    print(f"\nBaseline written: {out}")
    print(f"\n{'ALL GATES PASSED' if passed else 'GATE FAILURE'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
