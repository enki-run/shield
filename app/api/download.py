import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.services.token_service import TokenService

router = APIRouter(tags=["download"])

MEDIA_TYPES = {
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
}


@router.get("/dl/{token}")
async def public_download(token: str, db: AsyncSession = Depends(get_session)):
    settings = get_settings()
    service = TokenService(base_url="", token_ttl_minutes=settings.token_ttl_minutes)
    try:
        file_path, document_id = await service.consume_token(db, token)
    except ValueError:
        raise HTTPException(403, "Token invalid, expired, or already consumed")
    if not os.path.exists(file_path):
        raise HTTPException(404, "File not found")

    # Get original filename for download name
    row = (await db.execute(
        sql_text("SELECT filename, output_format FROM documents WHERE id = :id"),
        {"id": document_id},
    )).fetchone()

    ext = os.path.splitext(file_path)[1].lower()
    if row:
        stem = Path(row.filename).stem
        download_name = f"{stem}-shielded{ext}"
    else:
        download_name = f"shielded{ext}"

    return FileResponse(
        file_path,
        media_type=MEDIA_TYPES.get(ext, "application/octet-stream"),
        filename=download_name,
    )
