# Definição do Lake

## Arquitetura: Medallion Lakehouse

O data lake segue uma **arquitetura medallion** (bronze → silver → gold) com todas as camadas armazenadas no **BigQuery**. Cada camada tem um propósito claro, garantia de qualidade e convenção de nomenclatura.

```
Sources → [Bronze] → [Silver] → [Gold]
           raw        cleaned     business-ready
           append     deduplicated aggregated
           schema-    conformed    modeled
           on-read    typed        documented
```

**Regra de operação**: Toda movimentação de dados entre camadas, cópia entre datasets e transformação dentro do BigQuery é executada exclusivamente via **Dataform**, com preferência por processamento incremental. Veja [Transformações](transformations.md) para padrões e implementação.

---

## Camadas

### Bronze (Raw)

- **Propósito**: Ingerir e preservar dados brutos exatamente como recebidos dos sistemas de origem.
- **Qualidade**: Nenhuma transformação aplicada. Schema-on-read. Os dados podem conter duplicatas, nulos e inconsistências.
- **Retenção**: Histórico completo preservado. Somente append — nunca atualizar ou excluir registros brutos.
- **Colunas de metadados**: Toda tabela bronze inclui metadados de ingestão (veja Padrões de Colunas abaixo).

### Silver (Cleaned)

- **Propósito**: Dados deduplicados, tipados e conformados. Fonte única de verdade por entidade.
- **Qualidade**: Schema aplicado. Tipos de dados validados. Duplicatas removidas. Tratamento de nulos aplicado.
- **Retenção**: Estado mais recente de cada registro (full refresh ou upsert — sem histórico de versões).
- **Transformações**: Deduplicação, type casting, renomeação de colunas para convenções padrão, tratamento de nulos, validação básica.

### Gold (Business-Ready)

- **Propósito**: Dados agregados, enriquecidos e modelados prontos para analytics e consumo.
- **Qualidade**: Regras de negócio aplicadas. Integridade referencial garantida. Totalmente documentado.
- **Retenção**: Depende do caso de uso (snapshots, agregações, materialized views).
- **Transformações**: Joins, agregações, lógica de negócio, cálculos de KPIs, modelagem dimensional.

---

## Nomenclatura

### Nomenclatura de Datasets

Datasets são datasets do BigQuery que organizam tabelas por camada e domínio.

**Padrão**: `{layer}_{domain}`

| Componente | Descrição | Exemplos |
|-----------|-------------|----------|
| `layer` | Camada medallion | `bronze`, `silver`, `gold` |
| `domain` | Domínio de negócio ou sistema de origem | `sales`, `finance`, `marketing`, `erp`, `crm` |

**Exemplos**:
- `bronze_erp` — dados brutos ingeridos do sistema ERP
- `bronze_crm` — dados brutos ingeridos do sistema CRM
- `silver_sales` — dados de vendas limpos e conformados
- `silver_finance` — dados financeiros limpos e conformados
- `gold_sales` — modelos analíticos de vendas prontos para uso
- `gold_finance` — modelos de relatórios financeiros prontos para uso

**Regras**:
- Tudo em minúsculas, usando underscores como separadores.
- Nomes de domínio devem ser substantivos curtos e descritivos (não abreviações, a menos que sejam universalmente entendidas como `erp`, `crm`).
- Um dataset por combinação de camada-domínio.

### Nomenclatura de Tabelas

**Padrão**: `{entity}` (dentro do dataset de camada-domínio)

| Componente | Descrição | Exemplos |
|-----------|-------------|----------|
| `entity` | A entidade ou conceito de negócio que a tabela representa | `customers`, `orders`, `invoices`, `products` |

**Prefixos** (opcionais, aplicados quando necessário):

| Prefixo | Uso | Exemplo |
|--------|-------|---------|
| `dim_` | Tabela de dimensão (camada gold) | `dim_customers` |
| `fact_` | Tabela de fatos (camada gold) | `fact_orders` |
| `agg_` | Tabela pré-agregada (camada gold) | `agg_daily_sales` |
| `stg_` | Tabela de staging/intermediária (qualquer camada) | `stg_orders_deduped` |
| `bridge_` | Tabela bridge para muitos-para-muitos (camada gold) | `bridge_order_products` |

**Exemplos**:
- `bronze_erp.orders` — pedidos brutos do ERP
- `silver_sales.orders` — pedidos limpos e deduplicados
- `gold_sales.fact_orders` — tabela de fatos para analytics de pedidos
- `gold_sales.dim_customers` — dimensão de clientes

**Regras**:
- Tudo em minúsculas, usando underscores como separadores.
- Usar **substantivos no plural** para nomes de entidades (`orders` e não `order`).
- Nomes de tabelas devem ser únicos dentro de um dataset.
- Prefixos (`dim_`, `fact_`, `agg_`) são usados apenas na camada gold para modelagem dimensional.
- Tabelas de staging (`stg_`) são intermediárias e não devem ser consumidas downstream.

### Nomenclatura de Colunas

**Regras gerais**:
- Tudo em minúsculas, usando underscores como separadores (snake_case).
- Usar nomes descritivos e sem ambiguidade (`customer_email` e não `email`, `order_total_amount` e não `total`).
- Colunas booleanas: prefixar com `is_` ou `has_` (`is_active`, `has_subscription`).
- Colunas de data: sufixar com `_date` (`order_date`, `created_date`).
- Colunas de timestamp: sufixar com `_at` (`created_at`, `updated_at`).
- Colunas de ID/chave: sufixar com `_id` ou `_key` (`customer_id`, `order_key`).
- Colunas de valor/montante: sufixar com `_amount` ou `_value` e incluir contexto de moeda (`order_total_amount`).
- Colunas de contagem: sufixar com `_count` (`line_item_count`).

### Colunas de Metadados Obrigatórias

#### Camada Bronze

Toda tabela bronze deve incluir:

| Coluna | Tipo | Descrição |
|--------|------|-------------|
| `_ingestion_timestamp` | `TIMESTAMP` | Quando o registro foi ingerido no lake |
| `_source_file` | `STRING` | Caminho do arquivo de origem, endpoint da API ou identificador do sistema |
| `_batch_id` | `STRING` | Identificador único do batch de ingestão |

#### Camada Silver

Toda tabela silver deve incluir:

| Coluna | Tipo | Descrição |
|--------|------|-------------|
| `_loaded_at` | `TIMESTAMP` | Quando o registro foi carregado/atualizado pela última vez |
| `_source_table` | `STRING` | Tabela bronze de origem com nome completo |

#### Camada Gold

Tabelas gold incluem metadados padrão:

| Coluna | Tipo | Descrição |
|--------|------|-------------|
| `_last_updated_at` | `TIMESTAMP` | Quando o registro foi computado/atualizado pela última vez |

---

## Tipos de Dados

Usar tipos nativos do BigQuery de forma consistente:

| Conceito | Tipo BigQuery | Observações |
|---------|---------------|-------|
| Identificadores | `STRING` | Mesmo IDs numéricos são armazenados como STRING |
| Texto livre | `STRING` | Sem restrição de comprimento no BigQuery |
| Datas | `DATE` | Datas do calendário sem horário |
| Timestamps | `TIMESTAMP` | Sempre em UTC |
| Booleanos | `BOOL` | Não usar INT64 |
| Inteiros | `INT64` | Números inteiros |
| Decimais | `NUMERIC` ou `BIGNUMERIC` | Valores financeiros usam `NUMERIC(38,9)` |
| Ponto flutuante | `FLOAT64` | Apenas para valores não exatos (medições, scores) |
| Estruturado | `STRUCT` / `ARRAY` | Usar quando aninhamento simplifica o modelo |
| Binário | `BYTES` | Raro — evitar se possível |

---

## Particionamento e Clustering

### Particionamento

- Tabelas bronze: sempre particionar por `_ingestion_timestamp` (DAY).
- Tabelas silver: particionar pela data principal de negócio ou `_loaded_at` (DAY).
- Tabelas gold: particionar pela data principal de negócio ou `_last_updated_at`.

### Clustering

- Aplicar clustering em colunas frequentemente usadas em cláusulas `WHERE` e `JOIN`.
- Máximo de 4 colunas de clustering por tabela.
- Ordenar colunas de clustering da maior para a menor cardinalidade de benefício de filtragem.
