# Estrutura do Repositório

## Visão Geral

Este repositório é um **mono-repo** que centraliza todos os assets da plataforma de dados: ingestão, transformações, orquestração e documentação. A estrutura reflete a separação de responsabilidades descrita nos demais documentos de arquitetura.

---

## Árvore de Diretórios

```
agentic-data-development/
│
├── guidelines/                        # Documentação de arquitetura e design
│   ├── lake-definition.md             #   Definição do lake (medallion, nomenclatura)
│   ├── project-topology.md            #   Topologia do projeto GCP
│   ├── transformations.md             #   Padrões de transformação Dataform
│   ├── orchestration.md               #   Padrões de orquestração Composer/Airflow
│   ├── api-ingestion.md               #   Padrões de ingestão de APIs via Cloud Run Jobs
│   └── repo-structure.md              #   Este documento
│
├── transformation/                    # Camada de transformação
│   └── dataform/                      #   Projeto Dataform (ELT)
│       ├── workflow_settings.yaml     #     Configuração do projeto
│       ├── definitions/               #     Definições de tabelas e transformações
│       │   ├── bronze/                #       Declarações de fontes (raw)
│       │   │   └── {domain}/         #         Ex.: erp/, crm/
│       │   │       └── {entity}.sqlx #         Ex.: orders.sqlx, customers.sqlx
│       │   ├── silver/                #       Transformações de limpeza
│       │   │   └── {domain}/         #         Ex.: sales/, finance/
│       │   │       └── {entity}.sqlx
│       │   ├── gold/                  #       Lógica de negócio e modelagem
│       │   │   └── {domain}/         #         Ex.: sales/, finance/
│       │   │       └── {entity}.sqlx #         Ex.: fact_orders.sqlx, dim_customers.sqlx
│       │   └── staging/               #       Transformações intermediárias
│       │       └── {domain}/
│       │           └── stg_{entity}.sqlx
│       └── includes/                  #     Funções e constantes reutilizáveis
│           ├── constants.js           #       PROJECT_ID, LOCATION, etc.
│           └── helpers.js             #       Funções de geração SQL
│
├── ingestion/                         # Camada de ingestão
│   └── cloudrun/                      #   Cloud Run Jobs para APIs externas
│       ├── {domain}/                  #     Jobs organizados por domínio
│       │   └── {source}/              #       Um diretório por API/source
│       │       ├── Dockerfile         #         Container do job
│       │       ├── main.py            #         Lógica de extração
│       │       └── requirements.txt   #         Dependências Python
│       └── common/                    #     Utilitários compartilhados
│           ├── base.py                #       Classe base para extração
│           └── gcs_writer.py          #       Utilitário para escrita no GCS
│
├── orchestration/                     # Camada de orquestração
│   └── airflow/                       #   Cloud Composer (Airflow)
│       └── dags/                      #     DAGs do Airflow
│           ├── {domain}/              #       DAGs organizadas por domínio
│           │   └── {pipeline}.py     #         Ex.: daily_refresh.py, ingest_orders.py
│           └── common/                #       Utilitários compartilhados
│               └── utils.py
│       └── scripts/                   #     Scripts utilitários (deploy, etc.)
│           └── deploy_dags.sh
│
└── .gitignore
```

---

## Guia de Localização de Assets

Use esta tabela para determinar onde criar cada tipo de asset:

| Tipo de Asset | Diretório | Convenção de Nome | Referência |
|---|---|---|---|
| Job de ingestão de API | `ingestion/cloudrun/{domain}/{source}/` | `Dockerfile` + `main.py` | [Ingestão via APIs](api-ingestion.md) |
| Declaração de fonte (bronze) | `transformation/dataform/definitions/bronze/{domain}/` | `{entity}.sqlx` | [Transformações](transformations.md) |
| Transformação silver | `transformation/dataform/definitions/silver/{domain}/` | `{entity}.sqlx` | [Transformações](transformations.md) |
| Modelo gold | `transformation/dataform/definitions/gold/{domain}/` | `{fact\|dim\|agg}_{entity}.sqlx` | [Transformações](transformations.md) |
| Tabela intermediária | `transformation/dataform/definitions/staging/{domain}/` | `stg_{entity}.sqlx` | [Transformações](transformations.md) |
| Macro/helper SQL | `transformation/dataform/includes/` | `{nome_descritivo}.js` | [Transformações](transformations.md) |
| DAG de domínio | `orchestration/airflow/dags/{domain}/` | `{pipeline}.py` | [Orquestração](orchestration.md) |
| Utilitário de DAG | `orchestration/airflow/dags/common/` | `{nome_descritivo}.py` | [Orquestração](orchestration.md) |
| Documento de arquitetura | `guidelines/` | `{tema}.md` | - |
| Script de operação | `orchestration/airflow/scripts/` | `{ação}.sh` | - |

---

## Regras do Mono-Repo

### 1. Espelhamento de Domínios

Diretórios sob `ingestion/cloudrun/`, `transformation/dataform/definitions/` e `orchestration/airflow/dags/` devem espelhar os domínios de negócio do lake. Quando um novo domínio é adicionado, ele deve aparecer nas camadas aplicáveis:

```
ingestion/cloudrun/sales/                            →  (se houver APIs como fonte)
transformation/dataform/definitions/silver/sales/    →  orchestration/airflow/dags/sales/
transformation/dataform/definitions/silver/finance/  →  orchestration/airflow/dags/finance/
```

### 2. Um Arquivo por Tabela

Cada tabela de saída no Dataform corresponde a exatamente um arquivo `.sqlx`. O nome do arquivo deve ser idêntico ao nome da tabela destino.

### 3. Uma DAG por Arquivo

Cada arquivo Python em `orchestration/airflow/dags/` define exatamente uma DAG. O `dag_id` deve corresponder ao padrão `{domain}__{pipeline}`.

### 4. Separação de Responsabilidades

- `ingestion/` contém apenas lógica de extração de dados (`cloudrun/` para Cloud Run Jobs).
- `transformation/` contém apenas lógica de transformação.
- `orchestration/` contém apenas lógica de orquestração.
- Nenhum desses diretórios deve importar código dos outros.

### 5. Scripts Operacionais

Scripts de deploy, seed de dados, ou operações manuais ficam em `orchestration/airflow/scripts/`. Eles não fazem parte do runtime dos pipelines.

---

## Fluxo de Adição de um Novo Domínio

Ao adicionar um novo domínio (ex.: `marketing`), os seguintes arquivos devem ser criados:

1. **Ingestão** (se houver APIs como fonte) - Cloud Run Jobs:
   ```
   ingestion/cloudrun/marketing/{source}/Dockerfile
   ingestion/cloudrun/marketing/{source}/main.py
   ingestion/cloudrun/marketing/{source}/requirements.txt
   ```

2. **Dataform** - declarações bronze e transformações:
   ```
   transformation/dataform/definitions/bronze/marketing/{entity}.sqlx
   transformation/dataform/definitions/silver/marketing/{entity}.sqlx
   transformation/dataform/definitions/gold/marketing/{fact|dim}_{entity}.sqlx
   ```

3. **DAG** - pipeline de orquestração:
   ```
   orchestration/airflow/dags/marketing/daily_refresh.py
   ```

---

## Ambientes Virtuais Python

Ao desenvolver localmente (ex.: jobs de ingestão em `ingestion/cloudrun/`), usar `.venv/` como nome do diretório do ambiente virtual:

```bash
python -m venv .venv
source .venv/bin/activate
```

**Regras**:
- Sempre usar `.venv/` — nunca `venv/`, `env/`, `.env/` ou nomes personalizados.
- O diretório `.venv/` já está incluído no `.gitignore` do repositório.
- Cada job de ingestão pode ter seu próprio `.venv/` local para isolamento de dependências durante o desenvolvimento.

---

## O Que NÃO Pertence ao Repositório

| Item | Motivo | Onde Fica |
|---|---|---|
| Credenciais e secrets | Segurança | Secret Manager, Airflow Connections |
| Dados de negócio | Volume e sensibilidade | BigQuery, GCS |
| Configurações de IDE | Preferência pessoal | Local (`.gitignore`) |
