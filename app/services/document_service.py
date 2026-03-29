import json
import os
import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone

import structlog
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.core.crypto import encrypt_value
from app.pipeline.detector import PiiDetector
from app.pipeline.parsers import get_parser
from app.pipeline.pseudonymizer import Pseudonymizer

logger = structlog.get_logger()

OUTPUT_FORMATS = {"pdf": "md"}


class DocumentService:
    def __init__(self, upload_dir: str, output_dir: str):
        self.upload_dir = upload_dir
        self.output_dir = output_dir
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

    async def create_document(
        self,
        db: AsyncSession,
        file_path: str,
        filename: str,
        input_format: str,
        mode: str,
        actor_id: str,
        document_ttl_days: int = 14,
        max_downloads: int = 50,
    ) -> str:
        doc_id = str(ULID())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=document_ttl_days)
        output_format = OUTPUT_FORMATS.get(input_format, input_format)

        await db.execute(
            text(
                """
                INSERT INTO documents
                    (id, actor_id, filename, input_format, output_format, mode,
                     status, entity_count, pii_report, download_count, max_downloads,
                     input_path, output_path, created_at, expires_at)
                VALUES
                    (:id, :actor_id, :filename, :input_format, :output_format, :mode,
                     'processing', 0, '[]', 0, :max_downloads,
                     :input_path, '', :created_at, :expires_at)
                """
            ),
            {
                "id": doc_id,
                "actor_id": actor_id,
                "filename": filename,
                "input_format": input_format,
                "output_format": output_format,
                "mode": mode,
                "max_downloads": max_downloads,
                "input_path": file_path,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
        )
        await db.commit()

        logger.info(
            "document.created",
            document_id=doc_id,
            actor_id=actor_id,
            format=input_format,
            mode=mode,
        )
        return doc_id

    def _process_sync(
        self,
        file_path: str,
        input_format: str,
        mode: str,
        output_path: str,
    ) -> dict:
        parser = get_parser(input_format)
        parsed = parser.parse(file_path)

        detector = PiiDetector(mode=mode)
        doc_key = secrets.token_hex(32)
        pseudonymizer = Pseudonymizer(doc_key=doc_key)

        all_mappings: dict[str, object] = {}
        replacements: dict[str, str] = {}
        entity_counter: Counter = Counter()
        recognizer_counter: Counter = Counter()
        confidence_values: list[float] = []
        total_blocks = len(parsed.blocks)
        blocks_with_pii = 0

        for block in parsed.blocks:
            # Skip detection for header rows, numeric cells, etc.
            if block.metadata.get("skip_detection", False):
                continue
            entities = detector.detect(block.text)
            if entities:
                blocks_with_pii += 1
                new_text, block_mappings = pseudonymizer.apply(block.text, entities)
                block.text = new_text
                for m in block_mappings:
                    entity_counter[m.entity_type] += 1
                    if m.pseudonym not in all_mappings:
                        all_mappings[m.pseudonym] = m
                        replacements[m.original_value] = m.pseudonym
                for e in entities:
                    recognizer_counter[e.recognizer] += 1
                    confidence_values.append(e.confidence)

        parsed.metadata["replacements"] = replacements
        parsed.metadata["original_path"] = file_path

        output_format = OUTPUT_FORMATS.get(input_format, input_format)

        from app.pipeline.rebuilder import rebuild_document

        rebuild_document(parsed, output_path, output_format)

        pii_report = [
            {"entity_type": k, "count": v} for k, v in entity_counter.items()
        ]

        # Detection quality log — no PII values, only aggregated stats
        avg_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else 0
        )
        logger.info(
            "detection.quality",
            format=input_format,
            mode=mode,
            total_blocks=total_blocks,
            blocks_with_pii=blocks_with_pii,
            pii_coverage=round(blocks_with_pii / max(total_blocks, 1), 2),
            entity_count=sum(entity_counter.values()),
            unique_entities=len(all_mappings),
            entity_types=dict(entity_counter),
            recognizers=dict(recognizer_counter),
            avg_confidence=round(avg_confidence, 3),
            min_confidence=round(min(confidence_values), 3) if confidence_values else 0,
        )

        return {
            "entity_count": sum(entity_counter.values()),
            "pii_report": pii_report,
            "mappings": list(all_mappings.values()),
        }

    async def process_document(
        self,
        db: AsyncSession,
        doc_id: str,
        secret_key: str,
    ) -> None:
        row = (
            await db.execute(
                text(
                    "SELECT input_path, input_format, output_format, mode "
                    "FROM documents WHERE id = :id"
                ),
                {"id": doc_id},
            )
        ).fetchone()

        if row is None:
            return

        output_path = os.path.join(self.output_dir, f"{doc_id}.{row.output_format}")

        try:
            result = await run_in_threadpool(
                self._process_sync,
                row.input_path,
                row.input_format,
                row.mode,
                output_path,
            )

            now = datetime.now(timezone.utc)
            await db.execute(
                text(
                    "UPDATE documents "
                    "SET status='ready', entity_count=:count, "
                    "pii_report=:report, output_path=:path "
                    "WHERE id=:id"
                ),
                {
                    "id": doc_id,
                    "count": result["entity_count"],
                    "report": json.dumps(result["pii_report"]),
                    "path": output_path,
                },
            )

            for m in result["mappings"]:
                await db.execute(
                    text(
                        "INSERT INTO mappings "
                        "(id, document_id, pseudonym, original_value, entity_type, created_at) "
                        "VALUES (:id, :doc_id, :pseudo, :orig, :type, :created)"
                    ),
                    {
                        "id": str(ULID()),
                        "doc_id": doc_id,
                        "pseudo": m.pseudonym,
                        "orig": encrypt_value(m.original_value, secret_key),
                        "type": m.entity_type,
                        "created": now.isoformat(),
                    },
                )

            await db.commit()
            logger.info(
                "document.processed",
                document_id=doc_id,
                entity_count=result["entity_count"],
            )

        except Exception as e:
            logger.error("document.failed", document_id=doc_id, error=str(e))
            await db.execute(
                text("UPDATE documents SET status='failed' WHERE id=:id"),
                {"id": doc_id},
            )
            await db.commit()
