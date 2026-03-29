# Contributing to Shield

Thank you for your interest in contributing to Shield!

## Getting Started

```bash
git clone https://github.com/enki-run/shield.git
cd shield
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download de_core_news_lg
python -m pytest tests/ -v
```

## Development Workflow

1. Fork the repository
2. Create a feature branch (`feat/your-feature`)
3. Write tests first (TDD)
4. Implement the feature
5. Run the full test suite: `python -m pytest tests/ -v`
6. Run the benchmark: `python benchmarks/run_benchmark.py --verbose`
7. Submit a Pull Request

## Important Rules

- **No real PII in code, tests, or examples.** Use fictional data only:
  - Names: Max Mustermann, Erika Musterfrau
  - Addresses: Musterstraße 1, 10115 Berlin
  - Companies: Muster GmbH, Beispiel AG
- **Conventional Commits:** `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`
- **Detection rules** go in `detection_rules.json`, not in Python code
- **All API routes** under `/api/v1/`

## Detection Tuning

To improve PII detection, edit `app/pipeline/detection_rules.json`:
- Add regex patterns with appropriate confidence scores
- Add context words that boost detection confidence
- Add terms to the false-positive denylist
- Run the benchmark to verify improvements

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
