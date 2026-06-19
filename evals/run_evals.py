#!/usr/bin/env python3
"""Eval harness for the guardrails — a deterministic self-test (no LLM needed).

Two assertions, both runnable in CI:
  1. POSITIVE — every file under evals/golden/ passes all checks with zero
     findings (the target quality bar stays clean).
  2. NEGATIVE — every deliberately-bad fixture under evals/cases/bad/ trips the
     rule it is meant to trip (the checks actually fire).

If a rule regresses (stops firing) or a golden exemplar drifts out of
compliance, this fails. Natural-language agent-eval tasks live in evals/README.md.
"""
from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools", "checks"))

import forbidden_patterns  # noqa: E402
import validate_dataform  # noqa: E402

GOLDEN_DIR = os.path.join(REPO_ROOT, "evals", "golden")
BAD_DIR = os.path.join(REPO_ROOT, "evals", "cases", "bad")

# fixture (relative to evals/cases/bad) -> rule that MUST fire for it.
NEGATIVE_CASES = {
    "definitions/silver/sales/hardcoded_ref.sqlx": "no-hardcoded-ref",
    "definitions/bronze/erp/declared.sqlx": "bronze-must-materialize",
    "definitions/sources/erp/materialized.sqlx": "sources-declaration-only",
    "definitions/silver/sales/missing_assertions.sqlx": "assertions-required",
    "definitions/staging/sales/stg_table.sqlx": "staging-view-only",
    "scripts/copy.sh": "no-bq-cp",
    "scripts/leak.py": "secret-assignment",
}


def _all_findings(paths):
    return (forbidden_patterns.find_findings(paths)
            + validate_dataform.find_findings(paths))


def _walk(root):
    out = []
    for dp, _d, fs in os.walk(root):
        out.extend(os.path.join(dp, f) for f in fs)
    return out


def main():
    failures = []

    # 1. POSITIVE
    golden = _walk(GOLDEN_DIR)
    gold_findings = _all_findings(golden)
    if gold_findings:
        for f in gold_findings:
            failures.append(f"golden file flagged: {f['path']} [{f['rule']}] {f['message']}")
    print(f"POSITIVE: {len(golden)} golden file(s), {len(gold_findings)} unexpected finding(s).")

    # 2. NEGATIVE
    passed = 0
    for rel, expected in NEGATIVE_CASES.items():
        full = os.path.join(BAD_DIR, rel)
        if not os.path.isfile(full):
            failures.append(f"missing fixture: evals/cases/bad/{rel}")
            continue
        rules = {f["rule"] for f in _all_findings([full])}
        if expected in rules:
            passed += 1
        else:
            failures.append(
                f"fixture {rel} did NOT trip '{expected}' (got: {sorted(rules) or 'nothing'})")
    print(f"NEGATIVE: {passed}/{len(NEGATIVE_CASES)} fixtures tripped their rule.")

    if failures:
        print("\nEVAL FAILURES:")
        for msg in failures:
            print(f"  - {msg}")
        return 1
    print("\nAll evals passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
