# Agentic Data Development: Gemini Guidelines

This repository follows a strict architecture for building data pipelines using the **Medallion Architecture (Bronze -> Silver -> Gold)**. All data manipulation, ELT processes, and even data copies between datasets MUST be executed through **Dataform**, orchestrated via **Cloud Composer (Airflow)**, and infrastructure managed via **Terraform**.

Whenever you are generating code or assisting in this repository, you MUST adhere to the following development methods and rules outlined in the `guidelines/` documentation.

## Core Principles

1. **Dataform is the Engine**:
   - **Toda operação de dados que envolva o BigQuery deve ser implementada exclusivamente via Dataform.**
   - Do NOT use `bq cp`, manual `CREATE TABLE AS SELECT`, scheduled queries, or generic SQL scripts.
   - You must use incremental materializations whenever possible. Full refresh should be restricted to small dimension tables or initial bootstrap.
   - Reference all tables using `${ref("schema", "table")}` or `${self()}` in incremental queries.
   - Never hardcode table names.

2. **Mono-Repo Architecture**:
   - **Infrastructure**: Only Terraform configurations belong in `infra/terraform/`.
   - **Transformation**: Only Dataform ELT logic belongs in `transformation/dataform/definitions/`.
   - **Orchestration**: Only Airflow DAGs and utility scripts belong in `orchestration/airflow/`.
   - Ensure strict separation of concerns. Do not mix code from different layers.

## The Medallion Lakehouse

- **Bronze (Raw)**: Schema-on-read, no transformations, append-only. Must include `_ingestion_timestamp`, `_source_file`, and `_batch_id`. Dataform configs should be `type: "declaration"`.
- **Silver (Cleaned)**: Deduplicated, typed, and conformed data. Uses `type: "table"` or `type: "incremental"`. Must include `_loaded_at` and `_source_table`. Include Dataform assertions (`uniqueKey`, `nonNull`).
- **Gold (Business-Ready)**: Aggregated, modeled (dim, fact, agg). Uses `type: "table"` or `type: "incremental"`. Must include `_last_updated_at`. Include Dataform assertions.
- **Staging**: Intermediate logic. Must be `type: "view"`. Never consumed outside of its own layer.

## Nomenclatures and Organization

- **Datasets**: `{layer}_{domain}` (e.g., `bronze_erp`, `silver_sales`, `gold_finance`).
- **Tables**: Plural nouns for entities (`orders`, `customers`). Gold layer uses prefixes: `dim_`, `fact_`, `agg_`. Staging uses `stg_`.
- **Files**:
  - One Dataform `.sqlx` file per table, named exactly as the output table.
  - One Airflow DAG per `.py` file, named `{domain}__{pipeline}`.

## Domain Mirroring

Domains must be mirrored across `transformation` and `orchestration` directories. If a `sales` domain exists in Dataform, there must be a corresponding `sales` folder in Airflow DAGs.

Example:
`transformation/dataform/definitions/silver/sales/` -> `orchestration/airflow/dags/sales/`

## Before Creating New Assets

Always refer to the specific documentation files in `guidelines/` for deep-dives:
- `guidelines/lake-definition.md`: For Medallion layer specifics, naming conventions, clustering, partitioning, and mandatory metadata columns.
- `guidelines/transformations.md`: For Dataform specifics, incremental materialization patterns, assertions, macros, and SQL styling.
- `guidelines/orchestration.md`: For Composer/Airflow DAG creation rules (if requested).
- `guidelines/project-topology.md`: For GCP topology.
- `guidelines/repo-structure.md`: For exact file paths and mono-repo rules.
