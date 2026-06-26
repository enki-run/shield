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


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_typed_iban_with_invalid_checksum_is_detected():
    """Audit defect: Presidio's IbanRecognizer rejects checksum-invalid IBANs
    (typos/OCR), so a mistyped German IBAN leaks verbatim. A format fallback must
    catch the DE IBAN shape (DE + 20 digits) at a lower confidence."""
    from app.pipeline.detector import PiiDetector

    det = PiiDetector(mode="balanced")
    # DE + 20 digits: syntactically an IBAN but fails the mod-97 checksum
    ents = det.detect("Bitte auf IBAN DE00 1234 5678 0000 0000 00 ueberweisen.")
    assert "IBAN_CODE" in [e.entity_type for e in ents]


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_org_with_dotted_legal_suffix_is_detected():
    """Audit defect: e.V./Ltd./Inc. end in '.', and the trailing \\b in the
    DE_OrgSuffix regex fails right after a dot, so these organizations leak."""
    from app.pipeline.detector import PiiDetector

    det = PiiDetector(mode="balanced")
    for txt in (
        "Mitglied der Beispiel Verein e.V. seit 2020.",
        "Die Rechnung der Beispiel Trading Ltd. liegt vor.",
    ):
        orgs = [e.text for e in det.detect(txt) if e.entity_type == "ORGANIZATION"]
        assert any("Beispiel" in o for o in orgs), f"dotted-suffix org leaked: {orgs} in {txt!r}"


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_ipv6_compressed_fully_covered():
    """Audit defect: Presidio's IpRecognizer truncates compressed IPv6 to the
    prefix ('2001:db8::'), so the tail leaks. A config rule must cover the full
    compressed form span-exact."""
    from app.pipeline.detector import PiiDetector

    text = "Kurzform 2001:db8::8a2e:370:7334 ebenfalls gueltig."
    value = "2001:db8::8a2e:370:7334"
    s = text.index(value)
    ents = PiiDetector(mode="balanced").detect(text)
    assert any(
        e.entity_type == "IP_ADDRESS" and e.start == s and e.end == s + len(value)
        for e in ents
    ), f"compressed IPv6 not span-exact: {[(e.entity_type, e.text) for e in ents]}"


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_ipv6_rule_no_mac_or_scope_false_positive():
    """The IPv6 rule must not flag MAC addresses or the C++ '::' scope operator."""
    from app.pipeline.detector import PiiDetector

    det = PiiDetector(mode="compliant")
    for t in ("MAC 00:1A:2B:3C:4D:5E am Switch.", "Der Operator :: in C++ trennt Namensraeume."):
        assert not [e for e in det.detect(t) if e.entity_type == "IP_ADDRESS"], t


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_de_id_card_interior_letters_detected():
    """Audit defect: the DE_Personalausweis regex hard-coded 7 digits at pos 3-9,
    missing real nPA serials with interior letters (L01X00T471)."""
    from app.pipeline.detector import PiiDetector

    det = PiiDetector(mode="balanced")
    for txt, serial in (
        ("Personalausweis-Nummer L01X00T471 vorgelegt.", "L01X00T471"),
        ("Mein Personalausweis L1234567X8 ist gueltig.", "L1234567X8"),
        ("Die Ausweisnummer C2345678Y9 wurde geprueft.", "C2345678Y9"),
    ):
        ids = [e.text for e in det.detect(txt) if e.entity_type == "DE_ID_CARD"]
        assert serial in ids, f"{serial} not detected as DE_ID_CARD"


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_de_id_card_context_free_code_not_flagged():
    """FP guard: a context-free alphanumeric code must stay below the floor and
    NOT be flagged as DE_ID_CARD (the score-0.35 + context-gate is the safeguard)."""
    from app.pipeline.detector import PiiDetector

    det = PiiDetector(mode="balanced")
    ents = det.detect("Die Bestellnummer K123456789 wurde versandt.")
    assert not [e for e in ents if e.entity_type == "DE_ID_CARD"]


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_institutional_org_with_fuer_connector_detected_without_oversweep():
    """Audit defect: DE_OrgInstitution only had the umlaut 'für' connector, so
    ASCII 'Institut fuer Forschung' was missed. The 'fuer' alternation fixes it,
    but MUST keep the (?-i:) anchoring or IGNORECASE makes it swallow the whole
    sentence."""
    from app.pipeline.detector import PiiDetector

    det = PiiDetector(mode="balanced")
    for txt, org in (
        ("Das Beispiel Institut fuer Forschung publiziert Studien.", "Beispiel Institut fuer Forschung"),
        ("Die Beispiel Stiftung fuer Bildung foerdert Schueler.", "Beispiel Stiftung fuer Bildung"),
    ):
        start = txt.index(org)
        orgs = [e for e in det.detect(txt) if e.entity_type == "ORGANIZATION"]
        assert any(e.start <= start and e.end >= start + len(org) for e in orgs), (
            f"{org!r} not covered: {[e.text for e in orgs]}"
        )
    # over-extension guard: generic 'Institut fuer X' prose must not swallow the
    # sentence tail (would be RED under a bare-'fuer' fix without (?-i:) anchoring)
    tail = "Es gibt ein Institut fuer moderne Kunst in der Naehe."
    orgs = [e for e in det.detect(tail) if e.entity_type == "ORGANIZATION"]
    assert not any("Naehe" in e.text for e in orgs), f"sentence over-sweep: {[e.text for e in orgs]}"
