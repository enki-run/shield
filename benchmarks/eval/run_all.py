#!/usr/bin/env python3
"""Shield accuracy suite — aggregate runner (the 7th, integration phase).

Runs every specialized accuracy phase and the standalone unit suites, collects
each one's PASS/FAIL, writes a combined ``benchmarks/eval/baselines/report.json``,
prints a summary table, and exits NON-ZERO only when a gate REGRESSES.

Design contract (see GATE CALIBRATION RULE):
  * On THIS branch today every hard gate is calibrated just past the current
    measured value, and every KNOWN-OPEN defect is an xfail. So this runner must
    exit 0 today.
  * A future regression flips a phase script's exit code (a hard gate fails) or
    turns a pytest run red (an xfail becomes a real failure, or a guard breaks).
    Either way the offending component reports non-zero and this runner exits 1.

What "regression" means per component:
  * phase1..phase4 scripts  -> exit 0 iff all their hard gates pass.
  * phase5 script           -> diagnostic, always exits 0 (no hard gate); its
                               pytest guard (tests/test_eval_phase5_*) is the
                               real regression gate.
  * pytest suites           -> exit 0 iff no test fails. xfail/xpass do NOT fail
                               by default, so known-open defects stay green while
                               a fix that silently breaks a guard goes red.

xpass note: we run pytest WITHOUT ``-q --runxfail`` and without strict-xfail at
the CLI, so an xfail that starts passing (a defect got fixed) is reported as
XPASS, not a failure — the suite stays green and the human is nudged to convert
the xfail into a hard assertion. This keeps CI exit-0 stable across fixes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmarks.eval._common import BASELINE_DIR  # noqa: E402

PYTHON = sys.executable

# Each component: (id, kind, label, target). kind in {"script","pytest"}.
# "script"  -> run the phase module; exit 0 == gates pass.
# "pytest"  -> run pytest on a path; exit 0 == no test failed.
COMPONENTS = [
    ("phase1-strict-scorer", "script", "Phase 1 — strict span-exact scorer",
     "benchmarks/eval/phase1_strict_scorer.py"),
    ("phase2-per-type-recall", "script", "Phase 2 — per-type full-cover recall",
     "benchmarks/eval/phase2_per_type_recall.py"),
    ("phase3-fp-stress", "script", "Phase 3 — false-positive stress on clean docs",
     "benchmarks/eval/phase3_fp_stress.py"),
    ("phase4-roundtrip-leak", "script", "Phase 4 — pseudonymize round-trip leak",
     "benchmarks/eval/phase4_roundtrip.py"),
    ("phase5-threshold-sweep", "script", "Phase 5 — threshold sweep (diagnostic)",
     "benchmarks/eval/phase5_threshold_sweep.py"),
    ("phase5-guard", "pytest", "Phase 5 — pytest regression guard",
     "tests/test_eval_phase5_threshold_sweep.py"),
    ("phase6-dedup-units", "pytest", "Phase 6 — dedup / determinism unit suite",
     "tests/test_eval_dedup.py"),
    ("accuracy-regressions", "pytest", "Phase 6 — accuracy-audit regression pins",
     "tests/test_accuracy_regressions.py"),
]


def _parse_pytest_counts(stdout: str) -> dict:
    """Pull passed/failed/xfailed/xpassed/error counts off the pytest summary."""
    counts = {"passed": 0, "failed": 0, "xfailed": 0, "xpassed": 0,
              "error": 0, "errors": 0, "skipped": 0}
    # The summary line is the last non-empty line, e.g.
    #   "10 passed, 10 xfailed in 3.21s"
    last = ""
    for line in stdout.splitlines():
        if line.strip():
            last = line.strip()
    # Strip surrounding '=' decoration pytest uses on the summary line.
    cleaned = last.strip("= ").split(" in ")[0]
    for part in cleaned.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split()
        if len(bits) >= 2 and bits[0].isdigit():
            key = bits[1].rstrip(".")
            if key in counts:
                counts[key] += int(bits[0])
    counts["error"] += counts.pop("errors")
    return counts


def run_component(comp: tuple) -> dict:
    comp_id, kind, label, target = comp
    abs_target = os.path.join(_REPO_ROOT, target)
    if kind == "script":
        cmd = [PYTHON, abs_target]
    else:
        cmd = [PYTHON, "-m", "pytest", abs_target, "-q", "--no-header"]

    t0 = time.time()
    proc = subprocess.run(
        cmd, cwd=_REPO_ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": _REPO_ROOT},
    )
    dur = round(time.time() - t0, 2)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    result = {
        "id": comp_id,
        "kind": kind,
        "label": label,
        "target": target,
        "exit_code": proc.returncode,
        "duration_s": dur,
        # A component is a REGRESSION iff it returned non-zero.
        "regressed": proc.returncode != 0,
    }
    if kind == "pytest":
        counts = _parse_pytest_counts(stdout)
        result["pytest"] = counts
        # An xpass means a known-open defect appears fixed: green, but flagged.
        result["xpass_alert"] = counts["xpassed"] > 0
    if proc.returncode != 0:
        # Capture tails so CI logs show why something regressed.
        result["stdout_tail"] = "\n".join(stdout.splitlines()[-25:])
        result["stderr_tail"] = "\n".join(stderr.splitlines()[-15:])
    return result


def _fmt_detail(r: dict) -> str:
    if r["kind"] == "pytest":
        c = r["pytest"]
        bits = [f"{c['passed']} passed"]
        if c["failed"]:
            bits.append(f"{c['failed']} FAILED")
        if c["xfailed"]:
            bits.append(f"{c['xfailed']} xfail")
        if c["xpassed"]:
            bits.append(f"{c['xpassed']} XPASS")
        if c["error"]:
            bits.append(f"{c['error']} ERROR")
        if c["skipped"]:
            bits.append(f"{c['skipped']} skipped")
        return ", ".join(bits)
    return f"exit={r['exit_code']}"


def main() -> int:
    print("=" * 78)
    print("SHIELD ACCURACY SUITE — run_all (7 phases)")
    print("=" * 78)

    results = []
    for comp in COMPONENTS:
        print(f"\n>>> {comp[2]}")
        print(f"    target: {comp[3]}")
        r = run_component(comp)
        status = "REGRESSION" if r["regressed"] else "OK"
        print(f"    -> {status}  ({_fmt_detail(r)}, {r['duration_s']}s)")
        if r.get("xpass_alert"):
            print("    !! XPASS: a known-open defect now passes — convert its "
                  "xfail to a hard assertion.")
        if r["regressed"]:
            print("    --- regression output tail ---")
            for line in r.get("stdout_tail", "").splitlines():
                print(f"      {line}")
            for line in r.get("stderr_tail", "").splitlines():
                print(f"      {line}")
        results.append(r)

    regressed = [r for r in results if r["regressed"]]
    xpass = [r for r in results if r.get("xpass_alert")]

    # ----- summary table -----
    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    width = max(len(r["label"]) for r in results)
    for r in results:
        flag = "REGRESSION" if r["regressed"] else "OK"
        extra = "  [XPASS]" if r.get("xpass_alert") else ""
        print(f"  {flag:<11} {r['label']:<{width}}  {_fmt_detail(r)}{extra}")

    total_pass = sum(r["pytest"]["passed"] for r in results if r["kind"] == "pytest")
    total_xfail = sum(r["pytest"]["xfailed"] for r in results if r["kind"] == "pytest")
    print("-" * 78)
    print(f"  components: {len(results)}   regressions: {len(regressed)}   "
          f"pytest: {total_pass} passed / {total_xfail} xfailed   "
          f"xpass-alerts: {len(xpass)}")

    exit_code = 1 if regressed else 0

    payload = {
        "suite": "shield-accuracy-eval",
        "generated_by": "benchmarks/eval/run_all.py",
        "python": sys.version.split()[0],
        "n_components": len(results),
        "n_regressions": len(regressed),
        "n_xpass_alerts": len(xpass),
        "pytest_totals": {"passed": total_pass, "xfailed": total_xfail},
        "exit_code": exit_code,
        "all_green": exit_code == 0,
        "components": results,
        "regressions": [r["id"] for r in regressed],
        "xpass_alerts": [r["id"] for r in xpass],
    }
    os.makedirs(BASELINE_DIR, exist_ok=True)
    out = os.path.join(BASELINE_DIR, "report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"\n  combined report written: {out}")

    print(f"\n  RESULT: {'ALL GREEN (no regression)' if exit_code == 0 else 'REGRESSION DETECTED'}")
    print(f"  exit code: {exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
