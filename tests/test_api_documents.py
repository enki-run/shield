import asyncio
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import close_db, init_db

# spaCy guard
try:
    import spacy

    spacy.load("de_core_news_lg")
    HAS_SPACY = True
except Exception:
    HAS_SPACY = False

pytestmark = pytest.mark.skipif(
    not HAS_SPACY, reason="spaCy model de_core_news_lg not installed"
)


async def _wait_for_ready(client, doc_id, timeout=15):
    """Poll until document is ready or timeout."""
    for _ in range(timeout * 10):
        resp = await client.get(f"/api/v1/documents/{doc_id}")
        if resp.status_code == 200:
            data = resp.json()
            if data["status"] in ("ready", "failed"):
                return data
        await asyncio.sleep(0.1)
    return None


@pytest.mark.asyncio
async def test_upload_txt(setup_test_dirs):
    from app.core.config import get_settings

    settings = get_settings()
    await init_db(settings.db_url)

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/documents",
            files={
                "file": ("test.txt", b"Max Mustermann lebt in Berlin.", "text/plain")
            },
            data={"mode": "balanced"},
        )
    assert response.status_code == 202
    data = response.json()
    assert "id" in data
    assert data["status"] == "processing"
    await close_db()


@pytest.mark.asyncio
async def test_upload_unsupported_format(setup_test_dirs):
    from app.core.config import get_settings

    settings = get_settings()
    await init_db(settings.db_url)

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/documents",
            files={
                "file": ("test.exe", b"binary stuff", "application/octet-stream")
            },
            data={"mode": "balanced"},
        )
    assert response.status_code == 400
    await close_db()


@pytest.mark.asyncio
async def test_list_documents(setup_test_dirs):
    from app.core.config import get_settings

    settings = get_settings()
    await init_db(settings.db_url)

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Upload a file
        await client.post(
            "/api/v1/documents",
            files={"file": ("test.txt", b"Hallo Welt", "text/plain")},
            data={"mode": "balanced"},
        )

        # List
        response = await client.get("/api/v1/documents")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["filename"] == "test.txt"
    await close_db()


@pytest.mark.asyncio
async def test_get_document_detail(setup_test_dirs):
    from app.core.config import get_settings

    settings = get_settings()
    await init_db(settings.db_url)

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Upload a file with PII
        resp = await client.post(
            "/api/v1/documents",
            files={
                "file": (
                    "pii.txt",
                    "Dr. Hans Mueller arbeitet bei der Deutschen Bank in Frankfurt.".encode(),
                    "text/plain",
                )
            },
            data={"mode": "balanced"},
        )
        doc_id = resp.json()["id"]

        # Wait for processing
        detail = await _wait_for_ready(client, doc_id)

    assert detail is not None
    assert detail["status"] == "ready"
    assert detail["entity_count"] > 0
    assert "mappings" in detail
    # Verify mappings have decrypted original values (plain text, not base64)
    for m in detail["mappings"]:
        assert "pseudonym" in m
        assert "original_value" in m
        assert "entity_type" in m
        # Decrypted values should be readable text, not base64
        assert not m["original_value"].startswith("gA")
    await close_db()


@pytest.mark.asyncio
async def test_get_mapping_csv(setup_test_dirs):
    from app.core.config import get_settings

    settings = get_settings()
    await init_db(settings.db_url)

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Upload
        resp = await client.post(
            "/api/v1/documents",
            files={
                "file": (
                    "csv_test.txt",
                    "Maria Schmidt wohnt in Hamburg.".encode(),
                    "text/plain",
                )
            },
            data={"mode": "balanced"},
        )
        doc_id = resp.json()["id"]

        # Wait for processing
        await _wait_for_ready(client, doc_id)

        # Get CSV
        csv_resp = await client.get(f"/api/v1/documents/{doc_id}/mapping.csv")

    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    content = csv_resp.text
    assert "pseudonym" in content
    assert "original_value" in content
    assert "entity_type" in content
    # CSV should contain actual values, not encrypted blobs
    lines = content.strip().split("\n")
    assert len(lines) >= 2  # header + at least one mapping row
    await close_db()


@pytest.mark.asyncio
async def test_get_document_not_found(setup_test_dirs):
    from app.core.config import get_settings

    settings = get_settings()
    await init_db(settings.db_url)

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/documents/nonexistent-id")
    assert response.status_code == 404
    await close_db()
