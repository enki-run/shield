import os
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class CleanupService:
    def __init__(self, nuke_ttl_hours: int = 72):
        self.nuke_ttl_hours = nuke_ttl_hours

    async def cleanup(self, db: AsyncSession) -> int:
        now = datetime.now(timezone.utc)
        nuke_cutoff = (now - timedelta(hours=self.nuke_ttl_hours)).isoformat()

        # Find documents that are expired or nuked past the TTL
        rows = (
            await db.execute(
                text(
                    """
                    SELECT id, input_path, output_path FROM documents
                    WHERE (expires_at < :now)
                       OR (status = 'nuked' AND nuked_at IS NOT NULL
                           AND nuked_at < :nuke_cutoff)
                    """
                ),
                {"now": now.isoformat(), "nuke_cutoff": nuke_cutoff},
            )
        ).fetchall()

        deleted = 0
        for row in rows:
            # Remove files from disk
            for path in [row.input_path, row.output_path]:
                if path and os.path.exists(path):
                    os.remove(path)

            # Remove related DB records
            await db.execute(
                text("DELETE FROM mappings WHERE document_id = :id"),
                {"id": row.id},
            )
            await db.execute(
                text("DELETE FROM download_tokens WHERE document_id = :id"),
                {"id": row.id},
            )
            await db.execute(
                text("DELETE FROM documents WHERE id = :id"),
                {"id": row.id},
            )
            deleted += 1

        if deleted > 0:
            await db.commit()
            logger.info("cleanup.deleted_documents", count=deleted)

        # Expire stale active tokens
        await db.execute(
            text(
                "UPDATE download_tokens SET status='expired' "
                "WHERE status='active' AND expires_at < :now"
            ),
            {"now": now.isoformat()},
        )
        await db.commit()

        return deleted
