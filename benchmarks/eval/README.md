# Shield Accuracy Evaluation Suite

Specialized, **honest** accuracy phases for Shield's PII pseudonymization. They
replace the single inflated `benchmarks/run_benchmark.py` (which reported
100%/93% via fuzzy substring matching) with **span-exact** scoring and **real
false-positive counting**.

## Why span-exact, not fuzzy

Under GDPR pseudonymization the cost model is asymmetric and unforgiving:

- A **miss** (false negative) *or* a **partial span** (surname / house number /
  IBAN tail left in cleartext) is a real **PII leak**.
- A **false positive** over-redacts and destroys document utility.
- Span boundaries matter **char-for-char**, so the scorer is span-exact
  (`strict_score`) and a separate `covered()` check verifies *full* coverage
  (no cleartext tail). Fuzzy substring matching hides exactly these leaks.

All corpus data is **fictional only** (Max Mustermann / Erika Musterfrau,
Musterstrasse 1 / 10115 Berlin, Muster GmbH / Beispiel AG, `@example.com`,
fictional/test IBANs & card numbers with valid checksums). Never real data.

Shared primitives live in [`_common.py`](./_common.py): `detect`, `Span`,
`Detection`, `strict_score`, `covered`, `coverage_rate`, `load_jsonl`,
`doc_spans`, `write_report`, `gate`.

## Gate calibration philosophy

Each hard gate threshold is set **just past the current measured value** (small
margin) so the suite is **green on this branch today** while catching any future
**regression**. Every **known-open** audit defect is an `xfail` (or a documented
`known_open` list in the baseline JSON) rather than a hard failure — so a future
*fix* surfaces as an `XPASS` alert (nudge to convert to a hard assertion) instead
of breaking CI.

## The 7 phases

| # | Phase | Measures | Hard gate (PASS today) | Audit defect it catches |
|---|-------|----------|------------------------|--------------------------|
| 1 | `phase1_strict_scorer.py` | Span-exact P/R/F1 + coverage on the gold corpus and on `cv_synthetic.docx`; FP on the pii-free subset | gold strict F1 >= 0.7368; cv_synthetic strict F1 >= 0.7270; clean-subset FP == 0 | Inflated official 100%/93% collapses to span-exact 70%/79%; ORGANIZATION over-merge; residual spaCy NER FP; DE_ID_CARD miss |
| 2 | `phase2_per_type_recall.py` | Per-type full-cover (typed) recall across 13 PII types, best of balanced/compliant; macro + micro | no type at 0% in BOTH modes (HARD); macro typed recall >= 0.90 (measured 0.922) | DE_ID_CARD recall (62.5%), ORGANIZATION e.V./Ltd./suffixless (68.8%), IPv6 short-form / IP swallow (87.5%) |
| 3 | `phase3_fp_stress.py` | False positives on 4 PII-free docs (per-1000-token rate + driver breakdown), both modes | denylist-covered worst-doc FP/1k <= 45.0; non-denylist runbook FP/1k <= 92.0 (informational ceiling) | Residual spaCy NER FP on tech terms + denylist overfitting; `DE_StreetName` firing on common nouns |
| 4 | `phase4_roundtrip.py` | End-to-end pseudonymize round-trip: residual verbatim leaks + pseudonym consistency/collisions | no NEW residual leak; known-open leaks not grown (<= 5); 0 consistency violations; 0 collisions | IBAN checksum-invalid fallback; ORGANIZATION e.V./Ltd./suffixless; DE_ID_CARD 10-char regex gap |
| 5 | `phase5_threshold_sweep.py` | Confidence-threshold sweep: NER vs structured recall and clean-doc FP across thresholds; justifies the 0.40 structured floor | **report-only** (always exit 0); regression gate is its pytest guard | Confirms balanced=0.70 / compliant=0.50 operating points; structured floor buys +30 hits; residual NER tech-term FP |
| 6 | `tests/test_eval_dedup.py` + `tests/test_accuracy_regressions.py` | Deterministic unit tests for `_deduplicate_entities` / `_trim_entity` containment + `detect()` determinism (PYTHONHASHSEED 0/1/2); audit-defect regression pins | every unit test passes (1 strict xfail for the equal-span eviction defect) | Equal-span generic-over-structured eviction; trim-on-regex-span leak; cross-seed nondeterminism; each pinned audit leak |
| 7 | `run_all.py` (this integration phase) | Aggregates all of the above; writes `baselines/report.json`; exits non-zero ONLY on a regression | exit 0 iff no component regresses | n/a — the gate of gates |

Phases 1–5 also have pytest wrappers under `tests/eval/` and `tests/` that wrap
the same logic for CI (`-q`); the standalone scripts additionally write a
per-phase baseline JSON under [`baselines/`](./baselines).

## Run locally

From the repo root, with the project venv:

```bash
cd /Users/nico/Workspace/shield

# The whole suite (the 7th, integration phase) — writes baselines/report.json,
# exits 0 today, non-zero only on a regression:
.venv/bin/python benchmarks/eval/run_all.py

# Any single phase script (each writes its own baselines/<phase>.json):
.venv/bin/python benchmarks/eval/phase1_strict_scorer.py
.venv/bin/python benchmarks/eval/phase2_per_type_recall.py
.venv/bin/python benchmarks/eval/phase3_fp_stress.py
.venv/bin/python benchmarks/eval/phase4_roundtrip.py
.venv/bin/python benchmarks/eval/phase5_threshold_sweep.py   # diagnostic, always exit 0

# Full pytest suite (includes the eval wrappers + unit phases):
.venv/bin/python -m pytest tests/ -q
```

CI runs the same thing via [`.github/workflows/accuracy.yml`](../../.github/workflows/accuracy.yml)
(Python 3.12, `pip install -r requirements.txt`, `python -m spacy download
de_core_news_lg`, then `run_all.py` and the full pytest suite). Note: the spaCy
model `de_core_news_lg` is **not** in `requirements.txt` and must be downloaded
separately (the workflow does this).

## Current aggregated numbers (this branch)

- `run_all.py`: **8 components, 0 regressions, exit 0**. pytest within the suite:
  23 passed / 3 xfailed, 0 xpass-alerts.
- Phase 1: gold strict P=0.778 R=0.737 F1=0.757, coverage 0.895, clean FP=0;
  cv_synthetic strict P=0.705 R=0.795 F1=0.747 (vs inflated 1.00/0.93).
- Phase 2: macro typed recall 92.2%, micro 92.3%; no dead types.
- Phase 3: denylist-covered agg 22.12 FP/1k, non-denylist runbook 88.46 FP/1k.
- Phase 4: 5 residual leaks (all known-open baseline), 0 new, 0 consistency
  violations, 0 collisions.
- Phase 5: balanced=0.70 / compliant=0.50 give NER recall 0.90; structured floor
  lifts structured recall 0.80 -> 0.97 at thr 0.70; 0 structured FP at all thresholds.
- Full `pytest tests/ -q`: **160 passed, 1 skipped, 22 xfailed, 0 failed**.

## Known-open defects (xfail today — NOT regressions)

These are real, confirmed leaks/over-redactions pinned as `xfail`. A fix flips
them to `XPASS` (run_all prints an `[XPASS]` alert) — convert the xfail to a hard
assertion when that happens.

1. **DE_ID_CARD regex/priority gap** — 10-char forms with mid-string letters
   (`L01X00T471`, `L1234567X8`, `C2345678Y9`) miss the `DE_Personalausweis`
   pattern; spaCy often grabs the number into a PERSON/LOCATION span
   (type-confusion). Typed recall 62.5%. (Phases 1, 2, 4, 5)
2. **ORGANIZATION e.V. / Ltd. / Inc. / suffixless recall** — `Beispiel e.V.`,
   `Beispiel Trading Ltd.`, `Muster Inc.`, `Mustermann Consulting`, institutional
   forms (`Beispiel Institut fuer Forschung`) not caught. Typed recall 68.8%.
   (Phases 1, 2, 4, 5)
3. **IBAN checksum-invalid / typed fallback** — `DE00123456780000000000`
   (valid shape, bad checksum) is rejected by `IbanRecognizer` with no
   length/typed fallback -> leaks verbatim. (Phase 4)
4. **Residual spaCy NER false positives on tech terms** — non-denylist stack
   (Kafka/Datadog/Jenkins/Vault/Loki/Prometheus/ArgoCD/Terraform/Kubernetes) and
   hyphenated compounds (`Cisco-Hardware`, `Sophos-Firewalls`) mislabeled
   LOCATION/PERSON on PII-free docs (88.46 FP/1k in the runbook). Threshold
   tuning cannot fix; needs denylist/context coverage. (Phases 3, 5)
5. **IPv6 short-form recall** — abbreviated `2001:db8::8a2e:370:7334` only
   partially matched by Presidio (cleartext tail leak); some IPs swallowed into a
   spaCy LOCATION span. (Phases 2, 5)
6. **`DE_StreetName` over-fires on common nouns** — words ending in street-like
   suffixes (`Quartal` -> `-al`, `Speicherplatz` -> `platz`) flagged LOCATION
   without address context. (Phase 3)
7. **Equal-span containment eviction (dedup)** — on an *exactly-equal* span a
   lower-priority generic NER type (LOCATION/PERSON) evicts a higher-priority
   structured type (IBAN_CODE/DE_ID_CARD): redaction correctly placed but
   mistyped. Structured type is only preserved when its span is strictly wider.
   (Phase 6, strict xfail `test_structured_iban_survives_equal_span_generic_location`)
8. **cv_synthetic strict recall below official** — 0.795 strict vs 0.93 inflated;
   the official number came from fuzzy substring matching, not span-exact. (Phase 1)
