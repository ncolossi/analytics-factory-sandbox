#!/usr/bin/env python3
"""Validate Dataform SQLX files against org rules (AGENTS.md rules 2-6).

Pure stdlib. SQLX config blocks are JS-like, not JSON, so this uses targeted
brace-matching + regex rather than a full parser — pragmatic and good enough to
gate the rules below. Language of descriptions (Portuguese) is NOT machine-checked
here; that is a reviewer concern (the /review workflow flags it).

  - Rule 2: no hardcoded project.dataset.table references (use ${ref()}/${self()}).
  - Rule 3: bronze must materialize (table/incremental, append-only); sources are
    declaration-only.
  - Rule 4: silver & gold declare assertions with a uniqueKey.
  - Rule 5: staging is type "view".
  - Rule 6: silver & gold tables have a description and a columns{} block.
"""
from __future__ import annotations

import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFINITIONS = os.path.join("transformation", "dataform", "definitions")

_TYPE_RX = re.compile(r"\btype\s*:\s*['\"](\w+)['\"]")
_ASSERT_RX = re.compile(r"\bassertions\s*:\s*\{")
_UNIQUEKEY_RX = re.compile(r"\buniqueKey\s*:")
_DESC_RX = re.compile(r"\bdescription\s*:\s*['\"]")
_COLUMNS_RX = re.compile(r"\bcolumns\s*:\s*\{")
# A 3-part dotted identifier inside backticks = hardcoded FQN.
_FQN_RX = re.compile(r"`[A-Za-z][\w\-]*\.[A-Za-z]\w*\.[A-Za-z]\w*`")
# FROM/JOIN pointing at a literal (not ${ref / ${self).
_LITERAL_FROM_RX = re.compile(r"\b(?:FROM|JOIN)\s+(?!\$\{)[A-Za-z`]")


def _config_block(text):
    """Return the substring inside the top-level `config { ... }`."""
    m = re.search(r"\bconfig\s*\{", text)
    if not m:
        return ""
    start = m.end() - 1  # at the '{'
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return text[start + 1:]


def _layer_of(rel_path):
    """Layer = the path segment right after `definitions/`.

    Works for real paths (transformation/dataform/definitions/silver/...) and for
    eval fixtures (evals/cases/bad/definitions/bronze/...).
    """
    parts = rel_path.replace("\\", "/").split("/")
    if "definitions" in parts:
        idx = parts.index("definitions")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def _iter_sqlx(paths):
    if paths:
        for p in paths:
            if p.endswith(".sqlx") and os.path.isfile(p):
                yield os.path.abspath(p)
        return
    base = os.path.join(REPO_ROOT, DEFINITIONS)
    if not os.path.isdir(base):
        return
    for dirpath, _dirs, files in os.walk(base):
        for name in files:
            if name.endswith(".sqlx"):
                yield os.path.join(dirpath, name)


def find_findings(paths=None):
    findings = []
    for full in _iter_sqlx(paths):
        rel = os.path.relpath(full, REPO_ROOT)
        layer = _layer_of(rel)
        try:
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        cfg = _config_block(text)
        typ = (_TYPE_RX.search(cfg).group(1) if _TYPE_RX.search(cfg) else None)
        body = text[text.find(cfg) + len(cfg):] if cfg else text

        def add(sev, rule, msg):
            findings.append({"severity": sev, "rule": rule, "path": rel,
                             "line": None, "message": msg})

        # Rule 2 — hardcoded references (check the query body, not config).
        if _FQN_RX.search(body) or _LITERAL_FROM_RX.search(body):
            if "${ref(" not in body and "${self(" not in body:
                add("error", "no-hardcoded-ref",
                    "Hardcoded table reference; use ${ref()} / ${self()} (rule 2).")

        # Rule 3 — bronze must MATERIALIZE (not a declaration/pointer or a view).
        if layer == "bronze" and typ in ("declaration", "view"):
            add("error", "bronze-must-materialize",
                f"Bronze must materialize data (type table/incremental), found '{typ}' (rule 3).")
        if layer == "bronze" and "WRITE_TRUNCATE" in text:
            add("error", "bronze-append-only",
                "WRITE_TRUNCATE on bronze; bronze is append-only (rule 3).")
        # Rule 3 — sources are declaration-only.
        if layer == "sources" and typ and typ != "declaration":
            add("error", "sources-declaration-only",
                f"Sources must be type 'declaration', found '{typ}' (rule 3).")

        # Rule 5 — staging is a view.
        if layer == "staging" and typ and typ != "view":
            add("error", "staging-view-only",
                f"Staging must be type 'view', found '{typ}' (rule 5).")

        # Rules 4 & 6 — silver/gold contracts (skip declarations/views).
        if layer in ("silver", "gold") and typ in ("table", "incremental"):
            if not (_ASSERT_RX.search(cfg) and _UNIQUEKEY_RX.search(cfg)):
                add("error", "assertions-required",
                    f"{layer} needs assertions with a uniqueKey (rule 4).")
            if not _DESC_RX.search(cfg):
                add("error", "description-required",
                    f"{layer} table needs a (Portuguese) description (rule 6).")
            if not _COLUMNS_RX.search(cfg):
                add("error", "column-docs-required",
                    f"{layer} table needs a columns{{}} block with PT descriptions (rule 6).")
    return findings


if __name__ == "__main__":
    found = find_findings(sys.argv[1:] or None)
    for f in found:
        loc = f["path"] + (f":{f['line']}" if f["line"] else "")
        print(f"{f['severity'].upper()} {loc} [{f['rule']}] {f['message']}")
    sys.exit(1 if any(f["severity"] == "error" for f in found) else 0)
