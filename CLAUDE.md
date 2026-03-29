# Shield — Document Pseudonymization Service

## Project Overview

Shield is an open-source document pseudonymization service. It detects PII in documents, replaces it with consistent pseudonyms, and provides secure download links. Mappings (pseudonym → original value) are AES-256-GCM encrypted.

## Tech Stack

- **Runtime:** Python 3.11+
- **Framework:** FastAPI (async)
- **Database:** SQLite via SQLAlchemy async + aiosqlite
- **PII Detection:** Microsoft Presidio + spaCy (de_core_news_lg)
- **Auth:** Cloudflare Access JWT middleware
- **Logging:** structlog (JSON in production, console in dev)
- **Testing:** pytest + pytest-asyncio + httpx

## Project Structure

```
app/
  core/
    config.py       — Settings (env-driven, lru_cache)
    database.py     — SQLite async engine + schema + session
    crypto.py       — AES-256-GCM encrypt/decrypt for mappings
    logging.py      — structlog setup
  main.py           — FastAPI app + lifespan
  models.py         — Pydantic schemas
tests/
  conftest.py       — Shared fixtures (tmp_path DB, env vars)
  test_config.py
  test_database.py
  test_models.py
  test_crypto.py
  test_api_health.py
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| SHIELD_ENVIRONMENT | development | development / production |
| SHIELD_SECRET_KEY | dev-secret-change-me | Signing + encryption key (required in prod) |
| SHIELD_DATA_DIR | /data | Base directory for uploads, outputs, db |
| SHIELD_DB_URL | sqlite+aiosqlite:///... | Full DB connection URL |
| SHIELD_MAX_UPLOAD_MB | 50 | Max file size |
| SHIELD_MAX_DOWNLOADS | 50 | Max downloads per document |
| SHIELD_DOCUMENT_TTL_DAYS | 14 | Document expiry |
| SHIELD_NUKE_TTL_HOURS | 72 | Hours until nuke cleanup |
| SHIELD_TOKEN_TTL_MINUTES | 30 | Download token TTL |
| SHIELD_CF_TEAM_DOMAIN | (empty) | Cloudflare Access team domain |
| SHIELD_CF_ACCESS_AUD | (empty) | Cloudflare Access AUD claim |

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download de_core_news_lg
```

## Running Tests

```bash
python -m pytest tests/ -v
```

Note: spaCy model (de_core_news_lg) is NOT required for the foundation tests.

## Running the App

```bash
uvicorn app.main:app --reload
```

## Database Schema

Three tables: `documents`, `mappings`, `download_tokens`.

- Documents store file metadata, processing status, and PII stats.
- Mappings store encrypted pseudonym↔original pairs, linked to documents.
- Download tokens are single-use, time-limited tokens for public downloads.

## Key Design Decisions

- SQLite is sufficient for single-instance deployments; no ORM models — raw SQL via `text()`.
- Mapping `original_value` is AES-256-GCM encrypted at rest using `SHIELD_SECRET_KEY`.
- Nonces are random per encryption, so identical values get different ciphertexts.
- `get_settings()` uses `@lru_cache` — call `get_settings.cache_clear()` in tests.
