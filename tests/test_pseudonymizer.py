import pytest
from app.pipeline.detector import DetectedEntity
from app.pipeline.pseudonymizer import Pseudonymizer, MappingRecord


def _make_entity(entity_type: str, text: str, start: int = 0) -> DetectedEntity:
    return DetectedEntity(
        entity_type=entity_type,
        text=text,
        start=start,
        end=start + len(text),
        confidence=0.9,
        recognizer="test",
    )


def test_generate_pseudonym_format():
    p = Pseudonymizer(doc_key="test-key")
    entity = _make_entity("PERSON", "Max Müller")
    pseudonym = p.pseudonymize(entity)
    # Format: ENTITY_TYPE-XXXXXXXX (8 uppercase hex chars)
    assert pseudonym.startswith("PERSON-")
    suffix = pseudonym[len("PERSON-"):]
    assert len(suffix) == 8
    assert suffix == suffix.upper()
    assert all(c in "0123456789ABCDEF" for c in suffix)


def test_deterministic_same_key():
    p = Pseudonymizer(doc_key="secret-key")
    entity = _make_entity("PERSON", "Anna Schmidt")
    result1 = p.pseudonymize(entity)
    result2 = p.pseudonymize(entity)
    assert result1 == result2


def test_deterministic_new_instance():
    entity = _make_entity("EMAIL_ADDRESS", "test@example.de")
    p1 = Pseudonymizer(doc_key="my-doc-key")
    p2 = Pseudonymizer(doc_key="my-doc-key")
    assert p1.pseudonymize(entity) == p2.pseudonymize(entity)


def test_different_texts_different_pseudonyms():
    p = Pseudonymizer(doc_key="key123")
    e1 = _make_entity("PERSON", "Max Müller")
    e2 = _make_entity("PERSON", "Anna Schmidt")
    assert p.pseudonymize(e1) != p.pseudonymize(e2)


def test_different_doc_keys_different_pseudonyms():
    entity = _make_entity("PERSON", "Max Müller")
    p1 = Pseudonymizer(doc_key="key-one")
    p2 = Pseudonymizer(doc_key="key-two")
    assert p1.pseudonymize(entity) != p2.pseudonymize(entity)


def test_same_text_different_entity_types():
    p = Pseudonymizer(doc_key="mykey")
    e1 = _make_entity("PERSON", "Berlin")
    e2 = _make_entity("LOCATION", "Berlin")
    # Different entity types → different cache keys → different pseudonyms
    assert p.pseudonymize(e1) != p.pseudonymize(e2)


def test_cache_hit():
    p = Pseudonymizer(doc_key="cache-test-key")
    entity = _make_entity("PHONE_NUMBER", "+49 30 12345678")
    first = p.pseudonymize(entity)
    # Verify cache is populated
    cache_key = f"{entity.entity_type}:{entity.text}"
    assert cache_key in p._cache
    assert p._cache[cache_key] == first
    # Second call returns same value (from cache)
    second = p.pseudonymize(entity)
    assert first == second


def test_apply_replaces_entity_in_text():
    p = Pseudonymizer(doc_key="apply-key")
    text = "Bitte kontaktiere Max Müller direkt."
    entity = _make_entity("PERSON", "Max Müller", start=19)
    result_text, mappings = p.apply(text, [entity])
    assert "Max Müller" not in result_text
    assert "PERSON-" in result_text


def test_apply_returns_mapping_records():
    p = Pseudonymizer(doc_key="mapping-key")
    text = "Schreib an anna@example.de."
    entity = _make_entity("EMAIL_ADDRESS", "anna@example.de", start=10)
    result_text, mappings = p.apply(text, [entity])
    assert len(mappings) == 1
    record = mappings[0]
    assert isinstance(record, MappingRecord)
    assert record.original_value == "anna@example.de"
    assert record.entity_type == "EMAIL_ADDRESS"
    assert record.pseudonym.startswith("EMAIL_ADDRESS-")


def test_apply_multiple_entities():
    p = Pseudonymizer(doc_key="multi-key")
    text = "Max Müller (max@example.de) wohnt in Berlin."
    entities = [
        _make_entity("PERSON", "Max Müller", start=0),
        _make_entity("EMAIL_ADDRESS", "max@example.de", start=12),
        _make_entity("LOCATION", "Berlin", start=36),
    ]
    result_text, mappings = p.apply(text, entities)
    assert "Max Müller" not in result_text
    assert "max@example.de" not in result_text
    assert "Berlin" not in result_text
    assert len(mappings) == 3


def test_apply_deduplicates_repeated_entity():
    p = Pseudonymizer(doc_key="dedup-key")
    # Same text appears twice → same pseudonym, only one mapping record
    text = "Max ruft Max zurück."
    entities = [
        _make_entity("PERSON", "Max", start=0),
        _make_entity("PERSON", "Max", start=10),
    ]
    result_text, mappings = p.apply(text, entities)
    assert "Max" not in result_text
    # Only one unique mapping record (same pseudonym)
    assert len(mappings) == 1


def test_apply_empty_entities():
    p = Pseudonymizer(doc_key="empty-key")
    text = "Kein PII hier."
    result_text, mappings = p.apply(text, [])
    assert result_text == text
    assert mappings == []


def test_apply_preserves_text_outside_entities():
    p = Pseudonymizer(doc_key="preserve-key")
    text = "Hallo Max Müller, willkommen!"
    entity = _make_entity("PERSON", "Max Müller", start=6)
    result_text, _ = p.apply(text, [entity])
    assert result_text.startswith("Hallo ")
    assert result_text.endswith(", willkommen!")
