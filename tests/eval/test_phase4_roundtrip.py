"""CI wrapper for PHASE 4 — round-trip residual-leak gate.

Runs the real end-to-end round-trip (detect -> Pseudonymizer.apply) over
benchmarks/eval/corpus/roundtrip.jsonl and asserts the calibrated gates:

  * ZERO new residual leaks beyond the documented known-open baseline (per mode)
  * pseudonym consistency (same original -> same pseudonym)
  * no pseudonym collisions (two originals -> one pseudonym)

The currently-OPEN defects (IBAN checksum-fallback, ORGANIZATION e.V./Ltd./
suffixless recall, DE_ID_CARD regex gap) are encoded as the corpus `known_open`
list AND asserted here as xfail(strict=True): each is a real verbatim leak today,
so the xfail must actually fail — if one is fixed, the strict xfail flips to a
visible XPASS and tells us to tighten the baseline. No silent passes either way.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmarks.eval._common import CORPUS_DIR, load_jsonl  # noqa: E402
from benchmarks.eval.phase4_roundtrip import (  # noqa: E402
    MODES,
    _analyze_mode,
    _roundtrip,
)

CORPUS_PATH = os.path.join(CORPUS_DIR, "roundtrip.jsonl")


@pytest.fixture(scope="module")
def docs():
    return load_jsonl(CORPUS_PATH)


@pytest.fixture(scope="module")
def results(docs):
    return {m: _analyze_mode(docs, m) for m in MODES}


@pytest.mark.parametrize("mode", MODES)
def test_no_new_residual_leaks(results, mode):
    """Hard gate: no PII leak outside the documented known-open baseline."""
    r = results[mode]
    assert r["leaks_new"] == 0, (
        f"[{mode}] NEW residual leaks (regressions): {r['new_leak_examples']}"
    )


@pytest.mark.parametrize("mode", MODES)
def test_accepted_leaks_within_baseline(results, mode):
    """Known-open accepted leaks must not grow beyond the baseline size."""
    r = results[mode]
    baseline_size = len({s for d in load_jsonl(CORPUS_PATH)
                         for s in d.get("known_open", [])})
    assert r["leaks_accepted_known_open"] <= baseline_size


@pytest.mark.parametrize("mode", MODES)
def test_pseudonym_consistency(results, mode):
    """Same original value must always map to the same pseudonym."""
    r = results[mode]
    assert r["consistency_violations"] == 0, r["consistency_examples"]


@pytest.mark.parametrize("mode", MODES)
def test_no_pseudonym_collisions(results, mode):
    """Two different originals must never collapse to one pseudonym."""
    r = results[mode]
    assert r["collisions"] == 0, r["collision_examples"]


@pytest.mark.parametrize("mode", MODES)
def test_clean_docs_have_zero_leaks(docs, mode):
    """Docs with no known_open entry must round-trip with NO residual PII."""
    for doc in docs:
        if doc.get("known_open"):
            continue
        out_text, _, _ = _roundtrip(doc["text"], mode)
        for sub in doc["must_disappear"]:
            assert sub not in out_text, (
                f"[{mode}] clean doc {doc['id']} leaked {sub!r}"
            )


# --------------------------------------------------------------------------- #
# Known-open defects: each is a REAL verbatim leak today. Encode as strict
# xfail so CI stays green now, but a fix surfaces as XPASS -> tighten baseline.
# --------------------------------------------------------------------------- #
def _known_open_cases():
    cases = []
    for doc in load_jsonl(CORPUS_PATH):
        for sub in doc.get("known_open", []):
            cases.append(pytest.param(doc["id"], sub, id=f"{doc['id']}::{sub}"))
    return cases


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("doc_id,substring", _known_open_cases())
@pytest.mark.xfail(
    strict=True,
    reason="documented open defect: IBAN checksum-fallback / suffixless+e.V.+Ltd. "
           "ORGANIZATION recall / DE_ID_CARD regex gap — leaks verbatim today",
)
def test_known_open_defect_still_leaks(docs, mode, doc_id, substring):
    doc = next(d for d in docs if d["id"] == doc_id)
    out_text, _, _ = _roundtrip(doc["text"], mode)
    # xfail asserts the leak is STILL present; pass (=leak gone) -> XPASS alarm.
    assert substring not in out_text
