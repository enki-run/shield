import asyncio
import csv
import io
import json
import os
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.crypto import decrypt_value
from app.core.database import get_session, get_session_factory
from app.models import (
    DocumentDetail,
    DocumentResponse,
    MappingEntry,
    PiiMode,
    PiiReportEntry,
)
from app.pipeline.parsers import FORMAT_EXTENSIONS
from app.services.document_service import DocumentService
from app.services.token_service import TokenService

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
_logger = structlog.get_logger()


def _get_document_service():
    settings = get_settings()
    return DocumentService(
        upload_dir=f"{settings.data_dir}/uploads",
        output_dir=f"{settings.data_dir}/outputs",
    )


def _get_token_service():
    settings = get_settings()
    base_url = os.getenv("SHIELD_BASE_URL", "http://localhost:8000")
    return TokenService(base_url=base_url, token_ttl_minutes=settings.token_ttl_minutes)


@router.post("", status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    mode: PiiMode = Form(PiiMode.BALANCED),
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    settings = get_settings()

    # Validate file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in FORMAT_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file format: {ext}. "
            f"Supported: {list(FORMAT_EXTENSIONS.keys())}",
        )
    input_format = FORMAT_EXTENSIONS[ext]

    # Read and validate size
    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            413, f"File too large. Maximum: {settings.max_upload_mb} MB"
        )

    # Save upload to disk
    upload_dir = f"{settings.data_dir}/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    from ulid import ULID

    file_id = str(ULID())
    file_path = os.path.join(upload_dir, f"{file_id}{ext}")
    with open(file_path, "wb") as f:
        f.write(content)

    # Create document record
    service = _get_document_service()
    doc_id = await service.create_document(
        db=db,
        file_path=file_path,
        filename=file.filename,
        input_format=input_format,
        mode=mode.value,
        actor_id=user["email"],
        document_ttl_days=settings.document_ttl_days,
        max_downloads=settings.max_downloads,
    )

    # Kick off background processing
    async def _bg_process():
        try:
            factory = get_session_factory()
            async with factory() as bg_db:
                await service.process_document(bg_db, doc_id, settings.secret_key)
        except Exception:
            _logger.exception("background_task.failed", document_id=doc_id)

    asyncio.create_task(_bg_process())

    return {"id": doc_id, "status": "processing"}


@router.get("")
async def list_documents(
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    rows = (
        await db.execute(
            text(
                "SELECT id, filename, input_format, output_format, mode, status, "
                "entity_count, pii_report, download_count, max_downloads, "
                "created_at, expires_at, nuked_at "
                "FROM documents WHERE actor_id = :actor_id "
                "ORDER BY created_at DESC"
            ),
            {"actor_id": user["email"]},
        )
    ).fetchall()

    result = []
    for row in rows:
        pii_report = json.loads(row.pii_report) if row.pii_report else []
        result.append(
            DocumentResponse(
                id=row.id,
                filename=row.filename,
                input_format=row.input_format,
                output_format=row.output_format,
                mode=row.mode,
                status=row.status,
                entity_count=row.entity_count,
                pii_report=[PiiReportEntry(**e) for e in pii_report],
                download_count=row.download_count,
                max_downloads=row.max_downloads,
                created_at=row.created_at,
                expires_at=row.expires_at,
                nuked_at=row.nuked_at,
            )
        )
    return result


@router.get("/{document_id}")
async def get_document_detail(
    document_id: str,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    settings = get_settings()

    row = (
        await db.execute(
            text(
                "SELECT id, filename, input_format, output_format, mode, status, "
                "entity_count, pii_report, download_count, max_downloads, "
                "created_at, expires_at, nuked_at "
                "FROM documents WHERE id = :id AND actor_id = :actor_id"
            ),
            {"id": document_id, "actor_id": user["email"]},
        )
    ).fetchone()

    if row is None:
        raise HTTPException(404, "Document not found")

    pii_report = json.loads(row.pii_report) if row.pii_report else []

    # Query mappings
    mappings_rows = (
        await db.execute(
            text(
                "SELECT pseudonym, original_value, entity_type "
                "FROM mappings WHERE document_id = :doc_id"
            ),
            {"doc_id": document_id},
        )
    ).fetchall()

    mappings = []
    for m in mappings_rows:
        mappings.append(
            MappingEntry(
                pseudonym=m.pseudonym,
                original_value=decrypt_value(m.original_value, settings.secret_key),
                entity_type=m.entity_type,
            )
        )

    return DocumentDetail(
        id=row.id,
        filename=row.filename,
        input_format=row.input_format,
        output_format=row.output_format,
        mode=row.mode,
        status=row.status,
        entity_count=row.entity_count,
        pii_report=[PiiReportEntry(**e) for e in pii_report],
        download_count=row.download_count,
        max_downloads=row.max_downloads,
        created_at=row.created_at,
        expires_at=row.expires_at,
        nuked_at=row.nuked_at,
        mappings=mappings,
    )


@router.get("/{document_id}/mapping.csv")
async def get_mapping_csv(
    document_id: str,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    settings = get_settings()

    # Verify ownership
    doc = (
        await db.execute(
            text(
                "SELECT id FROM documents WHERE id = :id AND actor_id = :actor_id"
            ),
            {"id": document_id, "actor_id": user["email"]},
        )
    ).fetchone()

    if doc is None:
        raise HTTPException(404, "Document not found")

    mappings_rows = (
        await db.execute(
            text(
                "SELECT pseudonym, original_value, entity_type "
                "FROM mappings WHERE document_id = :doc_id"
            ),
            {"doc_id": document_id},
        )
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["pseudonym", "original_value", "entity_type"])
    for m in mappings_rows:
        writer.writerow([
            m.pseudonym,
            decrypt_value(m.original_value, settings.secret_key),
            m.entity_type,
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{document_id}_mapping.csv"'
        },
    )


@router.post("/{document_id}/token", status_code=201)
async def create_download_token(
    document_id: str,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    service = _get_token_service()
    try:
        result = await service.create_token(db, document_id, user["email"])
    except ValueError as e:
        msg = str(e)
        if "already exists" in msg:
            raise HTTPException(409, msg)
        if "not found" in msg:
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)
    return result


@router.delete("/{document_id}/token")
async def revoke_download_token(
    document_id: str,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    service = _get_token_service()
    try:
        count = await service.revoke_token(db, document_id, user["email"])
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"revoked": count}


@router.get("/{document_id}/token/status")
async def get_token_status(
    document_id: str,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    service = _get_token_service()
    return await service.get_active_token_status(db, document_id)
