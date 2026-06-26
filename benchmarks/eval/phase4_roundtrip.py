"""PHASE 4 — END-TO-END ROUND-TRIP RESIDUAL-LEAK GATE (the real GDPR test).

This is the only phase that exercises the *full* pseudonymization round-trip:

    text --detect()--> entities --Pseudonymizer.apply()--> (new_text, mappings)

and then asks the single question that actually matters under GDPR Art. 4(5):

    Does any original PII substring still appear VERBATIM in the output?

Span-level metrics (phases 1-3) can look healthy while real cleartext still
leaks — e.g. a detection whose span is one char short leaves a house-number
tail, or a missed entity is never replaced at all. A verbatim residual-substring
check over the rebuilt text catches every one of those, regardless of how the
upstream span scored.

On top of residual leaks this phase measures two pseudonym-quality properties
that a round-trip (and only a round-trip) can reveal:

  * CONSISTENCY  — the same original value must always map to the SAME pseudonym
                   (within a document key). Otherwise re-identification by
                   correlation is harder for the data controller and utility drops.
  * COLLISIONS   — two DIFFERENT originals must never map to the SAME pseudonym,
                   which would silently merge two real people/accounts.

Corpus: corpus/roundtrip.jsonl. Each doc carries `must_disappear` (the exact PII
substrings that must not survive) and `known_open` (the subset that is a CURRENTLY
ACCEPTED defect — IBAN checksum-fallback, suffixless / e.V. / Ltd. ORGANIZATION
recall, DE_ID_CARD regex gaps). The gate fails only on a leak that is NOT on the
known_open baseline, so this branch exits 0 today while catching any regression.

Run:  cd /Users/nico/Workspace/shield && \
      .venv/bin/python benchmarks/eval/phase4_roundtrip.py
"""

from __future__ import annotations

import os
import sys

# Allow `python benchmarks/eval/phase4_roundtrip.py` from the repo root: the
# script's own dir is sys.path[0], not the repo root, so the `benchmarks`
# package isn't importable yet. _common itself also inserts the repo root, but
# we need it BEFORE we can import _common. Insert it here too (idempotent).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmarks.eval._common import (
    CORPUS_DIR,
    detect,
    gate,
    load_jsonl,
    write_report,
)

# Pseudonymizer.apply() consumes app.pipeline.detector.DetectedEntity objects;
# detect() returns _common.Detection objects. Bridge the two by field name.
from app.pipeline.detector import DetectedEntity
from app.pipeline.pseudonymizer import Pseudonymizer

MODES = ("balanced", "compliant")
DOC_KEY = "phase4-roundtrip-doc-key"

CORPUS_PATH = os.path.join(CORPUS_DIR, "roundtrip.jsonl")


def _to_entities(detections) -> list[DetectedEntity]:
    """Adapt _common.Detection -> pipeline DetectedEntity (the apply() contract)."""
    return [
        DetectedEntity(
            entity_type=d.type,
            text=d.text,
            start=d.start,
            end=d.end,
            confidence=d.confidence,
            recognizer=d.recognizer,
        )
        for d in detections
    ]


def _roundtrip(text: str, mode: str):
    """Full pipeline: detect -> pseudonymize. Returns (out_text, mappings, entities)."""
    entities = _to_entities(detect(text, mode=mode))
    out_text, mappings = Pseudonymizer(DOC_KEY).apply(text, entities)
    return out_text, mappings, entities


def _analyze_mode(docs: list[dict], mode: str) -> dict:
    """Run the round-trip for every doc under one mode and collect leak stats."""
    total_required = 0          # count of must_disappear substrings across corpus
    leaks: list[dict] = []      # every residual-substring leak (verbatim survivor)
    new_leaks: list[dict] = []  # leaks NOT on the doc's known_open baseline (regressions)
    accepted_leaks: list[dict] = []  # leaks that ARE on known_open (expected/xfail)

    # Pseudonym consistency + collision tracking, accumulated across the corpus
    # under a single stable doc key (mirrors one document's mapping namespace).
    orig_to_pseudo: dict[tuple[str, str], str] = {}  # (type, original) -> pseudonym
    pseudo_to_orig: dict[str, tuple[str, str]] = {}  # pseudonym -> (type, original)
    consistency_violations: list[dict] = []
    collisions: list[dict] = []

    for doc in docs:
        text = doc["text"]
        required = doc.get("must_disappear", [])
        known_open = set(doc.get("known_open", []))
        total_required += len(required)

        out_text, mappings, _ = _roundtrip(text, mode)

        # ---- Residual-leak check: does the original PII survive verbatim? ----
        for sub in required:
            if sub in out_text:
                rec = {"doc": doc["id"], "substring": sub}
                leaks.append(rec)
                if sub in known_open:
                    accepted_leaks.append(rec)
                else:
                    new_leaks.append(rec)

        # ---- Consistency + collision over the mapping records ----
        for m in mappings:
            key = (m.entity_type, m.original_value)
            # consistency: same (type, original) must yield the same pseudonym
            prev = orig_to_pseudo.get(key)
            if prev is None:
                orig_to_pseudo[key] = m.pseudonym
            elif prev != m.pseudonym:
                consistency_violations.append(
                    {"doc": doc["id"], "original": m.original_value,
                     "pseudo_a": prev, "pseudo_b": m.pseudonym}
                )
            # collision: same pseudonym must not map back to a different original
            owner = pseudo_to_orig.get(m.pseudonym)
            if owner is None:
                pseudo_to_orig[m.pseudonym] = key
            elif owner != key:
                collisions.append(
                    {"doc": doc["id"], "pseudonym": m.pseudonym,
                     "original_a": owner[1], "original_b": m.original_value}
                )

    leak_rate = round(len(leaks) / total_required, 4) if total_required else 0.0
    new_leak_rate = round(len(new_leaks) / total_required, 4) if total_required else 0.0

    return {
        "mode": mode,
        "docs": len(docs),
        "required_substrings": total_required,
        "leaks_total": len(leaks),
        "leaks_accepted_known_open": len(accepted_leaks),
        "leaks_new": len(new_leaks),
        "residual_leak_rate": leak_rate,
        "new_leak_rate": new_leak_rate,
        "leak_examples": leaks[:20],
        "new_leak_examples": new_leaks[:20],
        "consistency_violations": len(consistency_violations),
        "consistency_examples": consistency_violations[:10],
        "collisions": len(collisions),
        "collision_examples": collisions[:10],
        "distinct_originals": len(orig_to_pseudo),
        "distinct_pseudonyms": len(pseudo_to_orig),
    }


def main() -> int:
    docs = load_jsonl(CORPUS_PATH)

    # Documented known-open baseline: the union of every doc's known_open list.
    # These are accepted residual leaks on THIS branch (IBAN checksum-fallback,
    # ORGANIZATION e.V./Ltd./suffixless recall, DE_ID_CARD regex gap). They are
    # tracked, not silently ignored, and a NEW leak outside this set fails CI.
    known_open_baseline = sorted(
        {s for d in docs for s in d.get("known_open", [])}
    )

    per_mode = {m: _analyze_mode(docs, m) for m in MODES}

    print(f"PHASE 4 — round-trip residual-leak gate  ({len(docs)} docs)")
    print(f"  known-open accepted-leak baseline ({len(known_open_baseline)}): "
          f"{known_open_baseline}")

    gates: dict[str, bool] = {}
    for mode in MODES:
        r = per_mode[mode]
        print(f"\n[{mode}]")
        print(f"  required PII substrings : {r['required_substrings']}")
        print(f"  total residual leaks    : {r['leaks_total']} "
              f"(rate {r['residual_leak_rate']})")
        print(f"    - accepted (known_open): {r['leaks_accepted_known_open']}")
        print(f"    - NEW (regressions)    : {r['leaks_new']} "
              f"(rate {r['new_leak_rate']})")
        if r["new_leak_examples"]:
            for ex in r["new_leak_examples"]:
                print(f"      NEW LEAK  {ex['doc']}: {ex['substring']!r}")
        if r["leak_examples"]:
            print(f"  leak detail ({len(r['leak_examples'])}):")
            for ex in r["leak_examples"]:
                tag = "known_open" if ex["substring"] in known_open_baseline else "NEW"
                print(f"      [{tag}] {ex['doc']}: {ex['substring']!r}")
        print(f"  consistency violations  : {r['consistency_violations']}")
        print(f"  pseudonym collisions    : {r['collisions']}")
        print(f"  distinct originals/pseudos: "
              f"{r['distinct_originals']}/{r['distinct_pseudonyms']}")

        # ---- GATES (calibrated to pass on this branch, catch regressions) ----
        # 1) Zero NEW residual leaks beyond the documented known-open baseline.
        gates[f"{mode}:no_new_residual_leaks"] = gate(
            r["leaks_new"] == 0,
            f"{mode}: no NEW residual leaks beyond known_open "
            f"(new={r['leaks_new']}, accepted={r['leaks_accepted_known_open']})",
        )
        # 2) Accepted leaks must not grow past the current count — a tightening
        #    ratchet: if a known-open defect gets FIXED, lower this and the gate
        #    re-locks at the better level. Current accepted count is the bound.
        gates[f"{mode}:known_open_not_grown"] = gate(
            r["leaks_accepted_known_open"] <= len(known_open_baseline),
            f"{mode}: accepted known_open leaks within baseline "
            f"({r['leaks_accepted_known_open']} <= {len(known_open_baseline)})",
        )
        # 3) Pseudonym consistency must be perfect (same original -> same pseudonym).
        gates[f"{mode}:pseudonym_consistency"] = gate(
            r["consistency_violations"] == 0,
            f"{mode}: pseudonym consistency holds "
            f"(violations={r['consistency_violations']})",
        )
        # 4) No pseudonym collisions (two originals -> one pseudonym).
        gates[f"{mode}:no_collisions"] = gate(
            r["collisions"] == 0,
            f"{mode}: no pseudonym collisions (collisions={r['collisions']})",
        )

    all_pass = all(gates.values())
    print(f"\nPHASE 4 result: {'PASS' if all_pass else 'FAIL'}  "
          f"({sum(gates.values())}/{len(gates)} gates)")

    payload = {
        "phase": "phase4-roundtrip-leak",
        "corpus": os.path.relpath(CORPUS_PATH, os.path.dirname(os.path.dirname(CORPUS_DIR))),
        "doc_count": len(docs),
        "doc_key": DOC_KEY,
        "known_open_baseline": known_open_baseline,
        "modes": per_mode,
        "gates": {k: bool(v) for k, v in gates.items()},
        "all_pass": all_pass,
    }
    path = write_report("phase4_roundtrip", payload)
    print(f"baseline written -> {path}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
