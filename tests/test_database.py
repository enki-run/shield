import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.database import create_engine_and_tables, init_db, close_db, get_session_factory


@pytest.mark.asyncio
async def test_tables_created(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = await create_engine_and_tables(db_url)

    async with engine.connect() as conn:
        # Check documents table
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'")
        )
        assert result.fetchone() is not None, "documents table should exist"

        # Check mappings table
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='mappings'")
        )
        assert result.fetchone() is not None, "mappings table should exist"

        # Check download_tokens table
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='download_tokens'")
        )
        assert result.fetchone() is not None, "download_tokens table should exist"

    await engine.dispose()


@pytest.mark.asyncio
async def test_indexes_created(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test_idx.db"
    engine = await create_engine_and_tables(db_url)

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index'")
        )
        indexes = {row[0] for row in result.fetchall()}

    assert "idx_mappings_document_id" in indexes
    assert "idx_download_tokens_hash" in indexes
    assert "idx_download_tokens_document_id" in indexes

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_db_creates_session_factory(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test_session.db"
    await init_db(db_url)

    factory = get_session_factory()
    assert factory is not None

    await close_db()


@pytest.mark.asyncio
async def test_schema_is_idempotent(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test_idem.db"
    # Run twice — should not raise
    engine = await create_engine_and_tables(db_url)
    await engine.dispose()
    engine = await create_engine_and_tables(db_url)
    await engine.dispose()


@pytest.mark.asyncio
async def test_documents_columns(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test_cols.db"
    engine = await create_engine_and_tables(db_url)

    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA table_info(documents)"))
        columns = {row[1] for row in result.fetchall()}

    expected = {
        "id", "actor_id", "filename", "input_format", "output_format",
        "mode", "status", "entity_count", "pii_report", "download_count",
        "max_downloads", "input_path", "output_path", "created_at", "expires_at", "nuked_at"
    }
    assert expected.issubset(columns)

    await engine.dispose()
