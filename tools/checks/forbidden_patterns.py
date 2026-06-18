#!/usr/bin/env python3
"""Scan code files for forbidden patterns (AGENTS.md rules 1, 7).

Tool-agnostic: invoked by pre-commit, CI, the /review workflow, and the eval
runner. Pure stdlib so it runs anywhere with no install.

Rules enforced here (the file-content-checkable subset):
  - Rule 1: no `bq cp`, no manual CREATE TABLE AS SELECT, no scheduled queries.
  - Rule 7: no secrets committed to code.

Command-interception ("block the agent before it runs `bq cp`") is a Claude Code
hook concern and is intentionally out of scope here — Antigravity has no hook
mechanism, so enforcement lives in the files that get committed.
"""
from __future__ import annotations

import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Directories never scanned.
EXCLUDE_DIRS = {
    ".git", ".agents", ".venv", "node_modules", ".dataform",
    "__pycache__", ".github",
}
# evals/cases holds deliberately-bad fixtures; the eval runner targets them
# explicitly, so the repo-wide scan skips them.
EXCLUDE_PREFIXES = ("evals/cases/", "tools/checks/")

# Only scan code-like files. Markdown is excluded so docs can name the very
# patterns they forbid (e.g. "never use `bq cp`").
SCAN_EXTS = {
    ".sqlx", ".sql", ".py", ".sh", ".js", ".ts", ".json",
    ".yaml", ".yml", ".tf",
}
SCAN_NAMES = {"Dockerfile", "requirements.txt", "cloudbuild.yaml"}

# Placeholders that should NOT count as real secrets.
_PLACEHOLDER = re.compile(
    r"(your[-_]|example|changeme|dummy|placeholder|xxxx|<[^>]+>|\$\{|\{\{|redacted|fake)",
    re.IGNORECASE,
)

# (rule, severity, compiled regex, message, restrict-to-extensions-or-None)
_PATTERNS = [
    ("no-bq-cp", "error", re.compile(r"\bbq\s+cp\b"),
     "Use Dataform for BigQuery copies, not `bq cp` (AGENTS.md rule 1).", None),
    ("no-scheduled-query", "error",
     re.compile(r"--transfer[_-]config|data_source\s*=\s*['\"]?scheduled_query"),
     "BigQuery scheduled queries are forbidden; use Dataform (rule 1).", None),
    ("no-manual-ctas", "error",
     re.compile(r"CREATE\s+(OR\s+REPLACE\s+)?TABLE\b[\s\S]{0,160}?\bAS\s+SELECT\b",
                re.IGNORECASE),
     "Manual CREATE TABLE AS SELECT is forbidden; model it in Dataform (rule 1).",
     # .sqlx excluded: Dataform itself compiles to CTAS; source SQLX never writes it.
     {".sql", ".py", ".sh", ".js", ".ts"}),
    ("secret-private-key", "error",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
     "Private key committed to code; use Secret Manager (rule 7).", None),
    ("secret-gcp-api-key", "error", re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
     "Google API key committed to code; use Secret Manager (rule 7).", None),
    ("secret-aws-key", "error", re.compile(r"AKIA[0-9A-Z]{16}"),
     "AWS access key committed to code; use Secret Manager (rule 7).", None),
    ("secret-assignment", "error",
     re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*"
                r"['\"][^'\"\s]{8,}['\"]"),
     "Hardcoded credential; use Secret Manager / Airflow Connections (rule 7).",
     None),
]


def _iter_files(paths):
    if paths:
        for p in paths:
            if os.path.isfile(p):
                yield os.path.abspath(p)
        return
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, REPO_ROOT)
            if rel.startswith(EXCLUDE_PREFIXES):
                continue
            ext = os.path.splitext(name)[1]
            if ext in SCAN_EXTS or name in SCAN_NAMES:
                yield full


def find_findings(paths=None):
    # Walk mode excludes fixtures/self (via _iter_files). Explicit paths are
    # always scanned — the eval runner deliberately targets evals/cases/.
    findings = []
    for full in _iter_files(paths):
        rel = os.path.relpath(full, REPO_ROOT)
        ext = os.path.splitext(full)[1]
        try:
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for rule, severity, rx, msg, only_exts in _PATTERNS:
            if only_exts is not None and ext not in only_exts:
                continue
            for i, line in enumerate(lines, 1):
                if not rx.search(line):
                    continue
                if rule.startswith("secret-assignment") and _PLACEHOLDER.search(line):
                    continue
                findings.append({
                    "severity": severity, "rule": rule, "path": rel,
                    "line": i, "message": msg,
                })
    return findings


if __name__ == "__main__":
    found = find_findings(sys.argv[1:] or None)
    for f in found:
        print(f"{f['severity'].upper()} {f['path']}:{f['line']} [{f['rule']}] {f['message']}")
    sys.exit(1 if any(f["severity"] == "error" for f in found) else 0)
