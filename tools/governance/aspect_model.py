#!/usr/bin/env python3
"""Governance metadata model — the single source of truth shared by:

  - tools/checks/validate_governance.py  (presence/consistency checks in CI)
  - tools/governance/apply_aspects.py    (attaches aspect VALUES to BQ entries)

Pure stdlib (no PyYAML): runs anywhere with no install, like the other checks.

## Where governance values live
Dataform's `config { ... }` block rejects unknown keys, so governance values
live in a leading **comment header** OUTSIDE it, at the top of each `.sqlx`:

    /* governance
    data_owners: [Ana Lima <ana@corp.com>, ops@corp.com]
    data_stewards: [maria@corp.com]
    source_system: ERP                 # bronze only
    raw_format: JSONL                  # bronze only
    data_sensitivity: CONFIDENTIAL     # gold only
    */
    config { type: "incremental", schema: "bronze_erp", name: "orders", ... }

`tier`, `domain_name` and `code_repository` are DERIVED (path / repo) and need
not be written; if written they must match (the validator flags a mismatch).

## The aspect catalog (verified against cymbal-data-platform-dev)
The 5 custom aspect types are DEFINED by Terraform in location `global`
(`goog-terraform-provisioned: true`). This repo only attaches values — it never
creates the types. Verified IDs (hyphenated) / record fields:

  medallion-tier       record `tier`           tier (enum BRONZE/SILVER/GOLD, required)   -> ALL layers
  data-provenance      record `provenance`     source_system, raw_format                  -> BRONZE
  transformation-logic record `transformation` code_repository                            -> SILVER
  business-governance  record `governance`     data_sensitivity                           -> GOLD
  domain               record `domain`         domain_name (required)                     -> GOLD

Plus the 1P contacts aspect `dataplex-types.global.contacts`
(record `identities`: array of {role, name (required), id}) -> ALL layers.
The Data Quality Scorecard aspect is populated automatically by Dataplex
data-quality scans, not by this code (see guidelines/data-governance.md).
"""
from __future__ import annotations

import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFINITIONS = os.path.join("transformation", "dataform", "definitions")

# Layer -> medallion_tier enum value.
LAYER_TO_TIER = {"bronze": "BRONZE", "silver": "SILVER", "gold": "GOLD"}
# Only these layers carry governance aspects (sources/staging do not).
GOVERNANCE_LAYERS = ("bronze", "silver", "gold")
# Custom aspect type IDs (location `global`), as deployed by Terraform.
CUSTOM_ASPECT_IDS = (
    "medallion-tier", "data-provenance", "transformation-logic",
    "business-governance", "domain",
)
CONTACTS_ASPECT_KEY = "dataplex-types.global.contacts"

_TYPE_RX = re.compile(r"\btype\s*:\s*['\"](\w+)['\"]")
_SCHEMA_RX = re.compile(r"\b(?:schema|dataset)\s*:\s*['\"]([^'\"]+)['\"]")
_NAME_RX = re.compile(r"\bname\s*:\s*['\"]([^'\"]+)['\"]")
_HEADER_RX = re.compile(r"/\*\s*governance\b(.*?)\*/", re.DOTALL | re.IGNORECASE)
_EMAIL_RX = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_NAMED_RX = re.compile(r"^\s*(.*?)\s*<\s*([^>]+?)\s*>\s*$")


# --- small SQLX helpers (kept local so this module stands alone) -------------

def _config_block(text):
    """Return the substring inside the top-level `config { ... }`."""
    m = re.search(r"\bconfig\s*\{", text)
    if not m:
        return ""
    start = m.end() - 1
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return text[start + 1:]


def layer_of(rel_path):
    """Layer = the path segment right after `definitions/` (works for evals too)."""
    parts = rel_path.replace("\\", "/").split("/")
    if "definitions" in parts:
        idx = parts.index("definitions")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def domain_of(rel_path):
    """Domain = the path segment after the layer (definitions/<layer>/<domain>/...)."""
    parts = rel_path.replace("\\", "/").split("/")
    if "definitions" in parts:
        idx = parts.index("definitions")
        if idx + 2 < len(parts):
            return parts[idx + 2]
    return None


def iter_sqlx(paths):
    """Yield absolute paths to .sqlx files (explicit list, or the definitions tree)."""
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


# --- governance header parsing ----------------------------------------------

def parse_header(text):
    """Parse the `/* governance ... */` block into a dict.

    Supports `key: scalar` and `key: [a, b, c]`. Trailing ` # comments` are
    stripped. Returns {} when no header is present.
    """
    m = _HEADER_RX.search(text)
    if not m:
        return {}
    out = {}
    for raw in m.group(1).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = re.sub(r"\s+#.*$", "", val).strip()  # strip trailing comment
        if val.startswith("[") and val.endswith("]"):
            items = [v.strip() for v in val[1:-1].split(",")]
            out[key] = [v for v in items if v]
        else:
            out[key] = val
    return out


def parse_sqlx(path):
    """Read a .sqlx file into a structured dict used by validation + apply."""
    rel = os.path.relpath(os.path.abspath(path), REPO_ROOT)
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        text = fh.read()
    cfg = _config_block(text)
    return {
        "path": rel,
        "layer": layer_of(rel),
        "domain": domain_of(rel),
        "entity": os.path.splitext(os.path.basename(rel))[0],
        "type": (_TYPE_RX.search(cfg).group(1) if _TYPE_RX.search(cfg) else None),
        "schema": (_SCHEMA_RX.search(cfg).group(1) if _SCHEMA_RX.search(cfg) else None),
        "name": (_NAME_RX.search(cfg).group(1) if _NAME_RX.search(cfg) else None),
        "header": parse_header(text),
    }


def _governed(parsed):
    """True when this file is a materialized lake table that must carry aspects."""
    return (parsed["layer"] in GOVERNANCE_LAYERS
            and parsed["type"] in ("table", "incremental"))


def _identity(raw, role):
    """Turn a header entry ('Ana <a@x>', 'a@x', or 'Ana') into a contacts identity.

    The contacts aspect requires role + name; id (email) is optional.
    """
    named = _NAMED_RX.match(raw)
    if named:
        return {"role": role, "name": named.group(1) or named.group(2),
                "id": named.group(2)}
    if _EMAIL_RX.fullmatch(raw.strip()):
        return {"role": role, "name": raw.strip(), "id": raw.strip()}
    return {"role": role, "name": raw.strip(), "id": ""}


# --- validation (consumed by tools/checks/validate_governance.py) -----------

def governance_issues(parsed):
    """Return [(rule, message), ...] for a parsed .sqlx; empty when compliant.

    Only materialized bronze/silver/gold tables are checked.
    """
    if not _governed(parsed):
        return []
    layer = parsed["layer"]
    h = parsed["header"]
    issues = []
    if not h:
        return [("governance-header-required",
                 f"{layer} table needs a /* governance */ header "
                 "(data_owners, data_stewards).")]

    def _nonempty_list(key):
        v = h.get(key)
        return isinstance(v, list) and len([x for x in v if x]) > 0 or (
            isinstance(v, str) and v.strip() != "")

    if not _nonempty_list("data_owners"):
        issues.append(("governance-owners-required",
                       f"{layer} table needs data_owners in the governance header "
                       "(rendered as Dataplex contacts)."))
    if not _nonempty_list("data_stewards"):
        issues.append(("governance-stewards-required",
                       f"{layer} table needs data_stewards in the governance header "
                       "(rendered as Dataplex contacts)."))
    if layer == "bronze":
        if not h.get("source_system"):
            issues.append(("governance-provenance-required",
                           "bronze table needs source_system (data_provenance aspect)."))
        if not h.get("raw_format"):
            issues.append(("governance-provenance-required",
                           "bronze table needs raw_format (data_provenance aspect)."))
    if layer == "gold" and not h.get("data_sensitivity"):
        issues.append(("governance-sensitivity-required",
                       "gold table needs data_sensitivity (business_governance aspect)."))

    # Consistency: explicit derived values must match the path.
    tier = h.get("tier")
    if isinstance(tier, str) and tier and tier.upper() != LAYER_TO_TIER[layer]:
        issues.append(("governance-tier-mismatch",
                       f"header tier '{tier}' != layer '{layer}' "
                       f"({LAYER_TO_TIER[layer]})."))
    dom = h.get("domain_name")
    if isinstance(dom, str) and dom and parsed["domain"] and dom != parsed["domain"]:
        issues.append(("governance-domain-mismatch",
                       f"header domain_name '{dom}' != path domain "
                       f"'{parsed['domain']}'."))
    return issues


# --- aspect payload construction (consumed by apply_aspects.py) --------------

def build_aspects(parsed, project_number, code_repository):
    """Build the Dataplex `aspects` map (key -> {data: {...}}) for one table.

    Keys for custom types are `{project_number}.global.<id>`; the 1P contacts
    type uses its system key. Returns {} for non-governed files.
    """
    if not _governed(parsed):
        return {}
    layer = parsed["layer"]
    h = parsed["header"]
    prefix = f"{project_number}.global."
    aspects = {}

    # medallion-tier + contacts -> every lake table.
    aspects[prefix + "medallion-tier"] = {"data": {"tier": LAYER_TO_TIER[layer]}}

    owners = h.get("data_owners") or []
    stewards = h.get("data_stewards") or []
    if isinstance(owners, str):
        owners = [owners]
    if isinstance(stewards, str):
        stewards = [stewards]
    identities = ([_identity(o, "owner") for o in owners]
                  + [_identity(s, "steward") for s in stewards])
    if identities:
        aspects[CONTACTS_ASPECT_KEY] = {"data": {"identities": identities}}

    if layer == "bronze":
        data = {}
        if h.get("source_system"):
            data["source_system"] = h["source_system"]
        if h.get("raw_format"):
            data["raw_format"] = h["raw_format"]
        aspects[prefix + "data-provenance"] = {"data": data}
    elif layer == "silver":
        aspects[prefix + "transformation-logic"] = {
            "data": {"code_repository": code_repository}}
    elif layer == "gold":
        aspects[prefix + "business-governance"] = {
            "data": {"data_sensitivity": h.get("data_sensitivity", "")}}
        domain = h.get("domain_name") or parsed["domain"] or ""
        aspects[prefix + "domain"] = {"data": {"domain_name": domain}}

    return aspects
