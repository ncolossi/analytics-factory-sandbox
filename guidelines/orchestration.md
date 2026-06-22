# Orchestration — org overrides

> **How-to:** use the `gcp-pipeline-orchestration` skill for DAG/operator
> mechanics. This file is only our deltas. Cloud Composer (Airflow) is the single
> orchestration layer; Dataform owns transformation logic, Composer owns *when*,
> *in what order*, and *what to do on failure*.

## Hard rules

1. **DAGs do not write to BigQuery** except the **raw load** into a landing/source
   table (`BigQueryInsertJobOperator`, `WRITE_APPEND`). Bronze and all transforms
   are Dataform invocations.
2. **One DAG per file**; `dag_id` == filename; pattern `{domain}__{pipeline}`
   (e.g. `sales__daily_refresh`).
3. **No secrets in DAGs.** Use Airflow Connections / Variables.

## Layout

```
orchestration/airflow/dags/{domain}/{pipeline}.py
orchestration/airflow/dags/common/utils.py
orchestration/airflow/scripts/*.sh        # ops only, not pipeline runtime
```

## DAG defaults

```python
default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "on_failure_callback": notify_on_failure,
}
# DAG: catchup=False, max_active_runs=1, cron schedule_interval,
# tags=[domain, cadence], doc_md=__doc__
```

## Pipeline shape

Task groups: **(extraction →) raw load (GCS→landing/source) → Dataform
(bronze → silver → gold) → tag_governance**. Pattern:
`compile_{layer}` (`DataformCreateCompilationResultOperator`, `git_commitish:
main` for prod) `>> run_{layer}` (`DataformCreateWorkflowInvocationOperator`).

The final **`tag_governance`** task runs after the last Dataform layer and
attaches Dataplex aspects to the tables it just (re)created — keeping prod
metadata in sync without manual steps.

**The worker has no `.sqlx`.** Composer only syncs `dags/`/`plugins/`/`data/`;
the Dataform definitions live in the Dataform service, never on the worker. So
the task reads a **precomputed manifest** instead of parsing SQLX:
`emit_manifest.py` runs in CI (and is drift-checked there), and the deploy ships
`governance_manifest.json` + `aspect_model.py` + `apply_aspects.py` into the
Composer bucket under `dags/governance/`.

```python
tag_governance = BashOperator(
    task_id="tag_governance",
    bash_command=(
        "python3 $AIRFLOW_HOME/dags/governance/apply_aspects.py "
        "--manifest $AIRFLOW_HOME/dags/governance/governance_manifest.json "
        "--project {{ var.value.gcp_project }} "
        "--region southamerica-east1"
    ),
)
run_gold >> tag_governance
```

The manifest is env-neutral; `--project` selects dev/prod and the script resolves
the project number + code repo at run time. `composer-sa` needs
`roles/dataplex.catalogEditor` (see [project-topology.md](project-topology.md)).
Never hand-run aspect tagging against prod. See
[data-governance.md](data-governance.md).

Filter each invocation by tags + resolve upstream automatically:

```python
"invocation_config": {
    "included_tags": ["silver", "sales"],
    "transitive_dependencies_included": True,
}
```

Tags must match the Dataform SQLX tags in [transformations.md](transformations.md).

## Ingestion tasks

Trigger Cloud Run jobs with `CloudRunExecuteJobOperator(deferrable=True)`, pass
dynamic params via `overrides` (e.g. `EXECUTION_DATE="{{ ds }}"`); secrets stay
on the job, not the DAG. Then load GCS→landing/source table with `WRITE_APPEND`,
and let Dataform materialize bronze. Details in [api-ingestion.md](api-ingestion.md).

## Style

PEP 8; type hints in `common/`; keep DAGs thin (business logic belongs to
Dataform); descriptive snake_case task ids; module docstring + `doc_md=__doc__`.
Environment values (project, region, buckets) come from Airflow Variables or
`common/utils.py`, never hardcoded across files.
