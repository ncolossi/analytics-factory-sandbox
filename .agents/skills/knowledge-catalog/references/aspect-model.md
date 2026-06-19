# Aspect model reference (verified deployment)

Authoritative field schema for the Dataplex aspects used by this lakehouse,
verified against `cymbal-data-platform-dev` (project number `261451122555`).
The single source of truth in code is
[`tools/governance/aspect_model.py`](../../../../tools/governance/aspect_model.py).

## Custom aspect types (Terraform-managed, location `global`)

IDs are **hyphenated** (the original design doc's underscores were wrong). This
repo attaches values only; it never creates these types.

| Aspect type ID | Record name | Fields (type) | Layers | Source of value |
|----------------|-------------|---------------|--------|-----------------|
| `medallion-tier` | `tier` | `tier` enum **BRONZE/SILVER/GOLD** (required) | all | derived from layer folder |
| `data-provenance` | `provenance` | `source_system` (string), `raw_format` (string) | bronze | header |
| `transformation-logic` | `transformation` | `code_repository` (string) | silver | constant (Dataform repo) |
| `business-governance` | `governance` | `data_sensitivity` (string) | gold | header |
| `domain` | `domain` | `domain_name` (string, required) | gold | derived from domain folder (overridable in header) |

Aspect-map key (in `--update-aspects` payloads): `{project_number}.global.<id>`,
e.g. `261451122555.global.medallion-tier`.

## First-party (1P) aspects

| Aspect type | Key | Shape | How it's set |
|-------------|-----|-------|--------------|
| Contacts | `dataplex-types.global.contacts` | `identities[]` of `{role, name (required), id}`; role ∈ owner/steward/producer/admin | `apply_aspects.py` from `data_owners`/`data_stewards` |
| Data Quality Scorecard | `dataplex-types.global.data-quality-scorecard` | populated by Dataplex | a **data-quality scan** on the table (not this code) |

## Example payload (gold table)

```json
{
  "261451122555.global.medallion-tier": { "data": { "tier": "GOLD" } },
  "dataplex-types.global.contacts": {
    "data": { "identities": [
      { "role": "owner", "name": "Equipe de Vendas", "id": "sales-data@corp.com" },
      { "role": "steward", "name": "maria.steward@corp.com", "id": "maria.steward@corp.com" }
    ] }
  },
  "261451122555.global.business-governance": { "data": { "data_sensitivity": "CONFIDENTIAL" } },
  "261451122555.global.domain": { "data": { "domain_name": "sales" } }
}
```

## BigQuery entry addressing

BigQuery tables auto-register as Dataplex entries in the `@bigquery` entry group,
in the table's BigQuery region. The entry id is deterministic:

```
bigquery.googleapis.com/projects/{project}/datasets/{dataset}/tables/{table}
```

So the attach call is:

```bash
gcloud dataplex entries update \
  "bigquery.googleapis.com/projects/PROJECT/datasets/DATASET/tables/TABLE" \
  --project PROJECT --location southamerica-east1 --entry-group @bigquery \
  --update-aspects=aspects.json
```

`--update-aspects` merges (only the listed keys change), so re-running is
idempotent.
