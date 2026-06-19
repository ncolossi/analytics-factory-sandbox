# Repo Structure — org overrides

Mono-repo for the whole platform: harness config, ingestion, transformation,
orchestration. Strict separation of concerns.

## Tree

```
analytics-factory-sandbox/
│
├── AGENTS.md                     # canonical agent constitution (single instruction file)
│
├── guidelines/                   # org overrides on top of the DAK skills
│   ├── lake-definition.md  transformations.md  orchestration.md
│   ├── api-ingestion.md    project-topology.md  repo-structure.md
│
├── .agents/                      # all agent config + skills (always PLURAL)
│   ├── rules/                    #   supplemental workspace rules (optional)
│   ├── workflows/                #   slash-command procedures (*.md)
│   └── skills/                   #   DAK + Cloud Run skills (cross-tool)
│
├── tools/checks/                 # portable guardrails (pre-commit + CI)
│   ├── run_checks.py  forbidden_patterns.py  validate_dataform.py
├── evals/                        # golden + negative cases + runner
├── .pre-commit-config.yaml       # local enforcement
├── .github/workflows/ci.yml      # authoritative enforcement
│
├── ingestion/cloudrun/{domain}/{source}/   # Dockerfile, main.py, requirements.txt
├── transformation/dataform/
│   ├── workflow_settings.yaml
│   ├── definitions/{sources,bronze,silver,gold,staging}/{domain}/{entity}.sqlx
│   └── includes/{constants,helpers}.js
└── orchestration/airflow/
    ├── dags/{domain}/{pipeline}.py   dags/common/utils.py
    └── scripts/*.sh
```

> Everything agent-related lives under `.agents/` (always **plural**): `rules/`,
> `workflows/`, and `skills/`. There is no singular `.agent/` folder.

## Asset placement

| Asset | Path | Name |
|-------|------|------|
| API ingestion job | `ingestion/cloudrun/{domain}/{source}/` | `Dockerfile` + `main.py` |
| Source declaration | `transformation/dataform/definitions/sources/{domain}/` | `{entity}.sqlx` (type `declaration`) |
| Bronze (materialized) | `transformation/dataform/definitions/bronze/{domain}/` | `{entity}.sqlx` (table/incremental) |
| Silver model | `…/definitions/silver/{domain}/` | `{entity}.sqlx` |
| Gold model | `…/definitions/gold/{domain}/` | `{fact\|dim\|agg}_{entity}.sqlx` |
| Staging (view) | `…/definitions/staging/{domain}/` | `stg_{entity}.sqlx` |
| SQL macro/helper | `transformation/dataform/includes/` | `{name}.js` |
| Domain DAG | `orchestration/airflow/dags/{domain}/` | `{pipeline}.py` |
| Ops script | `orchestration/airflow/scripts/` | `{action}.sh` |

## Mono-repo rules

1. **Mirror domains** across the layers that apply (ingestion if API-sourced,
   transformation, orchestration).
2. **One file per table** (Dataform) and **one DAG per file** (Airflow).
3. **No cross-layer imports** — `ingestion/`, `transformation/`, `orchestration/`
   are independent.
4. **Python:** whenever Python is needed, always create/use a virtualenv at
   `.venv/` — never install globally (`.venv/` is gitignored).

## New domain checklist

`ingestion/cloudrun/{domain}/{source}/` (if API) →
`transformation/dataform/definitions/{sources,bronze,silver,gold}/{domain}/` →
`orchestration/airflow/dags/{domain}/daily_refresh.py`. The `/scaffold-domain`
workflow automates this.

## Not in the repo

Credentials/secrets (Secret Manager, Airflow Connections), business data
(BigQuery/GCS), IDE config (local).
