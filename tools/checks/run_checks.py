#!/usr/bin/env python3
"""Run all portable harness guardrails (AGENTS.md non-negotiable rules).

This is the single entry point used by:
  - pre-commit and CI            -> enforce mode (exit 1 on any error)
  - the Antigravity /review flow  -> --annotate mode (report only, exit 0)

Usage:
  python3 tools/checks/run_checks.py [--annotate] [paths...]

With no paths it scans the whole repo. pre-commit passes changed files as paths.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import forbidden_patterns  # noqa: E402
import validate_dataform  # noqa: E402


def main(argv):
    annotate = "--annotate" in argv
    paths = [a for a in argv if not a.startswith("--")] or None

    findings = []
    findings += forbidden_patterns.find_findings(paths)
    findings += validate_dataform.find_findings(paths)

    errors = [f for f in findings if f["severity"] == "error"]
    warns = [f for f in findings if f["severity"] == "warn"]

    for f in sorted(findings, key=lambda x: (x["path"], x["line"] or 0)):
        loc = f["path"] + (f":{f['line']}" if f["line"] else "")
        print(f"{f['severity'].upper():5} {loc} [{f['rule']}] {f['message']}")

    if not findings:
        print("OK — no harness violations found.")

    print(f"\n{len(errors)} error(s), {len(warns)} warning(s).")
    if annotate:
        print("(annotate mode — not failing the run; review and decide.)")
        return 0
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
