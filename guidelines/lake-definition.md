# Lake Definition — org overrides

> Medallion lakehouse on BigQuery. How-to for Dataform modeling lives in the
> `dataform-bigquery` skill; this file is the org-specific contract on top of it.

## Layers

| Layer | Purpose | Quality | Write mode |
|-------|---------|---------|-----------|
| **Bronze** | Raw data exactly as received, **materialized** into the lake | None (schema-on-read; may contain dupes/nulls) | Materialized + append-only — never update/delete/overwrite |
| **Silver** | Deduplicated, typed, conformed; single source of truth per entity | Schema enforced, dupes removed, nulls handled | Full refresh or upsert (latest state) |
| **Gold** | Aggregated, modeled, business-ready | Business rules applied, fully documented | Depends on use case |

Every cross-layer move, cross-dataset copy, and in-BigQuery transform runs
**exclusively via Dataform**, incremental preferred (see
[transformations.md](transformations.md)).

**Bronze always materializes.** Even when the raw source already lives in
BigQuery (another dataset/project, a data share, an external table), bronze is a
**materialized** Dataform table that copies the data into `bronze_{domain}` —
never a `declaration`/pointer. Declare the upstream raw input as a **source**
(`definitions/sources/`, see [transformations.md](transformations.md)).

## Naming (mandatory)

- **Datasets:** `{layer}_{domain}` — lowercase, underscores. Examples:
  `bronze_erp`, `silver_sales`, `gold_finance`. One dataset per layer-domain.
- **Tables:** plural entity nouns (`orders`, not `order`). Gold modeling prefixes:
  `dim_`, `fact_`, `agg_`, `bridge_`. Staging: `stg_` (any layer, view only).
- **Columns:** `snake_case`. Booleans `is_`/`has_`; dates `_date`; timestamps
  `_at` (UTC); ids `_id`/`_key`; money `_amount`/`_value` (+ currency in
  description); counts `_count`.

## Mandatory metadata columns

| Layer | Columns |
|-------|---------|
| Bronze | `_ingestion_timestamp` (TIMESTAMP), `_source_file` (STRING), `_batch_id` (STRING) |
| Silver | `_loaded_at` (TIMESTAMP), `_source_table` (STRING) |
| Gold | `_last_updated_at` (TIMESTAMP) |

## Data types

IDs as `STRING` (even numeric ones). Dates `DATE`; timestamps `TIMESTAMP` (UTC);
booleans `BOOL`; money `NUMERIC(38,9)`; floats only for inexact values. Use
`STRUCT`/`ARRAY` when nesting simplifies the model.

## Partitioning & clustering

- Bronze: partition by `_ingestion_timestamp` (DAY).
- Silver/Gold: partition by the main business date (or `_loaded_at` /
  `_last_updated_at`).
- Cluster on frequent `WHERE`/`JOIN` columns; max 4, highest filtering benefit
  first.

## Descriptions are Portuguese (Rule 6)

Dataset/table descriptions, and silver/gold column descriptions, are **required
and written in Portuguese**. Explain business meaning, source, categorical
values, and currency — not the data type. Example:

```
order_total_amount: "Valor total do pedido em reais (BRL), incluindo todos os itens."
```
