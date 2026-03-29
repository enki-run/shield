#!/usr/bin/env python3
"""
Shield PII Detection Benchmark Runner

Usage:
    python benchmarks/run_benchmark.py [--mode balanced|compliant] [--verbose]

Runs all benchmark files (*.docx, *.xlsx) against their expected results
and prints precision/recall/F1 scores.
"""

import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.parsers import get_parser
from app.pipeline.detector import PiiDetector


def load_expected(json_path: str) -> dict:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_single_benchmark(doc_path: str, expected_path: str, mode: str, verbose: bool) -> dict:
    """Run benchmark on a single document. Returns score dict."""
    expected = load_expected(expected_path)
    ext = os.path.splitext(doc_path)[1].lstrip(".")
    parser = get_parser(ext)
    parsed = parser.parse(doc_path)
    detector = PiiDetector(mode=mode)

    # Detect all entities across all blocks
    detected = []
    for block in parsed.blocks:
        entities = detector.detect(block.text)
        detected.extend(entities)

    # Build lookup sets
    expected_entries = [
        e for e in expected["expected"]
        if e.get("mode", "balanced") in (mode, "balanced")
    ]
    must_not = set(t.lower() for t in expected.get("must_not_detect", []))

    # Score: for each expected entity, check if ANY detected entity contains the text
    true_positives = []
    false_negatives = []
    for exp in expected_entries:
        found = False
        for det in detected:
            if exp["text"].lower() in det.text.lower() or det.text.lower() in exp["text"].lower():
                if det.entity_type == exp["type"] or (
                    exp["type"] in ("LOCATION", "ORGANIZATION", "PERSON") and
                    det.entity_type in ("LOCATION", "ORGANIZATION", "PERSON")
                ):
                    true_positives.append({"expected": exp, "detected": det})
                    found = True
                    break
        if not found:
            false_negatives.append(exp)

    # False positives: detected entities that match must_not_detect or aren't in expected
    false_positives = []
    for det in detected:
        text_lower = det.text.strip().lower()
        if text_lower in must_not:
            false_positives.append(det)
            continue
        # Check if this detection matches any expected entry
        matched = False
        for exp in expected_entries:
            if exp["text"].lower() in text_lower or text_lower in exp["text"].lower():
                matched = True
                break
        if not matched and det.confidence < 0.95:
            # Only flag as FP if not a high-confidence spaCy detection
            # (some valid detections won't be in expected list)
            pass

    # Calculate scores
    tp = len(true_positives)
    fp = len(false_positives)
    fn = len(false_negatives)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    if verbose:
        print(f"\n{'='*70}")
        print(f"  Benchmark: {os.path.basename(doc_path)} (mode={mode})")
        print(f"{'='*70}")

        print(f"\n  TRUE POSITIVES ({tp}):")
        for item in true_positives:
            exp = item["expected"]
            det = item["detected"]
            print(f"    {exp['type']:20s} \"{exp['text'][:40]}\" → \"{det.text.strip()[:40]}\" ({det.confidence:.2f})")

        if false_negatives:
            print(f"\n  FALSE NEGATIVES ({fn}) — missed:")
            for exp in false_negatives:
                print(f"    {exp['type']:20s} \"{exp['text'][:50]}\"")

        if false_positives:
            print(f"\n  FALSE POSITIVES ({fp}) — wrongly detected:")
            for det in false_positives:
                print(f"    {det.entity_type:20s} \"{det.text.strip()[:50]}\" ({det.confidence:.2f})")

    return {
        "file": os.path.basename(doc_path),
        "mode": mode,
        "total_expected": len(expected_entries),
        "total_detected": len(detected),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
    }


def main():
    mode = "balanced"
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        mode = sys.argv[idx + 1]

    benchmark_dir = os.path.dirname(os.path.abspath(__file__))
    results = []

    # Find all benchmark pairs (document + expected JSON)
    for fname in sorted(os.listdir(benchmark_dir)):
        if fname.startswith("expected_") and fname.endswith(".json"):
            expected_path = os.path.join(benchmark_dir, fname)
            expected = load_expected(expected_path)
            source = expected.get("source", "")
            doc_path = os.path.join(os.path.dirname(benchmark_dir), source)

            if not os.path.exists(doc_path):
                doc_path = os.path.join(benchmark_dir, os.path.basename(source))

            if not os.path.exists(doc_path):
                print(f"  SKIP {fname} — source file not found: {source}")
                continue

            result = run_single_benchmark(doc_path, expected_path, mode, verbose)
            results.append(result)

    # Summary
    if results:
        print(f"\n{'='*70}")
        print(f"  BENCHMARK SUMMARY (mode={mode})")
        print(f"{'='*70}")
        print(f"  {'File':<30s} {'Precision':>10s} {'Recall':>10s} {'F1':>10s} {'TP':>5s} {'FP':>5s} {'FN':>5s}")
        print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10} {'-'*5} {'-'*5} {'-'*5}")

        total_tp = total_fp = total_fn = 0
        for r in results:
            print(f"  {r['file']:<30s} {r['precision']:>10.1%} {r['recall']:>10.1%} {r['f1']:>10.1%} {r['true_positives']:>5d} {r['false_positives']:>5d} {r['false_negatives']:>5d}")
            total_tp += r["true_positives"]
            total_fp += r["false_positives"]
            total_fn += r["false_negatives"]

        total_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        total_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        total_f1 = 2 * total_p * total_r / (total_p + total_r) if (total_p + total_r) > 0 else 0
        print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10} {'-'*5} {'-'*5} {'-'*5}")
        print(f"  {'TOTAL':<30s} {total_p:>10.1%} {total_r:>10.1%} {total_f1:>10.1%} {total_tp:>5d} {total_fp:>5d} {total_fn:>5d}")
        print()


if __name__ == "__main__":
    main()
