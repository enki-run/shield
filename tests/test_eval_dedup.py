"""Phase 6 — dedup / determinism unit suite.

Deterministic unit tests for the two functions that decide which detected PII
survives into the redacted document:

  * ``_deduplicate_entities`` — resolves overlapping spans. A bad decision here
    is a real GDPR leak: if the wider/correct span loses, the uncovered tail
    (house number, account digits) stays in cleartext.
  * ``_trim_entity`` — trims spaCy NER noise off ORGANIZATION spans. Trimming a
    *regex*-recognizer span instead would strip the leading name before an '&'
    connector and leak it ('Weber & Klein GmbH' -> 'Klein GmbH').

Most tests construct ``DetectedEntity`` overlaps directly and need no spaCy.
The final determinism test spawns subprocesses under PYTHONHASHSEED 0/1/2 and
asserts ``detect()`` is byte-identical — a pseudonymization service must map the
same input to the same redaction on every run.

All data is fictional (Max Mustermann / Musterstrasse 1 / Muster GmbH /
@example.com / a fictional test IBAN).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from app.pipeline.detector import (
    DetectedEntity,
    _deduplicate_entities,
    _trim_entity,
)

# Repo root: tests/ -> repo root. Used to put the package on the subprocess path.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The production dedup config shape is {"type_priority": {TYPE: rank, ...}};
# lower rank = preferred on a tie. Mirrors detection_rules.json -> entity_dedup.
_DEDUP_CONFIG = {
    "type_priority": {
        "IBAN_CODE": 0,
        "DE_SOCIAL_SECURITY": 1,
        "DE_ID_CARD": 1,
        "LOCATION": 2,
        "ORGANIZATION": 3,
        "PHONE_NUMBER": 4,
        "PERSON": 5,
    }
}


def _e(entity_type, text, start, end, confidence, recognizer="test"):
    return DetectedEntity(
        entity_type=entity_type,
        text=text,
        start=start,
        end=end,
        confidence=confidence,
        recognizer=recognizer,
    )


def _typed(ents):
    return sorted((e.entity_type, e.start, e.end) for e in ents)


# --------------------------------------------------------------------------- #
# (a) On overlap the FULLY-CONTAINING span wins — no cleartext tail.
# --------------------------------------------------------------------------- #
def test_containing_span_wins_no_cleartext_tail():
    """A wider span that fully contains a narrower kept span replaces it, even
    when the narrower span has *higher* confidence — otherwise the uncovered
    tail leaks. Here 'Musterstrasse' (0.90) is contained by 'Musterstrasse 1'
    (0.60); the house number '1' must not survive as cleartext."""
    inner = _e("LOCATION", "Musterstrasse", 0, 13, 0.90, "DE_StreetName")
    outer = _e("LOCATION", "Musterstrasse 1", 0, 15, 0.60, "DE_StreetWithNumber")

    kept = _deduplicate_entities([inner, outer], _DEDUP_CONFIG)

    assert _typed(kept) == [("LOCATION", 0, 15)], (
        "the fully-containing span must win so the house number does not leak"
    )
    # And the order of the input list must not change the outcome.
    kept_rev = _deduplicate_entities([outer, inner], _DEDUP_CONFIG)
    assert _typed(kept_rev) == [("LOCATION", 0, 15)]


# --------------------------------------------------------------------------- #
# (b) A structured span is not evicted by a generic NER span it contains.
# --------------------------------------------------------------------------- #
def test_structured_iban_survives_overlapping_generic_ner_fragment():
    """The real-world case: spaCy mistags a fragment *inside* an IBAN as
    LOCATION (e.g. the 'DE89' country/check prefix). The wider IBAN_CODE span
    fully contains that fragment, so IBAN_CODE must survive with its structured
    type intact — losing it would both leak the account tail and mislabel the
    redaction."""
    iban = _e("IBAN_CODE", "DE89370400440532013000", 20, 42, 0.60, "IbanRecognizer")
    frag = _e("LOCATION", "DE89", 20, 24, 0.85, "SpacyRecognizer")

    kept = _deduplicate_entities([frag, iban], _DEDUP_CONFIG)

    assert _typed(kept) == [("IBAN_CODE", 20, 42)], (
        "structured IBAN must not be evicted by a generic NER fragment it contains"
    )


def test_structured_de_id_card_survives_overlapping_generic_person_fragment():
    """Same guarantee for DE_ID_CARD against a PERSON fragment spaCy may tag on
    part of the card number. The structured span fully contains the fragment and
    must keep its type."""
    idc = _e("DE_ID_CARD", "T220001293", 10, 20, 0.60, "DE_Personalausweis")
    frag = _e("PERSON", "T2200", 10, 15, 0.80, "SpacyRecognizer")

    kept = _deduplicate_entities([frag, idc], _DEDUP_CONFIG)

    assert _typed(kept) == [("DE_ID_CARD", 10, 20)], (
        "structured DE_ID_CARD must not be evicted by a generic NER fragment"
    )


@pytest.mark.xfail(
    reason=(
        "KNOWN-OPEN: the containment branch in _deduplicate_entities has no "
        "type/priority guard. On an EXACTLY-equal span the later-processed "
        "generic LOCATION 'contains' (== covers) the structured IBAN_CODE and "
        "evicts it, so the redaction is mistyped as LOCATION. Real fix: do not "
        "let an equal-span lower-priority generic type evict a higher-priority "
        "structured type. Type is preserved today only when the structured span "
        "is strictly wider than the NER fragment (the common spaCy case)."
    ),
    strict=True,
)
def test_structured_iban_survives_equal_span_generic_location():
    iban = _e("IBAN_CODE", "DE89370400440532013000", 20, 42, 0.60, "IbanRecognizer")
    loc = _e("LOCATION", "DE89370400440532013000", 20, 42, 0.60, "SpacyRecognizer")

    kept = _deduplicate_entities([loc, iban], _DEDUP_CONFIG)

    assert _typed(kept) == [("IBAN_CODE", 20, 42)]


# --------------------------------------------------------------------------- #
# (c) _trim_entity keeps a leading capitalized name before '&' on regex spans.
# --------------------------------------------------------------------------- #
def test_trim_entity_does_not_touch_regex_org_with_ampersand():
    """A regex PatternRecognizer span ('DE_OrgSuffix') is already precise.
    _trim_entity must leave it untouched — trimming it would strip the leading
    'Weber' before the '&' connector and leak the partner name."""
    org = _e(
        "ORGANIZATION", "Weber & Klein GmbH", 0, 18, 0.60, "DE_OrgSuffix (regex)"
    )
    out = _trim_entity(org, "Weber & Klein GmbH ist ein Betrieb.")

    assert out.text == "Weber & Klein GmbH"
    assert (out.start, out.end) == (0, 18)


def test_trim_entity_trims_spacy_org_but_keeps_name_before_ampersand():
    """The spaCy NER path *does* trim leading sentence fragments ('der'), but
    must stop at the first capitalized name so the '&'-joined org survives
    intact ('der Weber & Klein GmbH' -> 'Weber & Klein GmbH')."""
    text = "der Weber & Klein GmbH ist ein Betrieb."
    org = _e("ORGANIZATION", "der Weber & Klein GmbH", 0, 22, 0.60, "SpacyRecognizer")
    out = _trim_entity(org, text)

    assert out.text == "Weber & Klein GmbH", f"trim leaked/over-trimmed: {out.text!r}"
    # Span must still anchor correctly into the source text.
    assert text[out.start:out.end] == out.text


# --------------------------------------------------------------------------- #
# (d) A giant wrong span does NOT swallow two distinct neighbours.
# --------------------------------------------------------------------------- #
def test_giant_partial_span_does_not_swallow_two_neighbours():
    """A long, low-confidence wrong span that only *partially* overlaps two real
    neighbouring entities (it contains neither fully) is a conflict and is
    dropped; both real entities survive. This is what stops one bad spaCy span
    from eating a PERSON and an EMAIL on either side of it."""
    person = _e("PERSON", "Max Mustermann", 0, 14, 0.90, "SpacyRecognizer")
    email = _e("EMAIL_ADDRESS", "max@example.com", 30, 45, 0.95, "EmailRecognizer")
    # 5..40 starts inside PERSON and ends inside EMAIL -> contains neither.
    giant = _e("ORGANIZATION", "<giant>", 5, 40, 0.50, "SpacyRecognizer")

    kept = _deduplicate_entities([person, email, giant], _DEDUP_CONFIG)

    assert _typed(kept) == [("EMAIL_ADDRESS", 30, 45), ("PERSON", 0, 14)], (
        "partial-overlap giant span must be dropped, both neighbours kept"
    )
    assert all(e.entity_type != "ORGANIZATION" for e in kept)


def test_containing_span_swallows_only_what_it_fully_covers():
    """Mixed case: a wider span that fully contains ONE neighbour but only
    partially overlaps another is a conflict (the partial overlap wins the
    guard), so it is dropped and both neighbours survive — a long span never
    swallows several distinct entities."""
    a = _e("PERSON", "Max", 0, 3, 0.90, "SpacyRecognizer")
    b = _e("LOCATION", "Berlin", 20, 26, 0.90, "SpacyRecognizer")
    # 0..23 fully covers PERSON(0..3) but only partially overlaps LOCATION(20..26).
    span = _e("ORGANIZATION", "<wide>", 0, 23, 0.50, "SpacyRecognizer")

    kept = _deduplicate_entities([a, b, span], _DEDUP_CONFIG)

    assert _typed(kept) == [("LOCATION", 20, 26), ("PERSON", 0, 3)]


# --------------------------------------------------------------------------- #
# Determinism — same input -> identical typed redaction across hash seeds.
# --------------------------------------------------------------------------- #
_DETERMINISM_TEXT = (
    "Max Mustermann wohnt in der Musterstrasse 1, 10115 Berlin. "
    "Kontakt: max.mustermann@example.com, IBAN DE89370400440532013000, "
    "Telefon +49 30 12345678. Die Muster GmbH beschaeftigt ihn."
)

# Tiny driver run in a subprocess: prints the sorted typed detections as a single
# JSON line, prefixed with a sentinel so we can isolate it from structlog's
# rules-loaded log line (which may land on stdout). Repo root is injected so
# `import app...` works regardless of cwd.
_SENTINEL = "__DETECT_JSON__"
_DETERMINISM_DRIVER = (
    "import json, sys\n"
    f"sys.path.insert(0, {_REPO_ROOT!r})\n"
    "from benchmarks.eval._common import detect\n"
    f"text = {_DETERMINISM_TEXT!r}\n"
    "dets = detect(text, mode='balanced')\n"
    "out = sorted((d.type, d.start, d.end, d.text) for d in dets)\n"
    f"sys.stdout.write({_SENTINEL!r} + json.dumps(out, ensure_ascii=False))\n"
)


def _run_detect_with_seed(seed: int) -> list:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(seed)
    proc = subprocess.run(
        [sys.executable, "-c", _DETERMINISM_DRIVER],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, (
        f"detect subprocess failed (seed={seed}):\n{proc.stderr}"
    )
    # structlog may write its rules-loaded line to stdout too; take only the
    # payload after our sentinel marker.
    marker = proc.stdout.rfind(_SENTINEL)
    assert marker != -1, (
        f"sentinel not found in subprocess stdout (seed={seed}):\n{proc.stdout}"
    )
    payload = proc.stdout[marker + len(_SENTINEL):].strip()
    return json.loads(payload)


try:
    import spacy

    spacy.load("de_core_news_lg")
    HAS_SPACY = True
except (ImportError, OSError):
    HAS_SPACY = False


@pytest.mark.skipif(not HAS_SPACY, reason="spaCy de_core_news_lg not installed")
def test_detect_is_deterministic_across_hash_seeds():
    """detect() must yield byte-identical typed output under PYTHONHASHSEED 0/1/2.

    A pseudonymization service has to map identical input to identical redaction
    on every run; any hash-seed-dependent ordering or set iteration in the
    pipeline would be a correctness bug (and break reproducible mappings)."""
    results = {seed: _run_detect_with_seed(seed) for seed in (0, 1, 2)}

    baseline = results[0]
    assert baseline, "expected non-empty detections on the fixed fictional text"
    for seed in (1, 2):
        assert results[seed] == baseline, (
            f"detect() differs under PYTHONHASHSEED={seed}:\n"
            f"  seed0={baseline}\n  seed{seed}={results[seed]}"
        )
