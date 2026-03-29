# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Shield, please report it responsibly:

1. **Do NOT** create a public GitHub issue
2. Email: security@enki.run
3. Include: description, steps to reproduce, potential impact

We will respond within 48 hours and work with you on a fix.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |

## Security Measures

- **Encrypted mappings:** AES-256-GCM at rest
- **One-time download tokens:** CSPRNG, 30min TTL, consumed after first use
- **No PII in logs:** Structured logging with metadata only
- **CF Access auth:** All endpoints except `/dl/{token}` require authentication
- **Document TTL:** Auto-deleted after 14 days
- **Scanned PDF rejection:** Prevents silent PII leaks from image-only documents
