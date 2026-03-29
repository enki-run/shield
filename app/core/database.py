from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

_engine = None
_session_factory = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    input_format TEXT NOT NULL,
    output_format TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('balanced', 'compliant')),
    status TEXT NOT NULL DEFAULT 'processing' CHECK(status IN ('processing', 'ready', 'failed', 'nuked', 'expired')),
    entity_count INTEGER DEFAULT 0,
    pii_report TEXT DEFAULT '{}',
    download_count INTEGER DEFAULT 0,
    max_downloads INTEGER DEFAULT 50,
    input_path TEXT,
    output_path TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    nuked_at TEXT
);

CREATE TABLE IF NOT EXISTS mappings (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    pseudonym TEXT NOT NULL,
    original_value TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mappings_document_id ON mappings(document_id);

CREATE TABLE IF NOT EXISTS download_tokens (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'consumed', 'expired')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_download_tokens_hash ON download_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_download_tokens_document_id ON download_tokens(document_id);
"""


async def create_engine_and_tables(db_url: str):
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        for statement in SCHEMA.strip().split(";"):
            statement = statement.strip()
            if statement:
                await conn.execute(text(statement))
    return engine


async def init_db(db_url: str):
    global _engine, _session_factory
    _engine = await create_engine_and_tables(db_url)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with _session_factory() as session:
        yield session


def get_session_factory():
    return _session_factory


async def close_db():
    global _engine
    if _engine:
        await _engine.dispose()
