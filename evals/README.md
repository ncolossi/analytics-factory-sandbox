# Evals — agent & guardrail evaluation

Agent-level observability for this harness (separate from the *data/pipeline*
monitoring in `guidelines/project-topology.md`). Two layers:

## 1. Deterministic self-test (runs in CI, no LLM)

`python3 evals/run_evals.py`

- **Positive:** every file under `evals/golden/` must pass all guardrails with
  zero findings. These doubles as canonical "this is compliant" reference
  examples for the agent.
- **Negative:** every fixture under `evals/cases/bad/` must trip the specific
  rule it targets — so a regressed/disabled check fails the build.

```
evals/
├── golden/definitions/{sources,bronze,silver,gold}/...   # must pass clean
└── cases/bad/                                             # each must be caught
    ├── definitions/...   (hardcoded ref, bronze-as-declaration, source-as-table,
    │                       missing assertions, staging-as-table)
    └── scripts/...       (bq cp, hardcoded secret)
```

`evals/cases/` is excluded from the repo-wide scan so the bad fixtures don't fail
CI; `run_evals.py` targets them explicitly.

## 2. Golden tasks (periodic agent eval)

Natural-language tasks to run against the agent (Antigravity `/run-evals`, or any
tool) and grade by whether the generated assets pass `tools/checks/run_checks.py`.
Add new tasks here as the platform grows.

| # | Task | Pass criteria |
|---|------|---------------|
| 1 | "Add a `marketing` domain that ingests campaigns from a paginated REST API." | Cloud Run job `ingest-marketing-*`, raw input as a **source declaration**, **materialized bronze** (append-only), silver+gold with assertions & **Portuguese** descriptions, a `marketing__daily_refresh` DAG; `run_checks.py` clean. |
| 2 | "Create the silver `customers` table from `bronze_crm`." | Incremental, `uniqueKey`, dedup via `QUALIFY`, PT column docs, no hardcoded refs. |
| 3 | "Copy `silver_sales.customers` into `silver_finance`." | Implemented as a Dataform action tagged `data-copy` — **not** `bq cp`. |
| 4 | "Schedule the sales pipeline to run daily at 06:00." | Composer DAG only (no BigQuery scheduled query); `catchup=False`, `max_active_runs=1`. |

These tasks probe the failure modes the harness exists to prevent: skipping
assertions, English descriptions, hardcoded IDs, and bypassing Dataform.
