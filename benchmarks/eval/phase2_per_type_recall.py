"""PHASE 2 — Per-PII-type recall harness.

For every example in corpus/per_type.jsonl this measures, per PII type and per
detection mode (balanced + compliant), the FULL-COVER recall: the fraction of
examples where some detection of the RIGHT type fully covers the gold `value`
substring (no cleartext tail left behind). Under GDPR pseudonymization a partial
span — a surname or house-number left in cleartext — is a real PII leak, so the
bar is full coverage, not mere overlap.

Two recall views are reported per example:
  * typed full-cover  — a detection of the *exact* expected type fully covers it.
                        This is the headline recall and what the gates use.
  * any-type cover    — some detection (regardless of type) fully covers it.
                        The gap between the two flags type-confusion (the PII is
                        redacted, but mislabelled — e.g. an ID card grabbed as a
                        PERSON), which still redacts the value but muddies the
                        pseudonym mapping.

Gates (calibrated to pass on this branch, catch future regressions):
  * HARD : no PII type is at 0% typed-recall in BOTH modes (a type that is dead
           in every mode means that PII class leaks wholesale — a release
           blocker). Types live in one mode only are allowed (compliant adds
           recognizers) but reported.
  * HARD : the per-example macro typed-recall (best of the two modes) does not
           regress below a floor calibrated just under the current value.
  * SOFT/known_open : any type below 90% typed-recall in its best mode is listed
           as a documented known-open recall gap, not a hard failure.

Run:
    cd /Users/nico/Workspace/shield && \
    .venv/bin/python benchmarks/eval/phase2_per_type_recall.py

Exits 0 when all HARD gates pass; non-zero on regression.
"""

from __future__ import annotations

import os
import sys

from benchmarks.eval._common import (
    CORPUS_DIR,
    Span,
    covered,
    detect,
    gate,
    load_jsonl,
    write_report,
)

CORPUS_PATH = os.path.join(CORPUS_DIR, "per_type.jsonl")
MODES = ("balanced", "compliant")

# Recall floor for the macro best-of-modes typed recall. The real measured value
# on this branch is 92.2% (see baselines/phase2_per_type_recall.json); this floor
# sits a small margin below it so the suite passes today yet fails the moment
# overall per-type recall regresses (e.g. a recognizer drops out or a dedup
# change starts swallowing structured PII into spaCy LOCATION spans).
MACRO_RECALL_FLOOR = 0.90

# A per-type recall at/above this in its best mode is considered healthy. Types
# below it are reported as known-open recall gaps (not a hard failure) — these
# map onto the documented OPEN defects (DE_ID_CARD regex/priority, ORGANIZATION
# e.V./Ltd./suffixless recall, etc.).
HEALTHY_TYPE_RECALL = 0.90


def _locate(text: str, value: str) -> Span | None:
    """Gold span for `value` inside `text` (first occurrence). type filled later."""
    idx = text.find(value)
    if idx < 0:
        return None
    return Span(idx, idx + len(value), "")


def _typed_dets(detections, expected_type):
    return [d for d in detections if d.type == expected_type]


def evaluate(rows: list[dict]) -> dict:
    """Run detection for every example in every mode; collect per-type tallies."""
    # results[mode][type] = {"n", "typed", "any", "examples":[...]}
    results: dict[str, dict[str, dict]] = {m: {} for m in MODES}
    skipped: list[dict] = []

    for row in rows:
        etype = row["type"]
        text = row["text"]
        value = row["value"]
        gold = _locate(text, value)
        if gold is None:
            skipped.append({"type": etype, "value": value, "reason": "value-not-in-text"})
            continue

        for mode in MODES:
            dets = detect(text, mode=mode)
            typed_cover = covered(gold, _typed_dets(dets, etype))
            any_cover = covered(gold, dets)

            bucket = results[mode].setdefault(
                etype, {"n": 0, "typed": 0, "any": 0, "misses": []}
            )
            bucket["n"] += 1
            bucket["typed"] += int(typed_cover)
            bucket["any"] += int(any_cover)
            if not typed_cover:
                # What did we get instead? Helps explain type-confusion vs miss.
                got = sorted({d.type for d in dets if d.span.overlaps(gold)})
                bucket["misses"].append(
                    {"value": value, "got_overlapping_types": got}
                )

    return {"results": results, "skipped": skipped}


def _rate(bucket: dict, key: str) -> float:
    return bucket[key] / bucket["n"] if bucket["n"] else 0.0


def build_table(results: dict) -> list[dict]:
    """One row per type with per-mode typed/any recall + best-mode summary."""
    all_types = sorted({t for mode in MODES for t in results[mode]})
    table = []
    for t in all_types:
        row = {"type": t}
        best_typed = 0.0
        best_any = 0.0
        n = 0
        for mode in MODES:
            b = results[mode].get(t)
            if b is None:
                row[f"{mode}_typed"] = None
                row[f"{mode}_any"] = None
                continue
            n = b["n"]
            tr = _rate(b, "typed")
            ar = _rate(b, "any")
            row[f"{mode}_typed"] = round(tr, 4)
            row[f"{mode}_any"] = round(ar, 4)
            best_typed = max(best_typed, tr)
            best_any = max(best_any, ar)
        row["n"] = n
        row["best_typed"] = round(best_typed, 4)
        row["best_any"] = round(best_any, 4)
        # zero in BOTH modes => the dead-type condition the hard gate guards
        row["dead_both_modes"] = all(
            (results[mode].get(t) is not None and _rate(results[mode][t], "typed") == 0.0)
            for mode in MODES
            if results[mode].get(t) is not None
        )
        table.append(row)
    # worst-first by best typed recall
    table.sort(key=lambda r: (r["best_typed"], r["best_any"], r["type"]))
    return table


def _fmt_pct(v) -> str:
    return "   n/a" if v is None else f"{v * 100:5.1f}%"


def print_table(table: list[dict]) -> None:
    print()
    print("PER-TYPE FULL-COVER RECALL (worst-first)")
    print("  typed = right-type detection fully covers value")
    print("  any   = some detection fully covers value (type-agnostic)")
    print()
    header = (
        f"  {'TYPE':<20} {'N':>3}  "
        f"{'bal_typed':>9} {'bal_any':>8}  "
        f"{'cmp_typed':>9} {'cmp_any':>8}  {'best_typ':>8}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in table:
        flag = "  <- DEAD" if r["dead_both_modes"] else (
            "  <- gap" if r["best_typed"] < HEALTHY_TYPE_RECALL else ""
        )
        print(
            f"  {r['type']:<20} {r['n']:>3}  "
            f"{_fmt_pct(r.get('balanced_typed')):>9} {_fmt_pct(r.get('balanced_any')):>8}  "
            f"{_fmt_pct(r.get('compliant_typed')):>9} {_fmt_pct(r.get('compliant_any')):>8}  "
            f"{_fmt_pct(r['best_typed']):>8}{flag}"
        )
    print()


def main() -> int:
    rows = load_jsonl(CORPUS_PATH)
    print(f"Loaded {len(rows)} per-type examples from {CORPUS_PATH}")

    ev = evaluate(rows)
    results = ev["results"]
    table = build_table(results)
    print_table(table)

    if ev["skipped"]:
        print(f"  WARNING: {len(ev['skipped'])} example(s) skipped (value not in text):")
        for s in ev["skipped"]:
            print(f"    - {s['type']}: {s['value']!r}")

    # macro best-of-modes typed recall (per-type mean, equal weight per type)
    macro = (
        sum(r["best_typed"] for r in table) / len(table) if table else 0.0
    )
    # micro (per-example) best-of-modes typed recall
    total_n = sum(r["n"] for r in table)
    micro = (
        sum(r["best_typed"] * r["n"] for r in table) / total_n if total_n else 0.0
    )

    dead = [r["type"] for r in table if r["dead_both_modes"]]
    known_open = [
        {
            "type": r["type"],
            "best_typed_recall": r["best_typed"],
            "best_any_recall": r["best_any"],
        }
        for r in table
        if r["best_typed"] < HEALTHY_TYPE_RECALL
    ]

    print(f"  Macro typed recall (mean over types, best mode): {macro * 100:5.1f}%")
    print(f"  Micro typed recall (per example,   best mode):   {micro * 100:5.1f}%")
    print()

    print("GATES")
    g_no_dead = gate(not dead, "no PII type at 0% typed-recall in BOTH modes")
    if dead:
        print(f"          dead types: {', '.join(dead)}")
    g_macro = gate(
        macro >= MACRO_RECALL_FLOOR,
        f"macro typed recall {macro * 100:.1f}% >= floor {MACRO_RECALL_FLOOR * 100:.1f}%",
    )

    if known_open:
        print()
        print(f"  KNOWN-OPEN recall gaps (<{int(HEALTHY_TYPE_RECALL * 100)}% best-mode typed, documented, not failing):")
        for ko in known_open:
            print(
                f"    - {ko['type']:<20} typed={ko['best_typed_recall'] * 100:5.1f}%  "
                f"any-cover={ko['best_any_recall'] * 100:5.1f}%"
            )

    payload = {
        "phase": "phase2-per-type-recall",
        "corpus": os.path.relpath(CORPUS_PATH, os.path.dirname(os.path.dirname(CORPUS_DIR))),
        "n_examples": len(rows),
        "modes": list(MODES),
        "macro_typed_recall_best_mode": round(macro, 4),
        "micro_typed_recall_best_mode": round(micro, 4),
        "macro_recall_floor": MACRO_RECALL_FLOOR,
        "healthy_type_recall": HEALTHY_TYPE_RECALL,
        "per_type": table,
        "dead_types": dead,
        "known_open": known_open,
        "skipped": ev["skipped"],
        "gates": {
            "no_dead_type": g_no_dead,
            "macro_recall_floor": g_macro,
        },
    }
    path = write_report("phase2_per_type_recall", payload)
    print()
    print(f"  Baseline written: {path}")

    all_pass = g_no_dead and g_macro
    print()
    print(f"PHASE 2 {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
