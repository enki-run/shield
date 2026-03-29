import os
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.cleanup_service import CleanupService


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
def cleanup_service():
    return CleanupService(nuke_ttl_hours=72)


async def _insert_document(
    db: AsyncSession,
    doc_id: str,
    status: str = "ready",
    expires_at: str | None = None,
    nuked_at: str | None = None,
    input_path: str = "",
    output_path: str = "",
) -> None:
    now = datetime.now(timezone.utc)
    if expires_at is None:
        expires_at = (now + timedelta(days=14)).isoformat()
    await db.execute(
        text(
            """
            INSERT INTO documents
                (id, actor_id, filename, input_format, output_format, mode,
                 status, entity_count, pii_report, download_count, max_downloads,
                 input_path, output_path, created_at, expires_at, nuked_at)
            VALUES
                (:id, 'actor-1', 'test.txt', 'txt', 'txt', 'balanced',
                 :status, 0, '[]', 0, 50,
                 :input_path, :output_path, :created_at, :expires_at, :nuked_at)
            """
        ),
        {
            "id": doc_id,
            "status": status,
            "input_path": input_path,
            "output_path": output_path,
            "created_at": now.isoformat(),
            "expires_at": expires_at,
            "nuked_at": nuked_at,
        },
    )
    await db.commit()


@pytest.mark.asyncio
async def test_cleanup_expired_document(db_session, cleanup_service, tmp_path):
    # Create files
    input_file = str(tmp_path / "input.txt")
    output_file = str(tmp_path / "output.txt")
    with open(input_file, "w") as f:
        f.write("test input")
    with open(output_file, "w") as f:
        f.write("test output")

    # Insert expired document
    expired_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    await _insert_document(
        db_session,
        doc_id="expired-doc",
        status="ready",
        expires_at=expired_at,
        input_path=input_file,
        output_path=output_file,
    )

    deleted = await cleanup_service.cleanup(db_session)
    assert deleted == 1

    # Verify document is gone from DB
    row = (
        await db_session.execute(
            text("SELECT id FROM documents WHERE id = 'expired-doc'")
        )
    ).fetchone()
    assert row is None

    # Verify files removed
    assert not os.path.exists(input_file)
    assert not os.path.exists(output_file)


@pytest.mark.asyncio
async def test_cleanup_nuked_past_ttl(db_session, cleanup_service, tmp_path):
    # Nuked 4 days ago (past 72h TTL)
    nuked_at = (datetime.now(timezone.utc) - timedelta(hours=80)).isoformat()
    await _insert_document(
        db_session,
        doc_id="nuked-doc",
        status="nuked",
        nuked_at=nuked_at,
    )

    deleted = await cleanup_service.cleanup(db_session)
    assert deleted == 1

    row = (
        await db_session.execute(
            text("SELECT id FROM documents WHERE id = 'nuked-doc'")
        )
    ).fetchone()
    assert row is None


@pytest.mark.asyncio
async def test_cleanup_does_not_delete_active(db_session, cleanup_service):
    # Active document: not expired, not nuked
    await _insert_document(
        db_session,
        doc_id="active-doc",
        status="ready",
    )

    deleted = await cleanup_service.cleanup(db_session)
    assert deleted == 0

    row = (
        await db_session.execute(
            text("SELECT id FROM documents WHERE id = 'active-doc'")
        )
    ).fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_cleanup_nuked_within_ttl_not_deleted(db_session, cleanup_service):
    # Nuked 1 hour ago (within 72h TTL), not expired
    nuked_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    await _insert_document(
        db_session,
        doc_id="recent-nuked",
        status="nuked",
        nuked_at=nuked_at,
    )

    deleted = await cleanup_service.cleanup(db_session)
    assert deleted == 0

    row = (
        await db_session.execute(
            text("SELECT id FROM documents WHERE id = 'recent-nuked'")
        )
    ).fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_cleanup_expires_stale_tokens(db_session, cleanup_service):
    # Insert a document first (for FK)
    await _insert_document(db_session, doc_id="token-doc", status="ready")

    # Insert an expired active token
    expired_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    await db_session.execute(
        text(
            """
            INSERT INTO download_tokens
                (id, document_id, token_hash, status, created_at, expires_at)
            VALUES
                ('tok-1', 'token-doc', 'hash123', 'active', :created, :expires)
            """
        ),
        {
            "created": datetime.now(timezone.utc).isoformat(),
            "expires": expired_at,
        },
    )
    await db_session.commit()

    await cleanup_service.cleanup(db_session)

    row = (
        await db_session.execute(
            text("SELECT status FROM download_tokens WHERE id = 'tok-1'")
        )
    ).fetchone()
    assert row.status == "expired"


@pytest.mark.asyncio
async def test_cleanup_deletes_related_mappings_and_tokens(
    db_session, cleanup_service
):
    expired_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    await _insert_document(
        db_session,
        doc_id="full-cleanup-doc",
        status="ready",
        expires_at=expired_at,
    )

    # Insert mapping
    now = datetime.now(timezone.utc).isoformat()
    await db_session.execute(
        text(
            "INSERT INTO mappings (id, document_id, pseudonym, original_value, entity_type, created_at) "
            "VALUES ('map-1', 'full-cleanup-doc', 'PERSON-ABCD', 'encrypted', 'PERSON', :now)"
        ),
        {"now": now},
    )
    # Insert token
    await db_session.execute(
        text(
            "INSERT INTO download_tokens (id, document_id, token_hash, status, created_at, expires_at) "
            "VALUES ('tok-2', 'full-cleanup-doc', 'hash456', 'consumed', :now, :now)"
        ),
        {"now": now},
    )
    await db_session.commit()

    deleted = await cleanup_service.cleanup(db_session)
    assert deleted == 1

    # Verify all related records gone
    for table, col in [("documents", "id"), ("mappings", "document_id"), ("download_tokens", "document_id")]:
        row = (
            await db_session.execute(
                text(f"SELECT COUNT(*) as cnt FROM {table} WHERE {col} = 'full-cleanup-doc'")
            )
        ).fetchone()
        assert row.cnt == 0
