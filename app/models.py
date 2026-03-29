from enum import Enum
from pydantic import BaseModel


class PiiMode(str, Enum):
    BALANCED = "balanced"
    COMPLIANT = "compliant"


class DocumentStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    NUKED = "nuked"
    EXPIRED = "expired"


class DocumentCreate(BaseModel):
    filename: str
    mode: PiiMode = PiiMode.BALANCED


class PiiReportEntry(BaseModel):
    entity_type: str
    count: int


class DocumentResponse(BaseModel):
    id: str
    filename: str
    input_format: str
    output_format: str
    mode: PiiMode
    status: DocumentStatus
    entity_count: int
    pii_report: list[PiiReportEntry]
    download_count: int
    max_downloads: int
    created_at: str
    expires_at: str
    nuked_at: str | None = None


class MappingEntry(BaseModel):
    pseudonym: str
    original_value: str
    entity_type: str


class DocumentDetail(DocumentResponse):
    mappings: list[MappingEntry]


class TokenResponse(BaseModel):
    url: str
    expires_at: str
    ttl_seconds: int


class TokenStatus(BaseModel):
    has_active_token: bool
    url: str | None = None
    expires_at: str | None = None
    ttl_seconds: int | None = None
