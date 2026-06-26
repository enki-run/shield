"""CI wrapper for PHASE 3 — false-positive stress gate.

Runs the real detector over benchmarks/eval/corpus/clean/ (four PII-FREE German
documents: an observability runbook, an invoice/boilerplate, a change-management
SOP, and a KPI metrics table). Because the documents contain NO PII, every
detection is a false positive. The gates assert over-redaction stays bounded:

  * denylist-covered worst-document FP-per-1000-tokens stays under the calibrated
    ceiling (hard gate) — catches any regression in the domain the
    false_positive_denylist is meant to cover.
  * the documents collectively yield only the expected FP drivers (tech-term->NER
    and date), i.e. NO numeric value is ever mislabeled as an ID / phone / IBAN.

KNOWN-OPEN (strict xfail): the observability runbook is built on a tech stack
ABSENT from detection_rules.json's denylist (Kafka / Datadog / Jenkins / Vault /
Loki / Prometheus / ArgoCD / Terraform / Kubernetes). spaCy NER hallucinates
ORG/PERSON/LOCATION on those proper nouns and the doc's FP rate blows past the
denylist ceiling. That is a real open defect today, so the assertion "the
non-denylist runbook is within the denylist ceiling" is marked xfail(strict=True):
it must fail now, and a future fix surfaces as XPASS telling us to tighten.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmarks.eval.phase3_fp_stress import (  # noqa: E402
    GATE_DENYLIST_FP_PER_1K,
    GATE_NONDENYLIST_FP_PER_1K,
    MODES,
    NON_DENYLIST_DOC,
    run_corpus,
)


@pytest.fixture(scope="module")
def corpus():
    per_doc, agg_drivers, summary = run_corpus()
    return {"per_doc": per_doc, "agg_drivers": agg_drivers, "summary": summary}


def test_at_least_four_clean_docs(corpus):
    """The stress corpus must hold >= 4 PII-free documents."""
    assert len(corpus["per_doc"]) >= 4


@pytest.mark.parametrize("mode", MODES)
def test_denylist_covered_within_ceiling(corpus, mode):
    """Hard gate: denylist-covered worst-doc FP/1k <= calibrated ceiling."""
    worst = corpus["summary"]["modes"][mode]["denylist_covered"]["worst_doc_fp_per_1k"]
    assert worst <= GATE_DENYLIST_FP_PER_1K, (
        f"[{mode}] denylist-covered worst-doc FP/1k regressed to {worst} "
        f"(> {GATE_DENYLIST_FP_PER_1K})"
    )


@pytest.mark.parametrize("mode", MODES)
def test_no_numeric_value_mislabeled_as_structured_pii(corpus, mode):
    """No figure/date in PII-free boilerplate may become an ID/phone/IBAN FP."""
    drivers = corpus["summary"]["modes"][mode]["driver_totals"]
    assert drivers.get("number_to_id_phone", 0) == 0, (
        f"[{mode}] a numeric value was mislabeled as structured PII: {drivers}"
    )


@pytest.mark.parametrize("mode", MODES)
def test_non_denylist_runbook_under_informational_ceiling(corpus, mode):
    """Known-open spike must not blow past its loose informational ceiling."""
    nd = corpus["summary"]["modes"][mode]["non_denylist_doc"]["fp_per_1k"]
    assert nd <= GATE_NONDENYLIST_FP_PER_1K, (
        f"[{mode}] non-denylist runbook FP/1k regressed to {nd} "
        f"(> {GATE_NONDENYLIST_FP_PER_1K})"
    )


# --------------------------------------------------------------------------- #
# Known-open defect: the non-denylist tech runbook over-redacts far above the
# denylist ceiling today. Encode as strict xfail so CI stays green now; a fix
# (e.g. denylisting Kafka/Datadog/Jenkins or NER-context gating) surfaces as
# XPASS and tells us to fold the runbook into the hard denylist gate.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.xfail(
    strict=True,
    reason="documented open defect: spaCy NER over-redacts a non-denylist tech "
           "stack (Kafka/Datadog/Jenkins/Vault/Loki/Prometheus); FP/1k exceeds "
           "the denylist ceiling. Denylist overfitting + residual NER FP.",
)
def test_known_open_non_denylist_stack_over_redacts(corpus, mode):
    nd = corpus["summary"]["modes"][mode]["non_denylist_doc"]["fp_per_1k"]
    # xfail asserts the runbook is WITHIN the denylist ceiling; it is NOT today,
    # so this fails as expected. If the defect is fixed -> XPASS alarm.
    assert nd <= GATE_DENYLIST_FP_PER_1K, (
        f"[{mode}] non-denylist runbook still over-redacts "
        f"({nd} FP/1k > {GATE_DENYLIST_FP_PER_1K})"
    )
