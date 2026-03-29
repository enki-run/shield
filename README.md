# Shield

Open-source document pseudonymization service. Upload documents (PDF, DOCX, XLSX, ODT, ODS, CSV, TXT), detect PII, pseudonymize, and provide secure one-time download links for LLMs.

## Features

- **7 document formats** — PDF (→ Markdown), DOCX, XLSX, ODT, ODS, CSV, TXT
- **2 PII modes** — Balanced (productivity) and Compliant (NIS2/DSGVO/ISO 27001)
- **Decoder view** — Mapping table (Pseudonym ↔ Original ↔ Type) with CSV export
- **One-time download tokens** — 30min TTL, max 50 per document, public endpoint for LLM access
- **Auto-cleanup** — Documents expire after 14 days, nuked after 50 downloads
- **Encrypted mappings** — AES-256-GCM at rest
- **Cloudflare Access** — GitHub OAuth + Email OTP authentication

## Quick Start

```bash
docker compose up -d
# Open http://localhost:8000/app/
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SHIELD_SECRET_KEY` | dev-secret... | Encryption key (required in production) |
| `SHIELD_DATA_DIR` | /data | Storage directory |
| `SHIELD_MAX_UPLOAD_MB` | 50 | Max file size |
| `SHIELD_MAX_DOWNLOADS` | 50 | Downloads before nuke |
| `SHIELD_DOCUMENT_TTL_DAYS` | 14 | Document lifetime |
| `SHIELD_TOKEN_TTL_MINUTES` | 30 | Download token TTL |
| `SHIELD_CF_TEAM_DOMAIN` | | CF Access team domain |
| `SHIELD_CF_ACCESS_AUD` | | CF Access audience |

## Tech Stack

Python 3.12, FastAPI, Presidio + spaCy, React 19, Vite, TailwindCSS, SQLite, Docker

## License

Apache 2.0 — see [LICENSE](LICENSE)
