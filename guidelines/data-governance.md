# Data Governance — org overrides

> **How-to:** use the `knowledge-catalog` skill for attaching Dataplex aspects and
> the exact field reference. This file is the org **contract**: what every lake
> table must declare and when it gets tagged. Governance runs on **Dataplex
> Knowledge Catalog** — five org-specific custom aspects plus two first-party (1P)
> aspects that render natively in the Dataplex UI.

## Hard rules (enforced by `tools/checks/`)

1. **Every materialized lake table carries governance aspects.** Each
   bronze/silver/gold `.sqlx` must have a `/* governance */` header supplying the
   layer's required fields. `validate_governance.py` fails the build otherwise.
2. **Header lives outside `config {}`.** Dataform rejects unknown `config` keys,
   so governance values go in a leading comment block (see below).
3. **Aspect *types* are Terraform-managed — never created from this repo.** They
   already exist in location `global`. We attach **values** only.
4. **Tagging is automated, via a manifest.** Aspects are attached by the Dataplex
   API (gcloud), never from SQL. Dev: run `tools/governance/apply_aspects.py`.
   Prod: the Composer `tag_governance` task. Agents tag only the **dev** project.

## The aspect catalog

| Aspect | Type | Layers | Value comes from |
|--------|------|--------|------------------|
| Medallion Tier | `medallion-tier` (custom) | all | layer folder (derived) |
| Data Provenance | `data-provenance` (custom) | bronze | header: `source_system`, `raw_format` |
| Transformation Logic | `transformation-logic` (custom) | silver | Dataform repo (constant) |
| Business Governance | `business-governance` (custom) | gold | header: `data_sensitivity` |
| Business Domain | `domain` (custom) | gold | domain folder (derived) |
| Contacts | `dataplex-types.global.contacts` (1P) | all | header: `data_owners`, `data_stewards` |
| Data Quality Scorecard | `dataplex-types.global.data-quality-scorecard` (1P) | silver/gold | Dataplex DQ scan (auto) |

Custom aspect type IDs are **hyphenated** and live in location `global`. Full
field schema: `knowledge-catalog` skill → `references/aspect-model.md`.

## The governance header

```sqlx
/* governance
data_owners: [Equipe de Vendas <sales-data@corp.com>]
data_stewards: [maria.steward@corp.com]
source_system: ERP                 # bronze only
raw_format: JSONL                  # bronze only
data_sensitivity: CONFIDENTIAL     # gold only
*/
config { type: "incremental", schema: "silver_sales", name: "orders", ... }
```

- `data_owners` / `data_stewards`: one+ entries, `Name <email>` or bare `email`.
- `tier`, `domain_name`, `code_repository` are **derived** — don't write them; if
  you do, they must match the path (validator flags a mismatch).

### Required fields per layer

| Layer | Required |
|-------|----------|
| Bronze | `data_owners`, `data_stewards`, `source_system`, `raw_format` |
| Silver | `data_owners`, `data_stewards` |
| Gold | `data_owners`, `data_stewards`, `data_sensitivity` |

Sources (`declaration`) and staging (views) are not tagged.

## How tagging runs (the manifest)

Aspects are a Dataplex **control-plane** operation — they can't be set from
Dataform/BigQuery SQL. They're attached by `apply_aspects.py` (a `gcloud` wrapper)
right after the tables exist. Because the Composer worker has no `.sqlx` (only
`dags/` syncs), tagging runs off a precomputed, env-neutral **manifest**:

```
emit_manifest.py  (CI)   ──>  tools/governance/governance_manifest.json
                                      │  shipped into the Composer bucket
                                      ▼            dags/governance/
apply_aspects.py --manifest ──>  gcloud dataplex entries update  (dev & prod)
```

- **Generate:** `python3 tools/governance/emit_manifest.py` parses every governed
  `.sqlx` once and writes `governance_manifest.json` (a list of
  `{layer, schema, name, header, …}` records). It refuses to emit on any invalid
  header. CI regenerates it and **fails on drift**, so the committed manifest is
  always in sync with the SQLX.
- **Apply (dev):** `python3 tools/governance/apply_aspects.py` — parses SQLX
  directly (no manifest needed locally), `--dry-run` to preview.
- **Apply (prod):** the Composer `tag_governance` task runs
  `apply_aspects.py --manifest …/governance_manifest.json --project <env>`. The
  manifest is env-neutral; the project number, region, and code repo are bound at
  run time. See [orchestration.md](orchestration.md).

## Provenance comes from ingestion

`source_system` and `raw_format` on a bronze table must reflect the actual
ingestion source and landing format (e.g. `JSONL` for API data per
[api-ingestion.md](api-ingestion.md)). Keep them in sync with the Cloud Run job
that produced the data.

## Data Quality Scorecard

The scorecard renders automatically once a Dataplex **data-quality scan** exists
on a silver/gold table — it is not attached by `apply_aspects.py`. Create a DQ
scan (build on the `data-autocleaning` scanner pattern) for tables that should
surface a health score.

## Language note

Aspect *values* (domain names, sensitivity labels, system names) follow the
business vocabulary. The Portuguese-description rule (lake-definition Rule 6) is
unchanged and independent of aspects.
