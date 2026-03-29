import pytest
from pydantic import ValidationError
from app.models import (
    PiiMode,
    DocumentStatus,
    DocumentCreate,
    PiiReportEntry,
    DocumentResponse,
    MappingEntry,
    DocumentDetail,
    TokenResponse,
    TokenStatus,
)


def test_pii_mode_values():
    assert PiiMode.BALANCED == "balanced"
    assert PiiMode.COMPLIANT == "compliant"


def test_document_status_values():
    assert DocumentStatus.PROCESSING == "processing"
    assert DocumentStatus.READY == "ready"
    assert DocumentStatus.FAILED == "failed"
    assert DocumentStatus.NUKED == "nuked"
    assert DocumentStatus.EXPIRED == "expired"


def test_document_create_defaults():
    doc = DocumentCreate(filename="test.pdf")
    assert doc.filename == "test.pdf"
    assert doc.mode == PiiMode.BALANCED


def test_document_create_compliant():
    doc = DocumentCreate(filename="test.pdf", mode="compliant")
    assert doc.mode == PiiMode.COMPLIANT


def test_document_create_invalid_mode():
    with pytest.raises(ValidationError):
        DocumentCreate(filename="test.pdf", mode="invalid")


def test_pii_report_entry():
    entry = PiiReportEntry(entity_type="PERSON", count=5)
    assert entry.entity_type == "PERSON"
    assert entry.count == 5


def test_document_response():
    doc = DocumentResponse(
        id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        filename="contract.pdf",
        input_format="pdf",
        output_format="pdf",
        mode=PiiMode.BALANCED,
        status=DocumentStatus.READY,
        entity_count=10,
        pii_report=[PiiReportEntry(entity_type="PERSON", count=3)],
        download_count=2,
        max_downloads=50,
        created_at="2024-01-01T00:00:00Z",
        expires_at="2024-01-15T00:00:00Z",
    )
    assert doc.nuked_at is None
    assert len(doc.pii_report) == 1


def test_document_response_with_nuked_at():
    doc = DocumentResponse(
        id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        filename="contract.pdf",
        input_format="pdf",
        output_format="pdf",
        mode=PiiMode.BALANCED,
        status=DocumentStatus.NUKED,
        entity_count=0,
        pii_report=[],
        download_count=0,
        max_downloads=50,
        created_at="2024-01-01T00:00:00Z",
        expires_at="2024-01-15T00:00:00Z",
        nuked_at="2024-01-02T00:00:00Z",
    )
    assert doc.nuked_at == "2024-01-02T00:00:00Z"


def test_mapping_entry():
    entry = MappingEntry(
        pseudonym="Person-1",
        original_value="John Doe",
        entity_type="PERSON",
    )
    assert entry.pseudonym == "Person-1"
    assert entry.original_value == "John Doe"
    assert entry.entity_type == "PERSON"


def test_document_detail_with_mappings():
    detail = DocumentDetail(
        id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        filename="contract.pdf",
        input_format="pdf",
        output_format="pdf",
        mode=PiiMode.BALANCED,
        status=DocumentStatus.READY,
        entity_count=2,
        pii_report=[],
        download_count=0,
        max_downloads=50,
        created_at="2024-01-01T00:00:00Z",
        expires_at="2024-01-15T00:00:00Z",
        mappings=[
            MappingEntry(pseudonym="Person-1", original_value="Jane Smith", entity_type="PERSON"),
            MappingEntry(pseudonym="Email-1", original_value="jane@example.com", entity_type="EMAIL_ADDRESS"),
        ],
    )
    assert len(detail.mappings) == 2


def test_token_response():
    token = TokenResponse(
        url="https://example.com/download/abc123",
        expires_at="2024-01-01T00:30:00Z",
        ttl_seconds=1800,
    )
    assert token.ttl_seconds == 1800


def test_token_status_no_token():
    status = TokenStatus(has_active_token=False)
    assert status.has_active_token is False
    assert status.url is None
    assert status.expires_at is None
    assert status.ttl_seconds is None


def test_token_status_with_token():
    status = TokenStatus(
        has_active_token=True,
        url="https://example.com/download/abc123",
        expires_at="2024-01-01T00:30:00Z",
        ttl_seconds=1800,
    )
    assert status.has_active_token is True
    assert status.url is not None
