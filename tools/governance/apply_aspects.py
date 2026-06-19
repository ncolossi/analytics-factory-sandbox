#!/usr/bin/env python3
"""Attach Dataplex governance aspects to BigQuery tables — a thin gcloud wrapper.

For each materialized lake table (.sqlx under definitions/{bronze,silver,gold}),
this derives the aspect values from the file's `/* governance */` header + path
(see aspect_model.py) and attaches them to the table's auto-cataloged BigQuery
entry via `gcloud dataplex entries update --update-aspects`.

It NEVER creates aspect TYPES — those are Terraform-managed in location `global`.
By default it targets the **dev** project only (agents never touch prod; prod is
tagged by the Composer `tag_governance` task — see guidelines/orchestration.md).

Usage:
  python3 tools/governance/apply_aspects.py [--dry-run] [paths...]
  python3 tools/governance/apply_aspects.py --project P --region R [paths...]

With no paths, scans transformation/dataform/definitions. `--dry-run` prints the
resolved aspect payloads (and the gcloud commands) without calling GCP — safe and
network-free, so it works on the eval fixtures too.

Requires: gcloud (authenticated), the 5 custom aspect types deployed (Terraform),
and the BigQuery tables to already exist (Dataform/Composer create them first).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aspect_model  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("apply_aspects")

DEFAULT_PROJECT = "cymbal-data-platform-dev"   # dev project
DEFAULT_REGION = "southamerica-east1"          # BigQuery / entry location
BQ_ENTRY_GROUP = "@bigquery"
# Dataform repo backing every transformation (transformation-logic aspect).
DEFAULT_CODE_REPOSITORY = (
    "https://console.cloud.google.com/bigquery/dataform"
)


def _run(cmd):
    """Run a command, raising with captured stderr on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def resolve_project_number(project):
    """dev/prod project ID -> numeric project number (aspect-key prefix)."""
    return _run([
        "gcloud", "projects", "describe", project,
        "--format=value(projectNumber)",
    ])


def entry_name(project, dataset, table):
    """Deterministic entry id for an auto-cataloged BigQuery table."""
    return (f"bigquery.googleapis.com/projects/{project}"
            f"/datasets/{dataset}/tables/{table}")


def apply_one(parsed, project, region, project_number, code_repository, dry_run):
    aspects = aspect_model.build_aspects(parsed, project_number, code_repository)
    if not aspects:
        return False  # not a governed table
    dataset = parsed["schema"]
    table = parsed["name"] or parsed["entity"]
    if not dataset or not table:
        log.warning("skip %s: cannot resolve dataset/table from config", parsed["path"])
        return False
    entry = entry_name(project, dataset, table)

    if dry_run:
        log.info("[dry-run] %s -> %s.%s", parsed["path"], dataset, table)
        print(json.dumps(aspects, indent=2, ensure_ascii=False))
        return True

    with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(aspects, fh, ensure_ascii=False)
        aspects_file = fh.name
    try:
        _run([
            "gcloud", "dataplex", "entries", "update", entry,
            "--project", project,
            "--location", region,
            "--entry-group", BQ_ENTRY_GROUP,
            f"--update-aspects={aspects_file}",
        ])
        log.info("tagged %s.%s (%d aspects)", dataset, table, len(aspects))
    finally:
        os.unlink(aspects_file)
    return True


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*", help="specific .sqlx files (default: all)")
    ap.add_argument("--project", default=DEFAULT_PROJECT,
                    help=f"GCP project (default: {DEFAULT_PROJECT}, the dev project)")
    ap.add_argument("--region", default=DEFAULT_REGION,
                    help=f"BigQuery / entry location (default: {DEFAULT_REGION})")
    ap.add_argument("--code-repository", default=DEFAULT_CODE_REPOSITORY,
                    help="value for the transformation-logic aspect (silver)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print resolved aspects without calling GCP")
    args = ap.parse_args(argv)

    project_number = "PROJECT_NUMBER"
    if not args.dry_run:
        project_number = resolve_project_number(args.project)

    governed = 0
    for full in aspect_model.iter_sqlx(args.paths or None):
        parsed = aspect_model.parse_sqlx(full)
        if apply_one(parsed, args.project, args.region, project_number,
                     args.code_repository, args.dry_run):
            governed += 1

    log.info("%s %d governed table(s).",
             "would tag" if args.dry_run else "tagged", governed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
