import os
import pytest
import pytest_asyncio
from sqlalchemy import text

try:
    import spacy

    spacy.load("de_core_news_lg")
    HAS_SPACY = True
except (ImportError, OSError):
    HAS_SPACY = False

SKIP_MSG = "spaCy de_core_news_lg not installed"


@pytest_asyncio.fixture
async def db_session(tmp_path):
    from app.core.database import create_engine_and_tables
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    db_url = f"sqlite+aiosqlite:///{tmp_path}/db/test.db"
    os.makedirs(f"{tmp_path}/db", exist_ok=True)
    engine = await create_engine_and_tables(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def doc_service(tmp_path):
    from app.services.document_service import DocumentService

    upload_dir = str(tmp_path / "uploads")
    output_dir = str(tmp_path / "outputs")
    return DocumentService(upload_dir=upload_dir, output_dir=output_dir)


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
async def test_create_document(db_session, doc_service, tmp_path):
    # Create a test file
    file_path = str(tmp_path / "uploads" / "test.txt")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("Max Müller wohnt in Berlin.\n")

    doc_id = await doc_service.create_document(
        db=db_session,
        file_path=file_path,
        filename="test.txt",
        input_format="txt",
        mode="balanced",
        actor_id="test-actor",
    )

    assert doc_id is not None
    assert len(doc_id) > 0

    # Verify DB record
    row = (
        await db_session.execute(
            text("SELECT * FROM documents WHERE id = :id"), {"id": doc_id}
        )
    ).fetchone()

    assert row is not None
    assert row.status == "processing"
    assert row.actor_id == "test-actor"
    assert row.filename == "test.txt"
    assert row.input_format == "txt"
    assert row.output_format == "txt"
    assert row.mode == "balanced"
    assert row.entity_count == 0
    assert row.download_count == 0


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
async def test_process_document(db_session, doc_service, tmp_path):
    # Create a test file with PII
    file_path = str(tmp_path / "uploads" / "pii.txt")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("Max Müller wohnt in Berlin.\n")
        f.write("Seine Email ist max.mueller@beispiel.de.\n")

    doc_id = await doc_service.create_document(
        db=db_session,
        file_path=file_path,
        filename="pii.txt",
        input_format="txt",
        mode="balanced",
        actor_id="test-actor",
    )

    secret_key = "test-secret-key-for-encryption"
    await doc_service.process_document(db_session, doc_id, secret_key)

    # Verify status is ready
    row = (
        await db_session.execute(
            text("SELECT * FROM documents WHERE id = :id"), {"id": doc_id}
        )
    ).fetchone()

    assert row.status == "ready"
    assert row.entity_count > 0
    assert row.output_path != ""
    assert os.path.exists(row.output_path)

    # Verify output file does NOT contain original PII
    with open(row.output_path, encoding="utf-8") as f:
        output_text = f.read()
    assert "Max Müller" not in output_text

    # Verify mappings are stored and encrypted
    mappings = (
        await db_session.execute(
            text("SELECT * FROM mappings WHERE document_id = :doc_id"),
            {"doc_id": doc_id},
        )
    ).fetchall()

    assert len(mappings) > 0
    for m in mappings:
        # original_value should be encrypted (base64), not plaintext
        assert m.original_value != "Max Müller"
        assert m.original_value != "max.mueller@beispiel.de"
        assert m.pseudonym.count("-") >= 1  # Format: TYPE-HASH


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_SPACY, reason=SKIP_MSG)
async def test_process_document_failure(db_session, doc_service, tmp_path):
    """Processing a non-existent file should set status to 'failed'."""
    file_path = str(tmp_path / "uploads" / "nonexistent.txt")

    doc_id = await doc_service.create_document(
        db=db_session,
        file_path=file_path,
        filename="nonexistent.txt",
        input_format="txt",
        mode="balanced",
        actor_id="test-actor",
    )

    await doc_service.process_document(db_session, doc_id, "some-key")

    row = (
        await db_session.execute(
            text("SELECT status FROM documents WHERE id = :id"), {"id": doc_id}
        )
    ).fetchone()

    assert row.status == "failed"
