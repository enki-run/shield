# Shield

Open-source document pseudonymization service. Upload documents, detect PII, replace it with consistent pseudonyms, and provide secure download links — ready for use with LLMs or data pipelines.

## Features

- **7 document formats** — PDF (converted to Markdown), DOCX, XLSX, ODT, ODS, CSV, TXT
- **2 PII detection modes** — Balanced (productivity-focused) and Compliant (NIS2/DSGVO/ISO 27001)
- **Decoder view** — Mapping table (Pseudonym ↔ Original ↔ Type) with CSV export
- **One-time download tokens** — 30-minute TTL, max 50 per document, public endpoint for LLM access
- **Auto-cleanup** — Documents expire after 14 days, automatically deleted after 50 downloads
- **Encrypted mappings** — AES-256-GCM at rest
- **Cloudflare Access** — GitHub OAuth + Email OTP authentication (optional)

## PII Detection

Shield uses a 4-stage detection pipeline:

1. **spaCy NER** (`de_core_news_lg`) — contextual entity recognition
2. **Presidio recognizers** — pattern-based detection (email, IBAN, phone, etc.)
3. **Config rules** (`detection_rules.json`) — editable without code changes
4. **Deduplication** — resolves overlapping entities, highest confidence wins

### Supported Entity Types

| Entity | Description |
|---|---|
| `PERSON` | Full names (e.g. Max Mustermann) |
| `ORGANIZATION` | Company and institution names |
| `LOCATION` | Addresses, street names, postal codes (e.g. Musterstraße 1, 10115 Berlin) |
| `EMAIL_ADDRESS` | Email addresses |
| `PHONE_NUMBER` | German and international phone numbers |
| `IBAN_CODE` | IBAN bank account numbers |
| `DE_TAX_ID` | German tax identification number |
| `DE_SOCIAL_SECURITY` | German social security number |
| `DE_ID_CARD` | German ID card number |
| `URL` | Web URLs |

Compliant mode additionally detects: `DATE_TIME`, `NRP`, `MEDICAL_LICENSE`, `US_SSN`.

### False-Positive Filtering

The pipeline includes targeted false-positive suppression: IBAN prefixes are not flagged as locations, common German organization terms without context are filtered, and phone pattern detection is context-aware.

### XLSX / CSV Header Preservation

Column headers in XLSX and CSV files are never pseudonymized — only cell values are processed. This ensures the document structure remains intact after pseudonymization.

## Benchmark Results

Tested on a synthetic German CV (DOCX) and a realistic XLSX dataset:

| Document | Precision | Recall | F1 |
|---|---|---|---|
| CV (DOCX) | 100% | 86.8% | 93.0% |
| XLSX | 97% | 90% | — |

XLSX column header preservation: **100%** (no header falsely pseudonymized).

Run benchmarks locally:

```bash
python benchmarks/run_benchmark.py --mode balanced
```

## Quick Start

```bash
docker compose up -d
# Open http://localhost:8000/app/
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SHIELD_ENVIRONMENT` | `development` | `development` or `production` |
| `SHIELD_SECRET_KEY` | `dev-secret-...` | Encryption key — **change in production** |
| `SHIELD_DATA_DIR` | `/data` | Storage directory |
| `SHIELD_MAX_UPLOAD_MB` | `50` | Max file size in MB |
| `SHIELD_MAX_DOWNLOADS` | `50` | Downloads before document is deleted |
| `SHIELD_DOCUMENT_TTL_DAYS` | `14` | Document lifetime in days |
| `SHIELD_TOKEN_TTL_MINUTES` | `30` | Download token TTL |
| `SHIELD_CF_TEAM_DOMAIN` | _(empty)_ | Cloudflare Access team domain (optional) |
| `SHIELD_CF_ACCESS_AUD` | _(empty)_ | Cloudflare Access audience (optional) |

## Detection Tuning

Edit `app/pipeline/detection_rules.json` to add patterns, adjust confidence scores, or extend context keywords — no code changes required, restart the service to apply.

## Tech Stack

- **Backend:** Python 3.12, FastAPI (async), SQLite + SQLAlchemy, structlog
- **PII:** Microsoft Presidio + spaCy `de_core_news_lg`
- **Frontend:** React 19, TypeScript, Vite, TailwindCSS
- **Auth:** Cloudflare Access JWT middleware
- **Container:** Docker

## License

Apache 2.0 — see [LICENSE](LICENSE)
