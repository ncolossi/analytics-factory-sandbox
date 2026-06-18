# API Ingestion — org overrides

> **How-to:** use the `cloud-run-basics` skill for Cloud Run jobs, builds, and
> deploys. This file is only our deltas. Flow:
> `API → Cloud Run Job → GCS landing → BigQuery bronze load (Composer)`.

## Hard rules

1. **Ingestion extracts raw data only — no transformation.** Cleaning/typing is
   Dataform's job.
2. **Idempotent.** Re-running with the same params overwrites the same GCS path;
   no duplicate output.
3. **Secrets via Secret Manager** mounted on the job (`--set-secrets`). Never in
   env vars, code, or the image.
4. The ingestion SA writes to the **landing bucket only** — never to BigQuery.

## Layout & naming

```
ingestion/cloudrun/{domain}/{source}/{Dockerfile,main.py,requirements.txt}
ingestion/cloudrun/common/{base.py,gcs_writer.py}
```

- Job name: `ingest-{domain}-{source}` (lowercase, hyphens).
- Landing path: `gs://{project}-data-landing/cloudrun/{domain}/{source}/{execution_date}/`.
- File format: `JSONL` for API data; `PARQUET` only when the source has a stable
  schema.

## Implementation contract

- Full **pagination** — never assume one call returns everything.
- Explicit HTTP `timeout` (default 30s); retry 429/5xx with exponential backoff.
- Params (`PROJECT_ID`, `EXECUTION_DATE`, URLs) via env vars injected by Composer
  `overrides`; static config on the job.
- Log to stdout/stderr (captured by Cloud Logging); exit 0 on success, non-zero
  on failure.

## Container

Slim base image, pinned dependency versions, no credentials baked in (use the
job's service account / Workload Identity). Images go to Artifact Registry:
`{region}-docker.pkg.dev/{project}/ingestion/ingest-{domain}-{source}:latest`.

## Composer integration

`CloudRunExecuteJobOperator(deferrable=True)`; pass `EXECUTION_DATE="{{ ds }}"`
for idempotency; do not duplicate the job's secrets in Composer. The bronze load
step that follows uses `WRITE_APPEND`. See [orchestration.md](orchestration.md).
