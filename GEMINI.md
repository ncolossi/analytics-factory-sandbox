# Agentic Data Development: Diretrizes Gerais

@guidelines/lake-definition.md
@guidelines/transformations.md
@guidelines/orchestration.md
@guidelines/project-topology.md
@guidelines/repo-structure.md
@guidelines/api-ingestion.md

Este repositório segue uma arquitetura rigorosa para construção de data pipelines utilizando a **Medallion Architecture (Bronze -> Silver -> Gold)**. Toda manipulação de dados, processos de ELT e até cópias de dados entre datasets DEVEM ser executados através do **Dataform**, orquestrados via **Cloud Composer (Airflow)**.

Sempre que estiver gerando código ou auxiliando neste repositório, você DEVE seguir os métodos de desenvolvimento e regras descritos na documentação em `guidelines/`.

## Princípios Fundamentais

1. **Dataform é o Motor**:
   - **Toda operação de dados que envolva o BigQuery deve ser implementada exclusivamente via Dataform.**
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
   - **Ingestão**: Somente Cloud Run Jobs de ingestão de APIs pertencem a `ingestion/cloudrun/`.
   - Garantir separação estrita de responsabilidades. Não misturar código de camadas diferentes.

## Anti-Padrões: O Que NUNCA Fazer

1. **NÃO utilizar `bq cp`, `CREATE TABLE AS SELECT` manual, scheduled queries ou scripts SQL genéricos.** Toda operação de dados no BigQuery passa pelo Dataform.
2. **NÃO hardcodar project IDs ou nomes de tabelas em arquivos SQLX.** Usar `${ref()}`, `${self()}` e `constants.js`.
3. **NÃO usar `WRITE_TRUNCATE` em tabelas bronze.** Bronze é somente append (`WRITE_APPEND`) — nunca sobrescrever dados brutos.
4. **NÃO criar DAGs do Airflow que escrevam diretamente no BigQuery** (exceto load jobs para bronze). Transformações pertencem ao Dataform.
5. **NÃO omitir descrições de colunas em tabelas silver e gold.** Usar o bloco `columns` no config do Dataform, sempre em português.
6. **NÃO omitir assertions (`uniqueKey`, `nonNull`) em tabelas silver e gold.** Toda tabela transformada deve ter validação.
7. **NÃO criar tabelas de staging como `type: "table"` ou `type: "incremental"`.** Staging deve ser `type: "view"`.
8. **NÃO incorporar credenciais ou secrets em código.** Usar Secret Manager montado no Cloud Run e Airflow Connections.
9. **NÃO consumir tabelas de staging fora de sua própria camada.** Staging é intermediário e interno.
10. **NÃO misturar código entre as camadas do mono-repo.** Cada diretório (`ingestion/`, `transformation/`, `orchestration/`) é independente.

## Antes de Criar Novos Assets

Sempre consultar os arquivos de documentação específicos em `guidelines/` para detalhamento:
- `guidelines/lake-definition.md`: Para especificidades das camadas Medallion, convenções de nomenclatura, clustering, partitioning e colunas de metadados obrigatórias.
- `guidelines/transformations.md`: Para especificidades do Dataform, padrões de materialização incremental, assertions, macros e estilo SQL.
- `guidelines/orchestration.md`: Para regras de criação de DAGs do Composer/Airflow.
- `guidelines/api-ingestion.md`: Para padrões de ingestão de APIs externas via Cloud Run Jobs, containerização e integração com Composer.
- `guidelines/project-topology.md`: Para topologia GCP, IAM e service accounts.
- `guidelines/repo-structure.md`: Para caminhos de arquivo exatos e regras do mono-repo.
