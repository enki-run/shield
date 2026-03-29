import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID


class TokenService:
    def __init__(self, base_url: str, token_ttl_minutes: int = 30):
        self.base_url = base_url.rstrip("/")
        self.token_ttl_minutes = token_ttl_minutes

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    async def create_token(
        self,
        db: AsyncSession,
        document_id: str,
        actor_id: str,
    ) -> dict:
        # Validate document exists, is ready, and belongs to actor
        doc = (
            await db.execute(
                text(
                    "SELECT id, status, actor_id FROM documents WHERE id = :id"
                ),
                {"id": document_id},
            )
        ).fetchone()

        if doc is None:
            raise ValueError("Document not found")
        if doc.status != "ready":
            raise ValueError(f"Document is not ready (status: {doc.status})")
        if doc.actor_id != actor_id:
            raise ValueError("Document does not belong to this actor")

        # Check no active token already exists
        existing = (
            await db.execute(
                text(
                    "SELECT id FROM download_tokens "
                    "WHERE document_id = :doc_id AND status = 'active' "
                    "AND expires_at > :now"
                ),
                {
                    "doc_id": document_id,
                    "now": datetime.now(timezone.utc).isoformat(),
                },
            )
        ).fetchone()

        if existing is not None:
            raise ValueError("An active download token already exists for this document")

        # Create token
        raw_token = secrets.token_urlsafe(32)
        token_hash = self._hash_token(raw_token)
        token_id = str(ULID())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.token_ttl_minutes)

        await db.execute(
            text(
                "INSERT INTO download_tokens "
                "(id, document_id, token_hash, status, created_at, expires_at) "
                "VALUES (:id, :doc_id, :hash, 'active', :created, :expires)"
            ),
            {
                "id": token_id,
                "doc_id": document_id,
                "hash": token_hash,
                "created": now.isoformat(),
                "expires": expires_at.isoformat(),
            },
        )
        await db.commit()

        url = f"{self.base_url}/dl/{raw_token}"
        ttl_seconds = int(self.token_ttl_minutes * 60)

        return {
            "url": url,
            "expires_at": expires_at.isoformat(),
            "ttl_seconds": ttl_seconds,
        }

    async def consume_token(
        self,
        db: AsyncSession,
        raw_token: str,
    ) -> tuple[str, str]:
        token_hash = self._hash_token(raw_token)
        now = datetime.now(timezone.utc)

        row = (
            await db.execute(
                text(
                    "SELECT dt.id, dt.document_id, dt.status, dt.expires_at, "
                    "d.output_path, d.download_count, d.max_downloads, d.status AS doc_status "
                    "FROM download_tokens dt "
                    "JOIN documents d ON d.id = dt.document_id "
                    "WHERE dt.token_hash = :hash"
                ),
                {"hash": token_hash},
            )
        ).fetchone()

        if row is None:
            raise ValueError("Invalid download token")
        if row.status != "active":
            raise ValueError("Token has already been used or expired")
        if row.expires_at < now.isoformat():
            raise ValueError("Token has expired")
        if row.doc_status == "nuked":
            raise ValueError("Document has been nuked")

        # Mark token as consumed
        await db.execute(
            text(
                "UPDATE download_tokens SET status='consumed' WHERE id = :id"
            ),
            {"id": row.id},
        )

        # Increment download count
        new_count = row.download_count + 1
        await db.execute(
            text(
                "UPDATE documents SET download_count = :count WHERE id = :doc_id"
            ),
            {"count": new_count, "doc_id": row.document_id},
        )

        # Nuke if at max downloads
        if new_count >= row.max_downloads:
            await db.execute(
                text(
                    "UPDATE documents SET status='nuked', nuked_at=:now "
                    "WHERE id = :doc_id"
                ),
                {"doc_id": row.document_id, "now": now.isoformat()},
            )

        await db.commit()

        return row.output_path, row.document_id

    async def revoke_token(
        self,
        db: AsyncSession,
        document_id: str,
        actor_id: str,
    ) -> int:
        # Verify ownership
        doc = (
            await db.execute(
                text("SELECT actor_id FROM documents WHERE id = :id"),
                {"id": document_id},
            )
        ).fetchone()

        if doc is None:
            raise ValueError("Document not found")
        if doc.actor_id != actor_id:
            raise ValueError("Document does not belong to this actor")

        result = await db.execute(
            text(
                "UPDATE download_tokens SET status='expired' "
                "WHERE document_id = :doc_id AND status = 'active'"
            ),
            {"doc_id": document_id},
        )
        await db.commit()
        return result.rowcount

    async def get_active_token_status(
        self,
        db: AsyncSession,
        document_id: str,
    ) -> dict:
        now = datetime.now(timezone.utc)

        row = (
            await db.execute(
                text(
                    "SELECT token_hash, expires_at FROM download_tokens "
                    "WHERE document_id = :doc_id AND status = 'active' "
                    "AND expires_at > :now "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"doc_id": document_id, "now": now.isoformat()},
            )
        ).fetchone()

        if row is None:
            return {"has_active_token": False}

        expires_at = datetime.fromisoformat(row.expires_at)
        ttl_seconds = max(0, int((expires_at - now).total_seconds()))

        return {
            "has_active_token": True,
            "expires_at": row.expires_at,
            "ttl_seconds": ttl_seconds,
        }
