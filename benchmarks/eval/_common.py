"""Shared primitives for the Shield accuracy evaluation suite.

The single inflated benchmark (benchmarks/run_benchmark.py) is replaced by a set
of specialized phases under benchmarks/eval/. They all build on these helpers so
scoring is consistent and honest:

  * span-EXACT matching (char-for-char start/end + exact entity type)
  * a COVERAGE check (does a detection fully cover a gold span? a partial cover
    is a real cleartext leak under pseudonymization)
  * REAL false-positive counting (any detection not matching a gold span is a FP)

Corpus format (JSONL, one document per line):
    {"id": "...", "text": "...", "lang": "de",
     "spans": [{"start": 12, "end": 27, "type": "IBAN_CODE"}],
     "pii_free": false}
A `pii_free: true` document has no spans; every detection on it is a false positive.

Per-type corpus (JSONL, one example per line) for the recall harness:
    {"type": "IBAN_CODE", "text": "... Muster ...", "value": "DE89370400440532013000"}
`value` is the exact PII substring that must be fully covered by a detection.

ALL corpus data must use fictional PII only (Max Mustermann, Musterstrasse 1,
@example.com, fictional/test IBANs and card numbers). Never real personal data.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

# Make `import app...` work no matter where a phase script is launched from.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

CORPUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus")
BASELINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baselines")

# Fuzzy NER types collapse to one another in spaCy; the strict scorer keeps them
# distinct, but a `lenient_type` scorer may treat these as one class on request.
NER_TYPES = {"PERSON", "LOCATION", "ORGANIZATION"}


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    type: str

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.end and self.end > other.start

    def covers(self, other: "Span") -> bool:
        """True if this span fully contains `other` (no uncovered tail leak)."""
        return self.start <= other.start and self.end >= other.end


@dataclass
class Detection:
    type: str
    text: str
    start: int
    end: int
    confidence: float
    recognizer: str

    @property
    def span(self) -> Span:
        return Span(self.start, self.end, self.type)


def detect(text: str, mode: str = "balanced") -> list[Detection]:
    """Run the real Shield detector and return normalized Detection objects."""
    from app.pipeline.detector import PiiDetector

    ents = PiiDetector(mode=mode).detect(text)
    return [
        Detection(e.entity_type, e.text, e.start, e.end, e.confidence, e.recognizer)
        for e in ents
    ]


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def strict_score(gold: list[Span], detections: list[Detection], *, lenient_type: bool = False) -> dict:
    """Span-exact precision/recall/F1 with REAL false-positive counting.

    A gold span is a true positive iff some detection has the identical
    [start,end) AND the same type (or, with lenient_type, both NER types).
    Every detection that matches no gold span is a false positive.
    """
    det_spans = [d.span for d in detections]

    def same_type(a: str, b: str) -> bool:
        if a == b:
            return True
        return lenient_type and a in NER_TYPES and b in NER_TYPES

    matched_det = [False] * len(det_spans)
    tp = 0
    fn_spans: list[Span] = []
    for g in gold:
        hit = None
        for i, d in enumerate(det_spans):
            if matched_det[i]:
                continue
            if d.start == g.start and d.end == g.end and same_type(d.type, g.type):
                hit = i
                break
        if hit is not None:
            matched_det[hit] = True
            tp += 1
        else:
            fn_spans.append(g)

    fp_dets = [detections[i] for i, m in enumerate(matched_det) if not m]
    fp = len(fp_dets)
    fn = len(fn_spans)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positives": [(d.type, d.text) for d in fp_dets],
        "false_negatives": [(g.type, g.start, g.end) for g in fn_spans],
    }


def covered(gold: Span, detections: list[Detection]) -> bool:
    """True if some detection fully covers the gold span (no cleartext tail)."""
    return any(d.span.covers(gold) for d in detections)


def coverage_rate(gold: list[Span], detections: list[Detection]) -> float:
    if not gold:
        return 1.0
    return round(sum(covered(g, detections) for g in gold) / len(gold), 4)


# --------------------------------------------------------------------------- #
# Corpus + report I/O
# --------------------------------------------------------------------------- #
def load_jsonl(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def doc_spans(doc: dict) -> list[Span]:
    return [Span(s["start"], s["end"], s["type"]) for s in doc.get("spans", [])]


def write_report(name: str, payload: dict) -> str:
    os.makedirs(BASELINE_DIR, exist_ok=True)
    path = os.path.join(BASELINE_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    return path


def gate(passed: bool, label: str) -> bool:
    """Print a PASS/FAIL line; return `passed` so callers can aggregate."""
    print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
    return passed
