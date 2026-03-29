import os
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.token_service import TokenService


@pytest_asyncio.fixture
async def db_session(tmp_path):
    from app.core.database import create_engine_and_tables

    db_url = f"sqlite+aiosqlite:///{tmp_path}/db/test.db"
    os.makedirs(f"{tmp_path}/db", exist_ok=True)
    engine = await create_engine_and_tables(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def token_service():
    return TokenService(base_url="https://shield.example.com", token_ttl_minutes=30)


async def _insert_test_document(
    db: AsyncSession,
    doc_id: str = "test-doc-001",
    actor_id: str = "actor-1",
    status: str = "ready",
    download_count: int = 0,
    max_downloads: int = 50,
    output_path: str = "/tmp/output.txt",
) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=14)
    await db.execute(
        text(
            """
            INSERT INTO documents
                (id, actor_id, filename, input_format, output_format, mode,
                 status, entity_count, pii_report, download_count, max_downloads,
                 input_path, output_path, created_at, expires_at)
            VALUES
                (:id, :actor_id, 'test.txt', 'txt', 'txt', 'balanced',
                 :status, 5, '[]', :download_count, :max_downloads,
                 '/tmp/input.txt', :output_path, :created_at, :expires_at)
            """
        ),
        {
            "id": doc_id,
            "actor_id": actor_id,
            "status": status,
            "download_count": download_count,
            "max_downloads": max_downloads,
            "output_path": output_path,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        },
    )
    await db.commit()
    return doc_id


@pytest.mark.asyncio
async def test_create_token(db_session, token_service):
    await _insert_test_document(db_session)

    result = token_service.create_token(db_session, "test-doc-001", "actor-1")
    result = await result

    assert "url" in result
    assert result["url"].startswith("https://shield.example.com/dl/")
    assert "expires_at" in result
    assert result["ttl_seconds"] == 30 * 60


@pytest.mark.asyncio
async def test_cannot_create_second_active_token(db_session, token_service):
    await _insert_test_document(db_session)

    await token_service.create_token(db_session, "test-doc-001", "actor-1")

    with pytest.raises(ValueError, match="active download token already exists"):
        await token_service.create_token(db_session, "test-doc-001", "actor-1")


@pytest.mark.asyncio
async def test_create_token_wrong_actor(db_session, token_service):
    await _insert_test_document(db_session, actor_id="actor-1")

    with pytest.raises(ValueError, match="does not belong"):
        await token_service.create_token(db_session, "test-doc-001", "actor-wrong")


@pytest.mark.asyncio
async def test_create_token_not_ready(db_session, token_service):
    await _insert_test_document(db_session, status="processing")

    with pytest.raises(ValueError, match="not ready"):
        await token_service.create_token(db_session, "test-doc-001", "actor-1")


@pytest.mark.asyncio
async def test_consume_token(db_session, token_service):
    await _insert_test_document(db_session)

    result = await token_service.create_token(db_session, "test-doc-001", "actor-1")

    # Extract raw token from URL
    raw_token = result["url"].split("/")[-1]

    output_path, document_id = await token_service.consume_token(db_session, raw_token)
    assert output_path == "/tmp/output.txt"
    assert document_id == "test-doc-001"

    # Verify download count incremented
    row = (
        await db_session.execute(
            text("SELECT download_count FROM documents WHERE id = 'test-doc-001'")
        )
    ).fetchone()
    assert row.download_count == 1


@pytest.mark.asyncio
async def test_consume_token_twice_fails(db_session, token_service):
    await _insert_test_document(db_session)

    result = await token_service.create_token(db_session, "test-doc-001", "actor-1")
    raw_token = result["url"].split("/")[-1]

    await token_service.consume_token(db_session, raw_token)

    with pytest.raises(ValueError, match="already been used"):
        await token_service.consume_token(db_session, raw_token)


@pytest.mark.asyncio
async def test_consume_invalid_token(db_session, token_service):
    with pytest.raises(ValueError, match="Invalid"):
        await token_service.consume_token(db_session, "nonexistent-token")


@pytest.mark.asyncio
async def test_nuke_at_max_downloads(db_session, token_service):
    await _insert_test_document(
        db_session, download_count=49, max_downloads=50
    )

    result = await token_service.create_token(db_session, "test-doc-001", "actor-1")
    raw_token = result["url"].split("/")[-1]

    await token_service.consume_token(db_session, raw_token)

    # Verify document is nuked
    row = (
        await db_session.execute(
            text("SELECT status, nuked_at FROM documents WHERE id = 'test-doc-001'")
        )
    ).fetchone()
    assert row.status == "nuked"
    assert row.nuked_at is not None


@pytest.mark.asyncio
async def test_revoke_token(db_session, token_service):
    await _insert_test_document(db_session)

    await token_service.create_token(db_session, "test-doc-001", "actor-1")

    revoked = await token_service.revoke_token(db_session, "test-doc-001", "actor-1")
    assert revoked == 1

    # Verify no active tokens remain
    status = await token_service.get_active_token_status(db_session, "test-doc-001")
    assert status["has_active_token"] is False


@pytest.mark.asyncio
async def test_get_active_token_status_active(db_session, token_service):
    await _insert_test_document(db_session)

    await token_service.create_token(db_session, "test-doc-001", "actor-1")

    status = await token_service.get_active_token_status(db_session, "test-doc-001")
    assert status["has_active_token"] is True
    assert "expires_at" in status
    assert status["ttl_seconds"] > 0


@pytest.mark.asyncio
async def test_get_active_token_status_none(db_session, token_service):
    await _insert_test_document(db_session)

    status = await token_service.get_active_token_status(db_session, "test-doc-001")
    assert status["has_active_token"] is False
