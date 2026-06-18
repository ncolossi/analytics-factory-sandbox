# Scaffold a new data domain

Create all assets for a new business domain end to end, following this repo's
constitution. **Read [AGENTS.md](../../AGENTS.md) and the relevant
`guidelines/` override files first.**

Ask me for: the domain name, the source(s) (API or existing GCS/BigQuery), and
the entities to model.

Then, using the routed skills (do not hand-write what a skill already does):

1. **Ingestion** (only if an external API is the source) — use the
   `cloud-run-basics` skill. Create
   `ingestion/cloudrun/{domain}/{source}/{Dockerfile,main.py,requirements.txt}`.
   Follow [guidelines/api-ingestion.md](../../guidelines/api-ingestion.md):
   job `ingest-{domain}-{source}`, JSONL to landing, secrets via Secret Manager,
   idempotent, no transformation.
2. **Transformation** — use the `dataform-bigquery` skill. Create
   `transformation/dataform/definitions/{bronze,silver,gold}/{domain}/...`.
   Follow [guidelines/transformations.md](../../guidelines/transformations.md):
   bronze = declaration; silver/gold = assertions + **Portuguese** descriptions;
   `${ref()}` only; incremental where it fits.
3. **Orchestration** — use the `gcp-pipeline-orchestration` skill. Create
   `orchestration/airflow/dags/{domain}/daily_refresh.py` (`{domain}__daily_refresh`)
   per [guidelines/orchestration.md](../../guidelines/orchestration.md).

Target `_dev` datasets. When done, run `/review`, then `/run-evals`. Report what
you created and any guardrail findings.
