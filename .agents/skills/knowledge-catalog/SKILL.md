---
name: knowledge-catalog
description: |
  Attach Dataplex Knowledge Catalog governance aspects to BigQuery lake tables
  (Analytics Factory). Use this skill whenever you:
    1. Create or modify a bronze/silver/gold table (Dataform) and must record its
       governance metadata (medallion tier, provenance, transformation repo,
       sensitivity, business domain, data owners/stewards).
    2. Need to write or fix the `/* governance */` header in a `.sqlx` file.
    3. Run or wire up aspect tagging (`tools/governance/apply_aspects.py`) after
       tables are created, or the `tag_governance` Composer task.
  This skill ATTACHES aspect values to entries. It does NOT define aspect types —
  the 5 custom types are Terraform-managed (location `global`).
license: Apache-2.0
metadata:
  version: v1
  publisher: analytics-factory
---

# Knowledge Catalog (Dataplex) — governance aspects

Data governance for this lakehouse runs on **Dataplex Knowledge Catalog**. Every
materialized lake table carries **aspects** that render in the Dataplex UI:
five org-specific custom aspects plus two first-party (1P) aspects.

> Org contract (read first): [guidelines/data-governance.md](../../../guidelines/data-governance.md).
> Full field reference: [references/aspect-model.md](references/aspect-model.md).

## The model in one paragraph

Governance values live in a **comment header** at the top of each Dataform
`.sqlx` (Dataform `config {}` rejects unknown keys, so the header sits *outside*
it). A shared module — [`tools/governance/aspect_model.py`](../../../tools/governance/aspect_model.py)
— parses that header, derives the rest from the file path
(`tier`←layer, `domain_name`←domain folder) and a constant
(`code_repository`←Dataform repo), and produces the aspect payloads. Two
consumers use it: the **validator** (CI/pre-commit) and the **apply script**
(attaches to BigQuery entries).

## The governance header

```sqlx
/* governance
data_owners: [Equipe de Vendas <sales-data@corp.com>]
data_stewards: [maria.steward@corp.com]
source_system: ERP                 # bronze only (data_provenance)
raw_format: JSONL                  # bronze only (data_provenance)
data_sensitivity: CONFIDENTIAL     # gold only   (business_governance)
*/
config { type: "incremental", schema: "silver_sales", name: "orders", ... }
```

Required per layer (enforced by `tools/checks/validate_governance.py`):

| Layer | Required header fields | Aspects attached |
|-------|------------------------|------------------|
| Bronze | `data_owners`, `data_stewards`, `source_system`, `raw_format` | medallion-tier, contacts, data-provenance |
| Silver | `data_owners`, `data_stewards` | medallion-tier, contacts, transformation-logic |
| Gold | `data_owners`, `data_stewards`, `data_sensitivity` | medallion-tier, contacts, business-governance, domain |

Sources (`type: declaration`) and staging (views) are **not** tagged.

## What to do when you create/modify a table

1. **Write the governance header** with the layer's required fields (above).
   Owners/stewards accept `Name <email>` or a bare `email`.
2. **Validate:** `python3 tools/checks/run_checks.py` (or `/review`). Missing or
   inconsistent headers fail the build.
3. **Apply aspects (dev):** after the table exists in BigQuery (Dataform ran),
   attach the aspects:
   ```bash
   python3 tools/governance/apply_aspects.py --dry-run    # preview payloads, no GCP
   python3 tools/governance/apply_aspects.py              # tag the dev project
   ```
   Defaults to the **dev** project (`cymbal-data-platform-dev`) and region
   `southamerica-east1`. Pass `--project`/`--region` to override.
4. **Prod** is tagged automatically by the Composer `tag_governance` task at the
   end of the pipeline — never run the script against prod by hand.

## Aspect types: do NOT create them here

The five custom aspect types (`medallion-tier`, `data-provenance`,
`transformation-logic`, `business-governance`, `domain`) and the 1P `contacts`
type already exist and are **Terraform-provisioned** in location `global`. This
repo only attaches **values**. If a type is missing, that is a Terraform/infra
task — do not `gcloud dataplex aspect-types create` from here.

## Data Quality Scorecard (1P, automatic)

`dataplex-types.global.data-quality-scorecard` is **not** attached by the apply
script — it is populated automatically by a Dataplex **data-quality scan**. To
get a scorecard on silver/gold, create a DQ scan on the table (build on the
`data-autocleaning` skill's `dataplex_scanner.py` profiling pattern, using a
data-*quality* scan with rules); the scorecard then renders on its own.

## Definition of Done

- The table's `.sqlx` has a valid `/* governance */` header for its layer.
- `python3 tools/checks/run_checks.py` is clean.
- In dev, `apply_aspects.py` ran (or its dry-run was reviewed) and aspects render
  in the Dataplex UI.
