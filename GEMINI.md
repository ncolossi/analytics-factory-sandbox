# Agentic Data Development: Diretrizes Gemini

Este repositório segue uma arquitetura rigorosa para construção de data pipelines utilizando a **Medallion Architecture (Bronze -> Silver -> Gold)**. Toda manipulação de dados, processos de ELT e até cópias de dados entre datasets DEVEM ser executados através do **Dataform**, orquestrados via **Cloud Composer (Airflow)**.

Sempre que estiver gerando código ou auxiliando neste repositório, você DEVE seguir os métodos de desenvolvimento e regras descritos na documentação em `guidelines/`.

## Princípios Fundamentais

1. **Dataform é o Motor**:
   - **Toda operação de dados que envolva o BigQuery deve ser implementada exclusivamente via Dataform.**
   - NÃO utilizar `bq cp`, `CREATE TABLE AS SELECT` manual, scheduled queries ou scripts SQL genéricos.
   - Deve-se usar materialização incremental sempre que possível. Full refresh deve ser restrito a tabelas de dimensão pequenas ou bootstrap inicial.
   - Referenciar todas as tabelas usando `${ref("schema", "table")}` ou `${self()}` em queries incrementais.
   - Nunca hardcodar nomes de tabelas.

2. **Documentação em Português**:
   - **Todas as descrições de datasets, tabelas e colunas no BigQuery devem ser escritas em português.**
   - Descrições de datasets devem explicar o domínio, a camada e o nível de qualidade dos dados.
   - Descrições de tabelas devem explicar o significado de negócio, a origem dos dados e as transformações aplicadas.
   - Descrições de colunas são obrigatórias para tabelas silver e gold, usando o bloco `columns` no config do Dataform. Devem explicar o significado de negócio, valores categóricos possíveis e moeda quando aplicável.

3. **Arquitetura Mono-Repo**:
   - **Transformação**: Somente lógica ELT do Dataform pertence a `transformation/dataform/definitions/`.
   - **Orquestração**: Somente DAGs do Airflow e scripts utilitários pertencem a `orchestration/airflow/`.
   - Garantir separação estrita de responsabilidades. Não misturar código de camadas diferentes.

## O Medallion Lakehouse

- **Bronze (Raw)**: Schema-on-read, sem transformações, somente append. Deve incluir `_ingestion_timestamp`, `_source_file` e `_batch_id`. Configurações do Dataform devem ser `type: "declaration"`.
- **Silver (Cleaned)**: Dados deduplicados, tipados e conformados. Usa `type: "table"` ou `type: "incremental"`. Deve incluir `_loaded_at` e `_source_table`. Incluir assertions do Dataform (`uniqueKey`, `nonNull`). Descrições de tabela e colunas em português são obrigatórias.
- **Gold (Business-Ready)**: Dados agregados e modelados (dim, fact, agg). Usa `type: "table"` ou `type: "incremental"`. Deve incluir `_last_updated_at`. Incluir assertions do Dataform. Descrições de tabela e colunas em português são obrigatórias.
- **Staging**: Lógica intermediária. Deve ser `type: "view"`. Nunca consumido fora de sua própria camada.

## Nomenclaturas e Organização

- **Datasets**: `{layer}_{domain}` (ex.: `bronze_erp`, `silver_sales`, `gold_finance`).
- **Tabelas**: Substantivos no plural para entidades (`orders`, `customers`). Camada gold usa prefixos: `dim_`, `fact_`, `agg_`. Staging usa `stg_`.
- **Arquivos**:
  - Um arquivo `.sqlx` do Dataform por tabela, nomeado exatamente como a tabela de saída.
  - Uma DAG do Airflow por arquivo `.py`, nomeada `{domain}__{pipeline}`.

## Espelhamento de Domínios

Os domínios devem ser espelhados entre os diretórios `transformation` e `orchestration`. Se um domínio `sales` existe no Dataform, deve haver uma pasta `sales` correspondente nas DAGs do Airflow.

Exemplo:
`transformation/dataform/definitions/silver/sales/` -> `orchestration/airflow/dags/sales/`

## Antes de Criar Novos Assets

Sempre consultar os arquivos de documentação específicos em `guidelines/` para detalhamento:
- `guidelines/lake-definition.md`: Para especificidades das camadas Medallion, convenções de nomenclatura, clustering, partitioning e colunas de metadados obrigatórias.
- `guidelines/transformations.md`: Para especificidades do Dataform, padrões de materialização incremental, assertions, macros e estilo SQL.
- `guidelines/orchestration.md`: Para regras de criação de DAGs do Composer/Airflow (se solicitado).
- `guidelines/project-topology.md`: Para topologia GCP.
- `guidelines/repo-structure.md`: Para caminhos de arquivo exatos e regras do mono-repo.
