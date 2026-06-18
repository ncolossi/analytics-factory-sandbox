# Analytics Factory — Agent Constitution

> Canonical, tool-neutral instructions for any coding agent (Antigravity, Gemini
> CLI, Claude Code, Codex). This is the **single** instruction file — agents read
> `AGENTS.md` directly; Antigravity additionally loads `.agents/rules/` and
> `.agents/workflows/`.
>
> **Language policy:** all instructions and code are in **English**, with ONE
> exception — every BigQuery dataset/table/column **description must be written
> in Portuguese** (see Rule 6). That carve-out is deliberate, not an oversight.

## Mission

You build and maintain **data pipelines on Google Cloud** under a **Medallion
architecture** (Bronze → Silver → Gold), in a single GCP project, region
`southamerica-east1`.

- **Transformation engine of record:** Dataform (all BigQuery writes).
- **Orchestration:** Cloud Composer (Airflow).
- **API ingestion:** Cloud Run Jobs.

This is a **mono-repo**. Keep layers separate: `ingestion/`, `transformation/`,
`orchestration/` never import from each other.

## How to work here: skills + overrides

Do **not** reinvent tool how-to. Google's Data Agent Kit skills already encode
it. Invoke the right skill, then apply this repo's **org overrides** in
`guidelines/`.

**Skill routing**

| Your task | Invoke skill |
|-----------|--------------|
| "Where do I start / which tool?" | `gcp-data-pipelines` (router) |
| Build/modify transformations (SQLX, BigQuery ELT) | `dataform-bigquery` |
| API ingestion job (Cloud Run) | `cloud-run-basics` |
| DAGs / scheduling / Composer | `gcp-pipeline-orchestration` |
| Provision GCP resources | `gcp-pipeline-resource-provisioning` |
| Discover existing GCP data assets | `discovering-gcp-data-assets` |
| Data quality / cleaning | `data-autocleaning` |
| Composer is failing | `gcp-composer-troubleshooting` |
| Auth / credentials problems | `gcloud-auth-verification` |
| Python dependencies | `managing-python-dependencies` |

Skills live in `.agents/skills/` (the neutral cross-tool path). Our deltas on
top of each skill are in `guidelines/` — read the matching override file before
generating assets.

## Non-negotiable rules

These are enforced by **pre-commit + CI** (`tools/checks/`), not by trust.
A commit that breaks them fails the build for everyone — agent or human.

1. **Dataform is the only writer.** No `bq cp`, no manual `CREATE TABLE AS
   SELECT`, no BigQuery scheduled queries. Every BigQuery write goes through
   Dataform — except the initial bronze load job (GCS → BigQuery via Composer).
2. **Never hardcode** project IDs or table names in SQLX. Use `${ref()}`,
   `${self()}`, and `includes/constants.js`.
3. **Bronze is append-only** (`WRITE_APPEND`). Never `WRITE_TRUNCATE` a
   `bronze_*` table.
4. **Silver & Gold require assertions** (`uniqueKey`, `nonNull`).
5. **Staging is `type: "view"`** and is never consumed outside its own layer.
6. **Descriptions in Portuguese.** Every dataset, table, and — for silver/gold —
   every column must have a Portuguese `description` explaining business meaning
   (categorical values, currency, source).
7. **No secrets in code.** Use Secret Manager (Cloud Run) and Airflow
   Connections.
8. **No cross-layer imports.** `ingestion/`, `transformation/`, `orchestration/`
   are independent.

## Environment defaults

- **Region:** `southamerica-east1` for every resource.
- **Single project**, dev/prod separated by dataset suffix: prod `{layer}_{domain}`,
  dev `{layer}_{domain}_dev`.
- **Compile and run against `_dev` by default.** Production datasets are touched
  only through Dataform release configs — never manually.
- Naming: datasets `{layer}_{domain}`; DAGs `{domain}__{pipeline}`; Cloud Run
  jobs `ingest-{domain}-{source}`.

## Org overrides (read before creating assets)

| Topic | File |
|-------|------|
| Layers, naming, metadata columns, partitioning | `guidelines/lake-definition.md` |
| Dataform deltas (layout, assertions, incremental) | `guidelines/transformations.md` |
| Composer/Airflow deltas | `guidelines/orchestration.md` |
| Cloud Run ingestion deltas | `guidelines/api-ingestion.md` |
| GCP topology, IAM, service accounts | `guidelines/project-topology.md` |
| Mono-repo file placement | `guidelines/repo-structure.md` |

## Verify your work

Before declaring a task done, run the harness checks:

```bash
python3 tools/checks/run_checks.py        # forbidden patterns + SQLX validation
python3 evals/run_evals.py                # golden + negative cases
```

In Antigravity these are also available as `/review` and `/run-evals` workflows.
CI runs the same checks on every push.
