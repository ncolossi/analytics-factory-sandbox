# Transformations — org overrides

> **How-to:** use the `dataform-bigquery` skill for SQLX syntax, incremental
> patterns, assertions, and project setup. This file is only our deltas on top
> of it. Do not duplicate the skill's tutorials here.

## Hard rules (enforced by `tools/checks/`)

1. **Dataform is the only writer to BigQuery.** No `bq cp`, no manual
   `CREATE TABLE AS SELECT`, no scheduled queries. Cross-dataset copies are
   Dataform actions too (tag them `data-copy`).
2. **No hardcoded** project IDs or table names — `${ref()}`, `${self()}`,
   `includes/constants.js` only.
3. **Bronze** sources are `type: "declaration"`. Never transform or truncate
   bronze.
4. **Silver & Gold** must declare `assertions` (`uniqueKey`, always; `nonNull`
   on required columns; `rowConditions` for business rules).
5. **Staging** is always `type: "view"` and never consumed outside its layer.
6. **Descriptions in Portuguese** on every table; on every silver/gold column
   (`columns` block). Explain business meaning, categorical values, currency,
   source.

## Layout (mono-repo)

```
transformation/dataform/definitions/{layer}/{domain}/{entity}.sqlx
transformation/dataform/includes/{constants,helpers}.js
```

One `.sqlx` per output table; filename == table name. Mirror lake domains.

## Materialization

- **Prefer incremental** for growing data (events, transactions, large tables
  with a reliable timestamp). Always set `uniqueKey`; make it idempotent; keep
  the incremental filter partition-compatible.
- **Full refresh** only for small dimensions, sources lacking a change column,
  or initial bootstrap.

## SQL style

Uppercase keywords; `snake_case` identifiers; one column per line; 2-space
indent; alias tables in joins; `SAFE_CAST` bronze→silver; `QUALIFY ROW_NUMBER()`
for dedup; `${ref()}` for every table reference.

## Tags

Layer (`bronze`/`silver`/`gold`) + domain + type (`fact`/`dim`/`agg`) +
`staging` + cadence (`daily`/`hourly`) + `incremental` where applicable. Composer
invokes Dataform filtered by these tags — keep them consistent with
[orchestration.md](orchestration.md).

## Minimal silver example (note Portuguese descriptions)

```sqlx
config {
  type: "incremental",
  schema: "silver_sales",
  name: "orders",
  description: "Pedidos de venda limpos e deduplicados, originados do ERP.",
  uniqueKey: ["order_id"],
  columns: {
    order_id: "Identificador único do pedido de venda, originado do ERP.",
    order_total_amount: "Valor total do pedido em reais (BRL), incluindo todos os itens.",
    _loaded_at: "Timestamp UTC da última carga/atualização na camada silver."
  },
  bigquery: { partitionBy: "DATE(order_date)" },
  tags: ["silver", "sales", "incremental"],
  assertions: { uniqueKey: ["order_id"], nonNull: ["order_id", "order_date"] }
}

SELECT
  CURRENT_TIMESTAMP() AS _loaded_at,
  '${ref("bronze_erp", "orders")}' AS _source_table,
  CAST(order_id AS STRING) AS order_id,
  SAFE_CAST(total_amount AS NUMERIC) AS order_total_amount
FROM ${ref("bronze_erp", "orders")}
${ when(incremental(), `WHERE _ingestion_timestamp > (SELECT MAX(_loaded_at) FROM ${self()})`) }
QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY _ingestion_timestamp DESC) = 1
```
