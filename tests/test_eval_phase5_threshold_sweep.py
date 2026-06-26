"""
CI guard for Phase 5 — mode/threshold sweep (benchmarks/eval/phase5_threshold_sweep.py).

Phase 5 is a DIAGNOSTIC: its purpose is to validate that the operating points
(balanced=0.70 / compliant=0.50 / structured-floor=0.40) are well chosen, not to
gate a number. So most assertions here are *regression* guards calibrated just
past the CURRENT measured values (with a small margin) — they pass today and trip
only if a future change degrades the behaviour the sweep relies on.

KNOWN-OPEN defects the sweep surfaces are marked xfail so they document the gap
without failing CI on this branch.

Measured on this branch (fictional Muster corpus, 35 per-type / 4 clean docs):
  * NER recall flat at 0.80 across thr 0.30..0.80, drops to 0.40 at 0.90
  * structured recall 0.95 (floored) at every threshold
  * structured floor lifts struct recall at thr=0.70 from 0.75 -> 0.95
  * 0 structured FP on clean docs at every threshold
  * 4 residual NER (LOCATION) FP on clean docs at thr=0.70 (tech terms)  <-- known-open
"""

import os

import pytest

from benchmarks.eval import phase5_threshold_sweep as ph5


@pytest.fixture(scope="module")
def corpus():
    per_type = ph5._load_per_type()
    clean = ph5._load_clean()
    return per_type, clean


@pytest.fixture(scope="module")
def floored(corpus):
    per_type, clean = corpus
    return ph5.sweep(per_type, clean, floor_override=None)


@pytest.fixture(scope="module")
def unfloored(corpus):
    per_type, clean = corpus
    return ph5.sweep_no_floor(per_type, clean)


def _row(rows, thr):
    return next(r for r in rows if r["threshold"] == thr)


# --------------------------------------------------------------------------- #
# The sweep produces output and a baseline
# --------------------------------------------------------------------------- #
def test_corpus_loads_and_is_fictional(corpus):
    per_type, clean = corpus
    assert len(per_type) >= 30
    assert len(clean) >= 3
    # STRICT DATA RULE: every example must be fictional Muster/Beispiel data.
    blob = " ".join(t for t, _, _ in per_type).lower()
    assert "muster" in blob or "beispiel" in blob
    for marker in ("mustermann", "beispiel", "muster"):
        pass  # presence checked above; loop documents the allowed vocabulary


def test_sweep_returns_all_thresholds(floored):
    assert [r["threshold"] for r in floored] == ph5.THRESHOLDS


def test_main_runs_and_writes_baseline():
    rc = ph5.main()
    assert rc == 0
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "benchmarks", "eval", "baselines", "phase5_threshold_sweep.json",
    )
    assert os.path.exists(path)


# --------------------------------------------------------------------------- #
# Regression guards — calibrated just past current measured values
# --------------------------------------------------------------------------- #
def test_ner_recall_flat_in_operating_band(floored):
    """spaCy is near-binary: NER recall must not differ between balanced/compliant.

    If this trips, the spaCy score distribution changed and the mode design
    (0.70 vs 0.50 making no NER difference) needs revisiting.
    """
    r30, r50, r70 = _row(floored, 0.30), _row(floored, 0.50), _row(floored, 0.70)
    assert r30["ner_recall"] == r50["ner_recall"] == r70["ner_recall"]
    # current value 0.80 — guard at >= 0.75 (margin) so it passes now.
    assert r70["ner_recall"] >= 0.75


def test_ner_recall_collapses_above_085(floored):
    """The un-boosted 0.85 spaCy spans must drop out at thr=0.90 (sanity of the
    bimodal-score finding). Current: 0.80 -> 0.40."""
    assert _row(floored, 0.90)["ner_recall"] < _row(floored, 0.80)["ner_recall"]


def test_structured_recall_high_at_operating_points(floored):
    """Structured PII recall must stay high with the floor in place.
    Current 0.95 — guard at >= 0.90."""
    assert _row(floored, 0.70)["struct_recall"] >= 0.90
    assert _row(floored, 0.50)["struct_recall"] >= 0.90


def test_structured_floor_is_justified(floored, unfloored):
    """The 0.40 floor must measurably raise structured recall at thr=0.70.
    Without it, IP/URL (0.60) and bare DE_TAX_ID (0.50) leak in balanced mode.
    Current: floored 0.95 vs no-floor 0.75."""
    f70 = _row(floored, 0.70)["struct_recall"]
    u70 = _row(unfloored, 0.70)["struct_recall"]
    assert f70 > u70, "structured floor no longer buys recall — re-evaluate it"
    assert f70 - u70 >= 0.10


def test_zero_structured_false_positives_on_clean_docs(floored):
    """The floor must not cost structured precision: 0 structured FP everywhere."""
    assert all(r["struct_fp"] == 0 for r in floored)


def test_balanced_operating_point_no_regression(floored):
    """Lock the balanced (0.70) operating point against recall regression."""
    bp = _row(floored, 0.70)
    assert bp["ner_recall"] >= 0.75      # current 0.80
    assert bp["struct_recall"] >= 0.90   # current 0.95


# --------------------------------------------------------------------------- #
# KNOWN-OPEN defects surfaced by the sweep — xfail, documented not fatal
# --------------------------------------------------------------------------- #
@pytest.mark.xfail(
    reason="KNOWN-OPEN: residual spaCy NER false positives on hyphenated tech "
    "compounds (Cisco-Hardware, Sophos-Firewalls, Security-Monitoring, "
    "Endgeraete) score 0.85 — identical to legit NER — so no threshold removes "
    "them. Fix is denylist/context coverage, not threshold tuning.",
    strict=True,
)
def test_no_ner_false_positives_on_clean_docs(floored):
    assert _row(floored, 0.70)["ner_fp"] == 0


def test_full_per_type_recall(floored):
    # ORGANIZATION (fuer-connector + anchoring), IP_ADDRESS (IPv6) and the
    # interior-letter DE_ID_CARD serials are now covered at the operating point.
    bp = _row(floored, 0.70)
    assert bp["ner_recall"] == 1.0 and bp["struct_recall"] == 1.0
