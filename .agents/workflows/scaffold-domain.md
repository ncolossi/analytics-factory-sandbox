# Scaffold a new data domain

Create all assets for a new business domain end to end, following this repo's
constitution. **Read [AGENTS.md](../../AGENTS.md) and the relevant
`guidelines/` override files first.**

Ask me for: the domain name, the source(s) (API or existing GCS/BigQuery), the
entities to model, **which layers** to build (bronze→silver→gold or a subset),
whether to **orchestrate** (a scheduled Composer DAG) or just do a **one-off data
movement** (run once, no DAG), and the **governance** inputs (data owners, data
stewards, source system + raw format for bronze, data sensitivity for gold).

Then, using the routed skills (do not hand-write what a skill already does):

1. **Ingestion** (only if an external API is the source) — use the
   `cloud-run-basics` skill. Create
   `ingestion/cloudrun/{domain}/{source}/{Dockerfile,main.py,requirements.txt}`.
   Follow [guidelines/api-ingestion.md](../../guidelines/api-ingestion.md):
   job `ingest-{domain}-{source}`, JSONL to landing, secrets via Secret Manager,
   idempotent, no transformation.
2. **Transformation** — use the `dataform-bigquery` skill. Create
   `transformation/dataform/definitions/{sources,bronze,silver,gold}/{domain}/...`.
   Follow [guidelines/transformations.md](../../guidelines/transformations.md):
   raw input as a `declaration` **source**; bronze **materialized** append-only;
   silver/gold = assertions + **Portuguese** descriptions; `${ref()}` only;
   incremental where it fits. Build **only the layers requested**.
3. **Orchestration** (only if a scheduled pipeline was requested) — use the
   `gcp-pipeline-orchestration` skill. Create
   `orchestration/airflow/dags/{domain}/daily_refresh.py` (`{domain}__daily_refresh`)
   per [guidelines/orchestration.md](../../guidelines/orchestration.md). Add the
   final `tag_governance` task so prod tables stay tagged.
4. **Governance** — use the `knowledge-catalog` skill. Add a `/* governance */`
   header to every materialized bronze/silver/gold `.sqlx` (owners, stewards;
   `source_system`+`raw_format` on bronze; `data_sensitivity` on gold) per
   [guidelines/data-governance.md](../../guidelines/data-governance.md). After the
   tables exist in dev, attach aspects:
   `python3 tools/governance/apply_aspects.py transformation/dataform/definitions/{bronze,silver,gold}/{domain}`.

Work in the **dev project**. When done, run `/review`, then `/run-evals`. Report
what you created and any guardrail findings.
