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
└── workflow_settings.yaml   # Configuração do projeto Dataform
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
  description: "Pedidos de venda limpos e deduplicados, originados do sistema ERP. Inclui type casting, remoção de duplicatas por order_id (mantém o registro mais recente) e padronização de nomes de colunas.",
  columns: {
    order_id: "Identificador único do pedido de venda, originado do sistema ERP.",
    customer_id: "Identificador único do cliente que realizou o pedido.",
    order_date: "Data em que o pedido foi realizado pelo cliente.",
    status: "Status atual do pedido no sistema ERP (ex.: pendente, aprovado, cancelado, entregue).",
    order_total_amount: "Valor total do pedido em reais (BRL), incluindo todos os itens.",
    line_item_count: "Quantidade de itens distintos incluídos no pedido.",
    _loaded_at: "Timestamp UTC de quando o registro foi carregado ou atualizado pela última vez na camada silver.",
    _source_table: "Nome completo da tabela bronze de origem deste registro."
  },
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
  description: "Tabela fato de pedidos de venda enriquecida com dimensões de cliente e produto. Contém métricas de valor total e contagem de itens por pedido.",
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
  description: "Etapa intermediária: pedidos deduplicados antes da carga final na camada silver.",
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

**Regra fundamental: todas as descrições de datasets, tabelas e colunas no BigQuery devem ser escritas em português.**

Descrições são obrigatórias e servem como documentação viva do lake — são exibidas no console do BigQuery, catálogos de dados e ferramentas de governança. Descrições claras e detalhadas em português garantem que qualquer pessoa da organização consiga entender o propósito e o conteúdo dos dados sem precisar consultar documentação externa.

#### Descrições de Datasets

Todo dataset criado no BigQuery deve ter uma descrição que explique:
- O domínio de dados que o dataset contém.
- A camada do lake a que pertence e o nível de qualidade dos dados.
- O sistema ou área de origem dos dados (para bronze e silver).

**Exemplos**:
- `bronze_erp`: *"Dados brutos ingeridos do sistema ERP sem nenhuma transformação aplicada. Contém o histórico completo de ingestão com possíveis duplicatas e inconsistências."*
- `silver_sales`: *"Dados de vendas limpos, deduplicados e tipados. Fonte única de verdade para entidades do domínio de vendas."*
- `gold_sales`: *"Modelos analíticos de vendas prontos para consumo por dashboards, relatórios e APIs. Contém tabelas fato, dimensão e agregações com regras de negócio aplicadas."*

#### Descrições de Tabelas

Todo arquivo `.sqlx` deve incluir `description` no bloco config com uma descrição detalhada que explique:
- O que a tabela representa em termos de negócio.
- A origem dos dados (de qual tabela/sistema vem).
- Transformações ou regras de negócio relevantes aplicadas.
- Para tabelas incrementais, a estratégia de atualização.

**Exemplos**:
```sqlx
config {
  type: "table",
  schema: "silver_sales",
  name: "orders",
  description: "Pedidos de venda limpos e deduplicados, originados do sistema ERP. Inclui type casting, remoção de duplicatas por order_id (mantém o registro mais recente) e padronização de nomes de colunas.",
  ...
}
```

```sqlx
config {
  type: "table",
  schema: "gold_sales",
  name: "fact_orders",
  description: "Tabela fato de pedidos de venda enriquecida com dimensões de cliente e produto. Contém métricas de valor total e contagem de itens por pedido, pronta para análises de receita e comportamento de compra.",
  ...
}
```

#### Descrições de Colunas

Descrições de colunas são obrigatórias para tabelas das camadas **silver** e **gold**. Utilizar o bloco `columns` no config do Dataform:

```sqlx
config {
  type: "table",
  schema: "gold_sales",
  name: "fact_orders",
  description: "Tabela fato de pedidos de venda enriquecida com dimensões de cliente e produto.",
  columns: {
    order_id: "Identificador único do pedido de venda, originado do sistema ERP.",
    customer_id: "Identificador único do cliente que realizou o pedido.",
    order_date: "Data em que o pedido foi realizado pelo cliente.",
    order_status: "Status atual do pedido (ex.: pendente, aprovado, cancelado, entregue).",
    order_total_amount: "Valor total do pedido em reais (BRL), incluindo todos os itens.",
    line_item_count: "Quantidade de itens distintos incluídos no pedido.",
    customer_name: "Nome completo do cliente, proveniente da dimensão de clientes.",
    customer_segment: "Segmento de classificação do cliente (ex.: varejo, atacado, premium).",
    _last_updated_at: "Timestamp UTC da última execução do pipeline que atualizou este registro."
  },
  ...
}
```

**Regras para descrições de colunas**:
- Explicar o significado de negócio da coluna, não apenas o tipo de dado.
- Para colunas com valores categóricos, listar os valores possíveis entre parênteses.
- Para colunas de valor monetário, indicar a moeda.
- Para colunas originadas de outros sistemas, indicar a origem.
- Colunas de metadados (`_loaded_at`, `_source_table`, `_last_updated_at`) também devem ter descrição.

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
  description: "Dados de clientes replicados do domínio de vendas para uso do domínio financeiro.",
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
  description: "Pedidos replicados incrementalmente do domínio de vendas para o domínio financeiro.",
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
