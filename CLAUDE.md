# Shield — Document Pseudonymization Service

## Project Overview

Shield is an open-source document pseudonymization service. It detects PII in uploaded documents, replaces it with consistent pseudonyms, and provides secure one-time download links. Pseudonym-to-original mappings are AES-256-GCM encrypted at rest.

**IMPORTANT:** Never use real personal data in code, comments, tests, or examples. Always use fictional data:
- Names: Max Mustermann, Erika Musterfrau
- Addresses: Musterstraße 1, 10115 Berlin
- Companies: Muster GmbH, Beispiel AG
- Email: max.mustermann@example.com
- Phone: +49 30 12345678

## Tech Stack

- **Runtime:** Python 3.12
- **Framework:** FastAPI (async)
- **Database:** SQLite via SQLAlchemy async + aiosqlite
- **PII Detection:** Microsoft Presidio + spaCy (`de_core_news_lg`)
- **Frontend:** React 19, TypeScript, Vite, TailwindCSS
- **Auth:** Cloudflare Access JWT middleware (optional)
- **Logging:** structlog (JSON in production, console in dev)
- **Testing:** pytest + pytest-asyncio + httpx

## Project Structure

```
app/
  api/
    dependencies.py   — FastAPI dependency injection (auth, DB session)
    documents.py      — Document upload, list, detail endpoints
    download.py       — One-time token generation + public download endpoint
  core/
    config.py         — Settings (env-driven, lru_cache)
    database.py       — SQLite async engine + schema + session
    crypto.py         — AES-256-GCM encrypt/decrypt for mappings
    logging.py        — structlog setup
  middleware/
    cf_access.py      — Cloudflare Access JWT validation middleware
  pipeline/
    detector.py       — 4-stage PII detection engine
    pseudonymizer.py  — Replace detected entities with pseudonyms
    rebuilder.py      — Reassemble pseudonymized document
    detection_rules.json — Editable detection rules (no code changes needed)
    parsers/
      base.py         — Parser interface
      pdf_parser.py   — PDF → Markdown
      docx_parser.py  — DOCX parser
      xlsx_parser.py  — XLSX parser (header-preserving)
      odt_parser.py   — ODT parser
      ods_parser.py   — ODS parser
      csv_parser.py   — CSV parser
      txt.py          — Plain text parser
  services/
    document_service.py — Document lifecycle (create, process, expire)
    token_service.py    — One-time download token management
    cleanup_service.py  — Background cleanup (expired docs, nuke threshold)
  main.py             — FastAPI app + lifespan + router registration
  models.py           — Pydantic schemas (request/response models)
benchmarks/
  run_benchmark.py    — Precision/recall/F1 benchmark runner
  cv_synthetic.docx   — Synthetic test document (fictional data only)
  expected_cv_synthetic.json — Expected detection results
frontend/
  src/
    pages/            — DocumentList, DocumentDetail
    components/       — Upload, MappingTable, PiiReport, DownloadToken, StatusBadge, DocumentCard
    services/         — API client
tests/
  conftest.py         — Shared fixtures (tmp_path DB, env vars)
  test_detector.py
  test_document_service.py
  test_api_documents.py
  test_api_download.py
  test_api_health.py
  test_cf_access.py
  test_cleanup_service.py
  test_parsers.py
  test_pseudonymizer.py
  test_rebuilder.py
  test_token_service.py
  test_config.py / test_database.py / test_models.py / test_crypto.py
```

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download de_core_news_lg

# Run backend (dev)
uvicorn app.main:app --reload

# Run tests
python -m pytest tests/ -v

# Run benchmarks
python benchmarks/run_benchmark.py --mode balanced
python benchmarks/run_benchmark.py --mode compliant --verbose

# Frontend dev
cd frontend && npm install && npm run dev

# Frontend build (output goes to app/static/)
cd frontend && npm run build

# Docker
docker compose up -d
```

## PII Detection Pipeline

The detector (`app/pipeline/detector.py`) runs 4 stages:

1. **spaCy NER** — `de_core_news_lg` model for contextual entity recognition (PERSON, ORGANIZATION, LOCATION)
2. **Presidio built-in recognizers** — regex + checksum-based (EMAIL, PHONE, IBAN, CREDIT_CARD, IP_ADDRESS, URL)
3. **Config-based rules** (`detection_rules.json`) — custom PatternRecognizers for DE_TAX_ID, DE_SOCIAL_SECURITY, DE_ID_CARD, German street/postal patterns
4. **Deduplication** — overlapping spans are resolved; highest-confidence entity wins

### Detection Modes

| Mode | Threshold | Entities |
|---|---|---|
| `balanced` | 0.70 | PERSON, ORGANIZATION, LOCATION, EMAIL, PHONE, IBAN, CREDIT_CARD, IP_ADDRESS, URL, DE_TAX_ID, DE_SOCIAL_SECURITY, DE_ID_CARD |
| `compliant` | 0.50 | All balanced + DATE_TIME, NRP, MEDICAL_LICENSE, US_SSN |

### Tuning Detection

Edit `app/pipeline/detection_rules.json` — add regex patterns, adjust scores, extend context keywords. Restart the service. No code changes needed.

### False-Positive Filtering

`_is_false_positive()` in `detector.py` suppresses known noise:
- IBAN prefixes (e.g. "DE") not flagged as LOCATION
- Phone patterns require minimum digit count
- Organization terms filtered without surrounding context

## Key Architectural Decisions

- **SQLite is sufficient** for single-instance deployments. Schema uses raw SQL via `text()`, no ORM models.
- **Mapping encryption:** `original_value` is AES-256-GCM encrypted using `SHIELD_SECRET_KEY`. Nonces are random per encryption — identical values get different ciphertexts.
- **`get_settings()` uses `@lru_cache`** — call `get_settings.cache_clear()` in tests to avoid state leakage.
- **spaCy model is lazy-loaded** — `_get_analyzer()` initializes on first call and caches globally. Tests that don't need NER can skip the model download.
- **XLSX/CSV headers are never pseudonymized** — parsers mark header rows explicitly; the rebuilder skips them.
- **One-time tokens** are single-use, expire after `SHIELD_TOKEN_TTL_MINUTES`, and are deleted on first access or expiry.
- **Cloudflare Access middleware** is a no-op when `SHIELD_CF_TEAM_DOMAIN` is not set — safe for local development.

## Conventions

- All API routes under `/api/v1/`
- Frontend served from `/app/` (static build output in `app/static/`)
- Public download endpoint at `/download/{token}` (no auth required)
- Structured logging with `structlog` — use `logger.info("event.name", key=value)` style
- Config is always accessed via `get_settings()`, never imported directly
- Test fixtures in `conftest.py` reset settings cache and use `tmp_path` for DB isolation
