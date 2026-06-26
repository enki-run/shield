"""Regression tests for PII-leak defects found in the 2026-06-25 accuracy audit.

Each test pins one confirmed defect: it fails on the pre-fix code (proving the
leak) and passes once the fix lands. Unit-level where possible (no spaCy) so the
core dedup/trim logic is tested deterministically.
"""

import pytest

from app.pipeline.detector import DetectedEntity, _deduplicate_entities

try:
    import spacy

    spacy.load("de_core_news_lg")
    HAS_SPACY = True
except (ImportError, OSError):
    HAS_SPACY = False

SKIP_MSG = "spaCy de_core_news_lg not installed"


def _e(entity_type, text, start, end, confidence, recognizer="test"):
    return DetectedEntity(
        entity_type=entity_type,
        text=text,
        start=start,
        end=end,
        confidence=confidence,
        recognizer=recognizer,
    )


def test_dedup_prefers_longer_covering_span_over_shorter_higher_confidence():
    """A short, high-confidence WRONG span must not evict the long correct span.

    Audit defect: dedup sorts only by (-confidence, type_priority) with no
    span-length term, so 'DE72' (LOCATION, 0.85) evicts the full IBAN
    'DE72 1203 0000 1052 4178 90' (0.60) and 23 chars of the account number
    leak in cleartext.
    """
    ents = [
        _e("LOCATION", "DE72", 0, 4, 0.85),
        _e("IBAN_CODE", "DE72 1203 0000 1052 4178 90", 0, 27, 0.60),
    ]
    kept = _deduplicate_entities(ents, {})
    assert [e.entity_type for e in kept] == ["IBAN_CODE"], (
        "longer covering span must win so no PII leaks in cleartext"
    )


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_credit_card_is_detected():
    """Audit defect: CreditCardRecognizer is not registered for lang='de', so
    CREDIT_CARD (in both entity sets) has 0% recall and card numbers leak."""
    from app.pipeline.detector import PiiDetector

    det = PiiDetector(mode="balanced")
    ents = det.detect("Bezahlt mit Kreditkarte 4111 1111 1111 1111 am Schalter.")
    assert "CREDIT_CARD" in [e.entity_type for e in ents]


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_org_with_ampersand_keeps_leading_name():
    """Audit defect: _trim_entity strips the leading name before an '&'
    connector, so 'Weber &' leaks from 'Weber & Klein Logistik GmbH'."""
    from app.pipeline.detector import PiiDetector

    det = PiiDetector(mode="balanced")
    ents = det.detect("Arbeitgeber: Weber & Klein Logistik GmbH in Berlin.")
    orgs = [e.text for e in ents if e.entity_type == "ORGANIZATION"]
    assert any("Weber" in o for o in orgs), f"leading name leaked; orgs={orgs}"


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_url_detected_in_balanced_mode():
    """Audit defect: UrlRecognizer scores ~0.5-0.6 < balanced 0.70, so the
    DEFAULT mode leaks URLs (6.7% recall)."""
    from app.pipeline.detector import PiiDetector

    det = PiiDetector(mode="balanced")
    ents = det.detect("Mein Profil liegt unter https://www.example.com/user/mm online.")
    assert "URL" in [e.entity_type for e in ents]


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_ip_address_detected_in_balanced_mode():
    """Audit defect: IpRecognizer scores ~0.6 < balanced 0.70, so the DEFAULT
    mode leaks IP addresses (13.3% recall)."""
    from app.pipeline.detector import PiiDetector

    det = PiiDetector(mode="balanced")
    ents = det.detect("Der Server antwortet unter der Adresse 203.0.113.42 nicht.")
    assert "IP_ADDRESS" in [e.entity_type for e in ents]


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_street_regex_does_not_swallow_preceding_words():
    """Audit defect: the greedy DE_StreetName prefix matches any words before a
    '...strasse' suffix, producing a giant LOCATION span ('Max Mustermann wohnt
    in der Musterstrasse') that — via containment dedup — swallows the real
    PERSON. The street span must stay tight and the person must survive."""
    from app.pipeline.detector import PiiDetector

    det = PiiDetector(mode="balanced")
    ents = det.detect("Max Mustermann wohnt in der Musterstrasse 1, 10115 Berlin.")
    locs = [e.text for e in ents if e.entity_type == "LOCATION"]
    assert not any("Mustermann" in loc for loc in locs), f"greedy street span: {locs}"
    assert "PERSON" in [e.entity_type for e in ents], "person swallowed by giant span"
