#!/usr/bin/env python3
"""Validate Dataplex governance headers on lake tables (data-governance rule).

Every materialized bronze/silver/gold table must carry a `/* governance */`
header that supplies the values attached as Dataplex aspects (owners/stewards,
plus source_system+raw_format on bronze and data_sensitivity on gold). The
derivation + per-layer requirements live in tools/governance/aspect_model.py;
this file only wires that logic into the harness check interface
(`find_findings(paths)`), matching forbidden_patterns.py / validate_dataform.py.

See guidelines/data-governance.md for the contract and the .agents/skills/
knowledge-catalog skill for how aspects are applied.
"""
from __future__ import annotations

import os
import sys

# tools/governance is a sibling of tools/checks; make aspect_model importable.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "governance"))

import aspect_model  # noqa: E402


def find_findings(paths=None):
    findings = []
    for full in aspect_model.iter_sqlx(paths):
        parsed = aspect_model.parse_sqlx(full)
        for rule, message in aspect_model.governance_issues(parsed):
            findings.append({
                "severity": "error", "rule": rule, "path": parsed["path"],
                "line": None, "message": message,
            })
    return findings


if __name__ == "__main__":
    found = find_findings(sys.argv[1:] or None)
    for f in found:
        loc = f["path"] + (f":{f['line']}" if f["line"] else "")
        print(f"{f['severity'].upper()} {loc} [{f['rule']}] {f['message']}")
    sys.exit(1 if any(f["severity"] == "error" for f in found) else 0)
