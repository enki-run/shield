import asyncio

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


async def _upload_and_wait(client, timeout=15):
    """Upload a document with PII and wait until it's ready. Returns doc_id."""
    resp = await client.post(
        "/api/v1/documents",
        files={
            "file": (
                "download_test.txt",
                "Max Mustermann lebt in Berlin und arbeitet bei SAP.".encode(),
                "text/plain",
            )
        },
        data={"mode": "balanced"},
    )
    doc_id = resp.json()["id"]

    # Wait for processing to complete
    for _ in range(timeout * 10):
        detail = await client.get(f"/api/v1/documents/{doc_id}")
        if detail.status_code == 200 and detail.json()["status"] in (
            "ready",
            "failed",
        ):
            break
        await asyncio.sleep(0.1)

    return doc_id


@pytest.mark.asyncio
async def test_create_download_token(setup_test_dirs):
    from app.core.config import get_settings

    settings = get_settings()
    await init_db(settings.db_url)

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        doc_id = await _upload_and_wait(client)

        resp = await client.post(f"/api/v1/documents/{doc_id}/token")

    assert resp.status_code == 201
    data = resp.json()
    assert "url" in data
    assert "expires_at" in data
    assert "ttl_seconds" in data
    assert "/dl/" in data["url"]
    await close_db()


@pytest.mark.asyncio
async def test_cannot_create_second_token(setup_test_dirs):
    from app.core.config import get_settings

    settings = get_settings()
    await init_db(settings.db_url)

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        doc_id = await _upload_and_wait(client)

        # First token
        resp1 = await client.post(f"/api/v1/documents/{doc_id}/token")
        assert resp1.status_code == 201

        # Second token should fail
        resp2 = await client.post(f"/api/v1/documents/{doc_id}/token")

    assert resp2.status_code == 409
    await close_db()


@pytest.mark.asyncio
async def test_public_download(setup_test_dirs):
    from app.core.config import get_settings

    settings = get_settings()
    await init_db(settings.db_url)

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        doc_id = await _upload_and_wait(client)

        # Create token
        token_resp = await client.post(f"/api/v1/documents/{doc_id}/token")
        url = token_resp.json()["url"]
        # Extract the path portion from the download URL
        token_path = "/dl/" + url.split("/dl/")[-1]

        # Download
        dl_resp = await client.get(token_path)

    assert dl_resp.status_code == 200
    assert len(dl_resp.content) > 0
    await close_db()


@pytest.mark.asyncio
async def test_consumed_token_fails(setup_test_dirs):
    from app.core.config import get_settings

    settings = get_settings()
    await init_db(settings.db_url)

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        doc_id = await _upload_and_wait(client)

        # Create and consume token
        token_resp = await client.post(f"/api/v1/documents/{doc_id}/token")
        url = token_resp.json()["url"]
        token_path = "/dl/" + url.split("/dl/")[-1]

        # First download succeeds
        dl1 = await client.get(token_path)
        assert dl1.status_code == 200

        # Second download fails (token consumed)
        dl2 = await client.get(token_path)

    assert dl2.status_code == 403
    await close_db()


@pytest.mark.asyncio
async def test_revoke_token(setup_test_dirs):
    from app.core.config import get_settings

    settings = get_settings()
    await init_db(settings.db_url)

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        doc_id = await _upload_and_wait(client)

        # Create first token
        resp1 = await client.post(f"/api/v1/documents/{doc_id}/token")
        assert resp1.status_code == 201

        # Revoke it
        revoke_resp = await client.delete(f"/api/v1/documents/{doc_id}/token")
        assert revoke_resp.status_code == 200

        # Now we can create a new one
        resp2 = await client.post(f"/api/v1/documents/{doc_id}/token")

    assert resp2.status_code == 201
    await close_db()


@pytest.mark.asyncio
async def test_token_status(setup_test_dirs):
    from app.core.config import get_settings

    settings = get_settings()
    await init_db(settings.db_url)

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        doc_id = await _upload_and_wait(client)

        # No token yet
        status_resp = await client.get(f"/api/v1/documents/{doc_id}/token/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["has_active_token"] is False

        # Create token
        await client.post(f"/api/v1/documents/{doc_id}/token")

        # Now has active token
        status_resp = await client.get(f"/api/v1/documents/{doc_id}/token/status")

    assert status_resp.json()["has_active_token"] is True
    await close_db()
