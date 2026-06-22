#!/usr/bin/env python3
"""Generate the env-neutral governance manifest from the Dataform SQLX tree.

Run this where the `.sqlx` files exist (CI / a repo checkout). The manifest is
consumed at apply time where the SQLX is NOT available — the Composer worker that
runs the `tag_governance` task reads it via `apply_aspects.py --manifest`. See
guidelines/orchestration.md and guidelines/data-governance.md.

It REFUSES to emit if any governed table has an invalid governance header (the
same gate as tools/checks/validate_governance.py), so a bad header can never
slip into a manifest. CI also regenerates and diffs this file to catch drift.

Usage:
  python3 tools/governance/emit_manifest.py [-o OUTFILE] [paths...]

With no paths it scans transformation/dataform/definitions. Default OUTFILE is
tools/governance/governance_manifest.json (the artifact shipped with the DAGs).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aspect_model  # noqa: E402

DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "governance_manifest.json")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*", help="specific .sqlx files (default: all)")
    ap.add_argument("-o", "--output", default=DEFAULT_OUT,
                    help=f"output file (default: {DEFAULT_OUT})")
    args = ap.parse_args(argv)

    manifest = aspect_model.build_manifest(args.paths or None)

    issues = []
    for rec in manifest["tables"]:
        for rule, msg in aspect_model.governance_issues(rec):
            issues.append(f"{rec['path']} [{rule}] {msg}")
    if issues:
        print("Refusing to emit manifest — governance issues:", file=sys.stderr)
        for line in issues:
            print(f"  {line}", file=sys.stderr)
        return 1

    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"Wrote {args.output}: {len(manifest['tables'])} governed table(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
