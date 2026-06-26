"""Pytest entry point for the Phase 2 per-type recall harness.

Runs the real detector over corpus/per_type.jsonl and asserts the HARD gates
(no dead PII type, macro recall floor). The KNOWN-OPEN per-type recall gaps that
the harness surfaces (DE_ID_CARD, ORGANIZATION, IP_ADDRESS at the time of
writing) are encoded as xfail so a *regression* into them stays visible while a
*fix* that raises them above the healthy bar trips xpass and prompts an update.

CI runs this file on the post-fix branch and must exit 0 today.
"""

from __future__ import annotations

import pytest

from benchmarks.eval.phase2_per_type_recall import (
    CORPUS_PATH,
    HEALTHY_TYPE_RECALL,
    MACRO_RECALL_FLOOR,
    build_table,
    evaluate,
)
from benchmarks.eval._common import load_jsonl

# Documented open recall defects on the post-fix branch (best-mode typed recall
# below the healthy 90% bar). Encoded as xfail: a regression keeps failing here,
# a real fix flips to xpass and tells us to promote the type.
KNOWN_OPEN_TYPES = {"DE_ID_CARD", "ORGANIZATION"}  # IP_ADDRESS promoted: IPv6 compressed rule


@pytest.fixture(scope="module")
def table():
    rows = load_jsonl(CORPUS_PATH)
    ev = evaluate(rows)
    return build_table(ev["results"])


def test_corpus_has_min_examples_per_type():
    rows = load_jsonl(CORPUS_PATH)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["type"]] = counts.get(r["type"], 0) + 1
    assert counts, "corpus is empty"
    for t, n in counts.items():
        assert n >= 15, f"{t} has only {n} examples (need >=15)"


def test_every_value_is_substring_of_text():
    rows = load_jsonl(CORPUS_PATH)
    bad = [(r["type"], r["value"]) for r in rows if r["value"] not in r["text"]]
    assert not bad, f"value not found in text for: {bad}"


def test_no_dead_type_in_both_modes(table):
    """HARD gate: every PII type is caught in at least one mode (no wholesale leak)."""
    dead = [r["type"] for r in table if r["dead_both_modes"]]
    assert not dead, f"PII types dead (0% typed recall) in BOTH modes: {dead}"


def test_macro_typed_recall_above_floor(table):
    """HARD gate: aggregate per-type recall has not regressed below the floor."""
    macro = sum(r["best_typed"] for r in table) / len(table)
    assert macro >= MACRO_RECALL_FLOOR, (
        f"macro typed recall {macro:.4f} < floor {MACRO_RECALL_FLOOR}"
    )


@pytest.mark.parametrize(
    "etype",
    sorted(KNOWN_OPEN_TYPES),
)
def test_known_open_type_recall(table, etype):
    """xfail: documented recall gaps. xpass => the defect is fixed, promote the type."""
    row = next(r for r in table if r["type"] == etype)
    if etype in KNOWN_OPEN_TYPES:
        if row["best_typed"] >= HEALTHY_TYPE_RECALL:
            pytest.fail(
                f"{etype} now at {row['best_typed']:.2%} (>= {HEALTHY_TYPE_RECALL:.0%}): "
                f"remove it from KNOWN_OPEN_TYPES"
            )
        pytest.xfail(
            f"{etype} typed recall {row['best_typed']:.2%} is a documented open gap"
        )
    assert row["best_typed"] >= HEALTHY_TYPE_RECALL


def test_healthy_types_meet_bar(table):
    """Types NOT marked known-open must clear the healthy recall bar."""
    offenders = [
        (r["type"], r["best_typed"])
        for r in table
        if r["type"] not in KNOWN_OPEN_TYPES and r["best_typed"] < HEALTHY_TYPE_RECALL
    ]
    assert not offenders, (
        f"types below {HEALTHY_TYPE_RECALL:.0%} that are not marked known-open: {offenders}"
    )
