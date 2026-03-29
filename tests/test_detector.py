import pytest

try:
    import spacy

    spacy.load("de_core_news_lg")
    HAS_SPACY = True
except (ImportError, OSError):
    HAS_SPACY = False

SKIP_MSG = "spaCy de_core_news_lg not installed"


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_detect_person_balanced():
    from app.pipeline.detector import PiiDetector

    detector = PiiDetector(mode="balanced")
    entities = detector.detect("Max Müller wohnt in Berlin.")
    types = [e.entity_type for e in entities]
    assert "PERSON" in types


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_detect_email_balanced():
    from app.pipeline.detector import PiiDetector

    detector = PiiDetector(mode="balanced")
    entities = detector.detect("Kontaktiere mich unter hans.meier@beispiel.de bitte.")
    types = [e.entity_type for e in entities]
    assert "EMAIL_ADDRESS" in types


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_detect_iban():
    from app.pipeline.detector import PiiDetector

    detector = PiiDetector(mode="balanced")
    entities = detector.detect("Bitte überweise auf IBAN DE89370400440532013000.")
    types = [e.entity_type for e in entities]
    assert "IBAN_CODE" in types


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_detect_ip_address():
    from app.pipeline.detector import PiiDetector

    detector = PiiDetector(mode="balanced")
    entities = detector.detect("Der Server hat die IP-Adresse 192.168.1.100.")
    types = [e.entity_type for e in entities]
    assert "IP_ADDRESS" in types


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_compliant_mode_includes_date_time():
    from app.pipeline.detector import PiiDetector

    detector = PiiDetector(mode="compliant")
    entities = detector.detect("Das Treffen findet am 01.01.2024 statt.")
    types = [e.entity_type for e in entities]
    assert "DATE_TIME" in types


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_entities_sorted_by_start():
    from app.pipeline.detector import PiiDetector

    detector = PiiDetector(mode="balanced")
    entities = detector.detect(
        "Max Müller schreibt an anna@example.de wegen 192.168.0.1."
    )
    starts = [e.start for e in entities]
    assert starts == sorted(starts)


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_detected_entity_fields():
    from app.pipeline.detector import PiiDetector

    detector = PiiDetector(mode="balanced")
    entities = detector.detect("Schreib mir an test@example.de.")
    assert len(entities) >= 1
    email_entities = [e for e in entities if e.entity_type == "EMAIL_ADDRESS"]
    assert len(email_entities) >= 1
    e = email_entities[0]
    assert e.text == "test@example.de"
    assert e.start >= 0
    assert e.end > e.start
    assert 0.0 <= e.confidence <= 1.0
    assert isinstance(e.recognizer, str)


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_no_false_positives_empty_text():
    from app.pipeline.detector import PiiDetector

    detector = PiiDetector(mode="balanced")
    entities = detector.detect("")
    assert entities == []


@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
def test_balanced_mode_lower_threshold_than_compliant():
    from app.pipeline.detector import PiiDetector, CONFIDENCE_THRESHOLDS

    assert CONFIDENCE_THRESHOLDS["balanced"] > CONFIDENCE_THRESHOLDS["compliant"]
