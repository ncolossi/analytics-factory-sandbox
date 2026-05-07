# Transformações

## Motor: Dataform

Todas as transformações dentro do lake são implementadas como pipelines do **Dataform**. O Dataform gerencia transformações baseadas em SQL com resolução de dependências, testes e documentação integrados.

---

## Princípio Fundamental

**Toda operação de dados que envolva o BigQuery — seja cópia, movimentação ou transformação — deve ser implementada exclusivamente via Dataform.**

Isso inclui:
- Transformações entre camadas (bronze → silver → gold).
- Cópia de dados entre datasets ou tabelas dentro do BigQuery.
- Movimentação ou consolidação de dados entre domínios.
- Qualquer pipeline que leia e escreva no BigQuery.

**Não utilizar** scripts SQL avulsos, `bq cp`, `CREATE TABLE AS SELECT` executados manualmente, scheduled queries do BigQuery, ou qualquer outro mecanismo fora do Dataform para essas operações. O Dataform garante rastreabilidade, resolução de dependências, versionamento e governança sobre todo o ciclo de vida dos dados.

### Preferência por Processamento Incremental

Sempre que possível, pipelines devem usar **materialização incremental** em vez de full refresh. O processamento incremental:
- Reduz custos de processamento no BigQuery (menos bytes lidos/escritos).
- Diminui o tempo de execução dos pipelines.
- Minimiza o impacto em tabelas consumidas por dashboards e APIs em produção.

**Quando usar incremental**:
- Tabelas com volume de dados que cresce continuamente (logs, eventos, transações).
- Tabelas onde a fonte possui uma coluna confiável de timestamp ou controle de versão.
- Tabelas grandes onde full refresh tem custo proibitivo ou tempo de execução inaceitável.

**Quando usar full refresh**:
- Tabelas de dimensão pequenas que mudam por completo (ex.: tabela de configuração, categorias).
- Quando não há coluna confiável para identificar registros novos/alterados.
- Durante o bootstrap inicial de uma tabela incremental.

Veja a seção [Processamento Incremental](#processamento-incremental) para padrões de implementação.

---

## Estrutura do Projeto

```
dataform/
├── definitions/
│   ├── bronze/              # Declarações de fonte para dados brutos
│   │   └── {domain}/
│   │       └── {entity}.sqlx
│   ├── silver/              # Transformações de limpeza e conformação
│   │   └── {domain}/
│   │       └── {entity}.sqlx
│   ├── gold/                # Lógica de negócio e modelagem
│   │   └── {domain}/
│   │       └── {entity}.sqlx
│   └── staging/             # Transformações intermediárias (não expostas)
│       └── {domain}/
│           └── {entity}.sqlx
├── includes/                # Funções SQL e macros reutilizáveis
│   ├── constants.js
│   └── helpers.js
├── dataform.json            # Configuração do projeto
└── workflow_settings.yaml   # Configurações de workflow do Dataform
```

**Regras**:
- Espelhar a estrutura de camadas do lake: `definitions/{layer}/{domain}/{entity}.sqlx`.
- Um arquivo `.sqlx` por tabela de saída.
- Nomes de arquivos correspondem aos nomes das tabelas de destino (ex.: `orders.sqlx` produz a tabela `orders`).
- Arquivos de staging usam o prefixo `stg_` tanto no nome do arquivo quanto no nome da tabela.

---

## Padrões de Arquivos SQLX

### Bronze: Declarações de Fonte

Fontes bronze são declaradas (não transformadas) para que o Dataform possa rastrear dependências.

```sqlx
config {
  type: "declaration",
  database: "${constants.PROJECT_ID}",
  schema: "bronze_erp",
  name: "orders"
}
```

### Silver: Transformações de Limpeza

Transformações silver limpam, deduplicam e conformam dados bronze.

```sqlx
config {
  type: "table",
  schema: "silver_sales",
  name: "orders",
  description: "Cleaned and deduplicated sales orders.",
  bigquery: {
    partitionBy: "DATE(order_date)",
    clusterBy: ["customer_id", "order_date"]
  },
  tags: ["silver", "sales"],
  assertions: {
    uniqueKey: ["order_id"],
    nonNull: ["order_id", "customer_id", "order_date"]
  }
}

SELECT
  CURRENT_TIMESTAMP() AS _loaded_at,
  '${ref("bronze_erp", "orders")}' AS _source_table,

  CAST(order_id AS STRING) AS order_id,
  CAST(customer_id AS STRING) AS customer_id,
  SAFE_CAST(order_date AS DATE) AS order_date,
  CAST(status AS STRING) AS status,
  SAFE_CAST(total_amount AS NUMERIC) AS order_total_amount,
  SAFE_CAST(line_item_count AS INT64) AS line_item_count

FROM ${ref("bronze_erp", "orders")}
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY order_id
  ORDER BY _ingestion_timestamp DESC
) = 1
```

### Gold: Lógica de Negócio

Transformações gold aplicam regras de negócio, joins e agregações.

```sqlx
config {
  type: "table",
  schema: "gold_sales",
  name: "fact_orders",
  description: "Order fact table with enriched customer and product dimensions.",
  bigquery: {
    partitionBy: "DATE(order_date)",
    clusterBy: ["customer_id"]
  },
  tags: ["gold", "sales", "fact"],
  assertions: {
    uniqueKey: ["order_id"],
    nonNull: ["order_id", "customer_id", "order_date", "order_total_amount"]
  }
}

SELECT
  o.order_id,
  o.customer_id,
  o.order_date,
  o.status AS order_status,
  o.order_total_amount,
  o.line_item_count,
  c.customer_name,
  c.customer_segment,
  CURRENT_TIMESTAMP() AS _last_updated_at

FROM ${ref("silver_sales", "orders")} AS o
LEFT JOIN ${ref("silver_sales", "customers")} AS c
  ON o.customer_id = c.customer_id
```

### Staging: Etapas Intermediárias

Usar staging para transformações complexas que precisam ser divididas em etapas.

```sqlx
config {
  type: "view",
  schema: "silver_sales",
  name: "stg_orders_deduped",
  description: "Intermediate: deduplicated orders before final silver load.",
  tags: ["staging", "sales"]
}
```

**Regras**:
- Saídas de staging devem ser `type: "view"` para evitar materializar dados intermediários.
- Tabelas/views de staging nunca são consumidas fora de sua própria camada.

---

## Padrões de Codificação

### Estilo SQL

- Usar **letras maiúsculas** para palavras-chave SQL (`SELECT`, `FROM`, `WHERE`, `JOIN`).
- Usar **snake_case em minúsculas** para nomes de colunas e aliases.
- Uma coluna por linha em instruções `SELECT`.
- Indentar com 2 espaços.
- Sempre usar alias para tabelas em joins (aliases curtos e significativos: `o` para orders, `c` para customers).
- Preferir `SAFE_CAST` em vez de `CAST` ao converter dados de bronze para silver.
- Usar `QUALIFY` com `ROW_NUMBER()` para deduplicação em vez de subqueries.
- Usar `ref()` para todas as referências de tabelas — nunca hardcodar nomes de tabelas.

### Assertions

Toda tabela silver e gold deve incluir assertions:

| Assertion | Quando Usar |
|-----------|-------------|
| `uniqueKey` | Sempre — garante que não há registros duplicados na chave de negócio |
| `nonNull` | Em colunas que nunca devem ser nulas (IDs, datas, campos obrigatórios) |
| `rowConditions` | Para regras de negócio (ex.: `"order_total_amount >= 0"`) |

### Tags

Aplicar tags de forma consistente para gerenciamento de pipelines:

| Tag | Uso |
|-----|-------|
| `bronze` / `silver` / `gold` | Identificação de camada |
| `{domain}` | Agrupamento por domínio (ex.: `sales`, `finance`) |
| `fact` / `dim` / `agg` | Tipo de tabela (apenas camada gold) |
| `staging` | Tabelas intermediárias |
| `daily` / `hourly` | Cadência de atualização |

### Documentação

Todo arquivo `.sqlx` deve incluir:
- `description` no bloco config: um resumo em uma linha do que a tabela representa.
- Descrições de colunas para tabelas da camada gold via config `columns` do Dataform ou um bloco de documentação separado.

---

## Cópia e Movimentação de Dados

Para cenários de cópia ou movimentação de dados entre datasets ou tabelas do BigQuery, utilizar Dataform com as mesmas convenções do pipeline de transformação. Nunca utilizar `bq cp`, scripts avulsos ou scheduled queries.

### Cópia Direta entre Datasets

Quando é necessário replicar uma tabela de um dataset para outro sem transformação:

```sqlx
config {
  type: "table",
  schema: "silver_finance",
  name: "shared_customers",
  description: "Customer data replicated from sales domain for finance use.",
  bigquery: {
    partitionBy: "DATE(created_date)",
    clusterBy: ["customer_id"]
  },
  tags: ["silver", "finance", "data-copy"]
}

SELECT *
FROM ${ref("silver_sales", "customers")}
```

### Cópia Incremental entre Datasets

Para tabelas grandes, a cópia deve ser incremental:

```sqlx
config {
  type: "incremental",
  schema: "silver_finance",
  name: "shared_orders",
  description: "Orders replicated incrementally from sales domain.",
  uniqueKey: ["order_id"],
  bigquery: {
    partitionBy: "DATE(order_date)"
  },
  tags: ["silver", "finance", "data-copy", "incremental"]
}

SELECT *
FROM ${ref("silver_sales", "orders")}

${ when(incremental(), `
WHERE _loaded_at > (
  SELECT MAX(_loaded_at) FROM ${self()}
)
`) }
```

**Regras para cópia/movimentação**:
- Aplicar a tag `data-copy` para identificar pipelines que são réplicas sem transformação.
- Manter assertions de `uniqueKey` e `nonNull` mesmo em cópias diretas.
- Preferir cópia incremental para qualquer tabela acima de 1 GB ou com crescimento contínuo.
- Documentar no `description` a origem e a justificativa da cópia.

---

## Processamento Incremental

Processamento incremental é a estratégia preferencial para todas as tabelas com volume de dados crescente. Utilizar full refresh apenas quando as condições descritas no [Princípio Fundamental](#princípio-fundamental) justificarem.

### Padrão Básico: Filtro por Timestamp de Ingestão

Para tabelas silver que processam dados da camada bronze:

```sqlx
config {
  type: "incremental",
  schema: "silver_sales",
  name: "orders",
  uniqueKey: ["order_id"],
  bigquery: {
    partitionBy: "DATE(order_date)"
  },
  tags: ["silver", "sales", "incremental"]
}

SELECT
  ...
FROM ${ref("bronze_erp", "orders")}

${ when(incremental(), `
WHERE _ingestion_timestamp > (
  SELECT MAX(_loaded_at) FROM ${self()}
)
`) }
```

### Padrão Avançado: Merge com Múltiplas Colunas de Controle

Para tabelas onde registros podem ser atualizados na origem:

```sqlx
config {
  type: "incremental",
  schema: "silver_sales",
  name: "customers",
  uniqueKey: ["customer_id"],
  bigquery: {
    clusterBy: ["customer_id"]
  },
  tags: ["silver", "sales", "incremental"]
}

SELECT
  ...
FROM ${ref("bronze_crm", "customers")}

${ when(incremental(), `
WHERE _ingestion_timestamp > (
  SELECT MAX(_loaded_at) FROM ${self()}
)
OR updated_at > (
  SELECT MAX(_loaded_at) FROM ${self()}
)
`) }
```

### Padrão Gold Incremental: Agregações sobre Janela de Tempo

Para tabelas gold que agregam dados incrementalmente:

```sqlx
config {
  type: "incremental",
  schema: "gold_sales",
  name: "agg_daily_sales",
  uniqueKey: ["sale_date", "customer_segment"],
  bigquery: {
    partitionBy: "sale_date",
    clusterBy: ["customer_segment"]
  },
  tags: ["gold", "sales", "agg", "incremental"]
}

SELECT
  DATE(o.order_date) AS sale_date,
  c.customer_segment,
  COUNT(DISTINCT o.order_id) AS order_count,
  SUM(o.order_total_amount) AS total_revenue,
  CURRENT_TIMESTAMP() AS _last_updated_at
FROM ${ref("silver_sales", "orders")} AS o
LEFT JOIN ${ref("silver_sales", "customers")} AS c
  ON o.customer_id = c.customer_id

${ when(incremental(), `
WHERE o._loaded_at > (
  SELECT MAX(_last_updated_at) FROM ${self()}
)
`) }

GROUP BY sale_date, customer_segment
```

**Regras**:
- Sempre definir `uniqueKey` para tabelas incrementais.
- Usar o padrão `when(incremental(), ...)` para filtrar novos registros.
- Garantir que a lógica incremental seja idempotente — reprocessar um batch não deve criar duplicatas.
- Aplicar a tag `incremental` para identificar tabelas com materialização incremental.
- Utilizar `${self()}` para referenciar a própria tabela ao consultar o último estado processado.
- Para tabelas particionadas, o filtro incremental deve ser compatível com a coluna de partição para otimizar custos de leitura.

---

## Includes Reutilizáveis

### constants.js

Centralizar constantes em nível de projeto:

```javascript
const PROJECT_ID = "your-gcp-project-id";
const LOCATION = "southamerica-east1";

module.exports = { PROJECT_ID, LOCATION };
```

### helpers.js

Funções reutilizáveis de geração SQL:

```javascript
function safeCastColumns(columns, type) {
  return columns.map(c => `SAFE_CAST(${c} AS ${type}) AS ${c}`).join(",\n  ");
}

module.exports = { safeCastColumns };
```

Uso em SQLX:

```sqlx
js {
  const { safeCastColumns } = require("includes/helpers");
}

SELECT
  ${safeCastColumns(["order_date"], "DATE")},
  ...
```
