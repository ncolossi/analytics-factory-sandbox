# Project Topology — org overrides

> Single GCP project, region `southamerica-east1` for **every** resource
> (BigQuery datasets, Dataform repo, Composer env, GCS buckets). Provisioning
> how-to: `gcp-pipeline-resource-provisioning` skill.

## Services

| Service | Role | Notes |
|---------|------|-------|
| **BigQuery** | Warehouse for all layers | Datasets `{layer}_{domain}`, same location; descriptions in Portuguese |
| **Dataform** | Only writer to BigQuery (except bronze load) | One repo; workspace per dev/branch; default location matches BigQuery |
| **Cloud Composer 2** | Orchestration | Autoscaling defaults; same region |
| **Cloud Run Jobs** | API ingestion | Images in Artifact Registry `ingestion/`; secrets via Secret Manager |
| **Artifact Registry** | Docker images | Repo `ingestion` (Docker), same region |
| **Cloud Storage** | Landing / export staging (support role, not a lake layer) | `{project}-data-{purpose}` |

## IAM (least privilege)

| Service Account | Purpose | Key roles |
|-----------------|---------|-----------|
| `dataform-sa` | Run Dataform | `bigquery.dataEditor`, `bigquery.jobUser` |
| `composer-sa` | Orchestrate | `composer.worker`, `dataform.editor`, `bigquery.jobUser`, `run.invoker` |
| `ingestion-sa` | Run ingestion jobs | `storage.objectCreator` (landing), `secretmanager.secretAccessor` |

- No user account writes directly to any lake dataset — all writes go through
  service accounts via Dataform.
- Bronze: write = ingestion SAs; read = Dataform SA. Silver: write = Dataform SA.
  Gold: write = Dataform SA; read = consumers (BI/analysts/ML) via `dataViewer`.

## Environments (one project, dataset suffixes)

| Env | Dataset pattern | Rules |
|-----|-----------------|-------|
| Production | `{layer}_{domain}` | Modified only through Dataform release configs |
| Development | `{layer}_{domain}_dev` | Ephemeral; default compile/run target |

**Agents compile and run against `_dev` by default.** Production is never touched
manually.

## Observability (data/pipeline runtime)

- BigQuery: `INFORMATION_SCHEMA.JOBS` / `TABLE_STORAGE`, audit logs, slot usage.
- Dataform: workflow invocation status; failed assertions must alert.
- Composer: DAG/task success & duration; scheduler health via Cloud Monitoring.
- Alerts: pipeline failures (`on_failure_callback` + Monitoring), assertion
  failures (block downstream), cost anomalies (budget alerts).

> Agent-level observability (token cost, eval pass-rate, drift) is separate — see
> `evals/` and CI.
