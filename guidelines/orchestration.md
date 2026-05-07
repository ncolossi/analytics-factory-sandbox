# Orquestração

## Motor: Cloud Composer (Airflow)

**Cloud Composer** é a camada única de orquestração. Ele agenda e coordena todas as etapas do pipeline: ingestão no bronze, transformações do Dataform (silver e gold) e tarefas auxiliares (notificações, verificações de qualidade de dados).

O Dataform gerencia a lógica de transformação SQL e a resolução de dependências dentro de uma camada. O Composer gerencia o pipeline de ponta a ponta: quando executar, em qual ordem entre camadas e o que fazer em caso de falha.

---

## Organização de DAGs

### Estrutura de Arquivos

```
dags/
├── {domain}/
│   └── {pipeline}.py
├── sales/
│   ├── daily_refresh.py
│   └── ingest_orders.py
├── finance/
│   └── daily_refresh.py
└── common/
    └── utils.py
```

**Regras**:
- Uma DAG por arquivo.
- Espelhar a estrutura de domínios do lake: `dags/{domain}/{pipeline}.py`.
- Utilitários compartilhados ficam em `dags/common/`.

### Nomenclatura de DAGs

**Padrão**: `{domain}__{pipeline}`

| Componente | Descrição | Exemplos |
|-----------|-------------|----------|
| `domain` | Domínio de negócio (corresponde aos domínios dos datasets do lake) | `sales`, `finance`, `erp` |
| `pipeline` | Propósito do pipeline | `daily_refresh`, `ingest_orders`, `hourly_metrics` |

**Exemplos**:
- `sales__daily_refresh` — pipeline diário completo para o domínio de vendas (ingest → silver → gold)
- `erp__ingest_orders` — pipeline somente de ingestão para pedidos do ERP
- `finance__daily_refresh` — pipeline diário completo para o domínio financeiro

**Regras**:
- Tudo em minúsculas, underscore duplo (`__`) separando domínio do pipeline.
- O DAG ID deve corresponder entre o nome do arquivo e o parâmetro `dag_id`.

---

## Padrões de DAGs

### Argumentos Padrão

Toda DAG deve usar argumentos padrão consistentes:

```python
from datetime import datetime, timedelta

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}
```

### Configuração de DAG

```python
from airflow import DAG

with DAG(
    dag_id="sales__daily_refresh",
    default_args=default_args,
    schedule_interval="0 6 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["sales", "daily"],
    max_active_runs=1,
    doc_md=__doc__,
) as dag:
    ...
```

**Regras**:
- `catchup=False` por padrão — backfills são acionados manualmente quando necessário.
- `max_active_runs=1` — prevenir execuções sobrepostas para a mesma DAG.
- `tags` — incluir domínio e cadência (corresponde às convenções de tags do Dataform).
- `doc_md=__doc__` — usar a docstring do módulo para documentação da DAG na UI do Airflow.
- `schedule_interval` — usar expressões cron, não presets.

---

## Padrões de Pipeline

### Full Domain Refresh (Bronze → Silver → Gold)

O padrão comum para um pipeline de domínio usa **task groups** por camada:

```python
"""Sales daily refresh pipeline.

Ingests raw data from GCS into bronze, then triggers Dataform
to process silver and gold layers.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.utils.task_group import TaskGroup
from airflow.providers.google.cloud.operators.bigquery import (
    BigQueryInsertJobOperator,
)
from airflow.providers.google.cloud.operators.dataform import (
    DataformCreateCompilationResultOperator,
    DataformCreateWorkflowInvocationOperator,
)

PROJECT_ID = "your-gcp-project-id"
REGION = "your-region"
DATAFORM_REPOSITORY = "your-dataform-repo"

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}

with DAG(
    dag_id="sales__daily_refresh",
    default_args=default_args,
    schedule_interval="0 6 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["sales", "daily"],
    max_active_runs=1,
    doc_md=__doc__,
) as dag:

    # --- Bronze: Ingestão ---
    with TaskGroup("bronze_ingestion") as bronze:
        ingest_orders = BigQueryInsertJobOperator(
            task_id="ingest_orders",
            configuration={
                "load": {
                    "sourceUris": ["gs://your-project-data-landing/sales/orders/*.parquet"],
                    "destinationTable": {
                        "projectId": PROJECT_ID,
                        "datasetId": "bronze_sales",
                        "tableId": "orders",
                    },
                    "sourceFormat": "PARQUET",
                    "writeDisposition": "WRITE_APPEND",
                }
            },
            location=REGION,
        )

        ingest_customers = BigQueryInsertJobOperator(
            task_id="ingest_customers",
            configuration={
                "load": {
                    "sourceUris": ["gs://your-project-data-landing/sales/customers/*.parquet"],
                    "destinationTable": {
                        "projectId": PROJECT_ID,
                        "datasetId": "bronze_sales",
                        "tableId": "customers",
                    },
                    "sourceFormat": "PARQUET",
                    "writeDisposition": "WRITE_APPEND",
                }
            },
            location=REGION,
        )

    # --- Silver: Transformações Dataform ---
    with TaskGroup("silver_transformations") as silver:
        compile_silver = DataformCreateCompilationResultOperator(
            task_id="compile_silver",
            project_id=PROJECT_ID,
            region=REGION,
            repository_id=DATAFORM_REPOSITORY,
            compilation_result={
                "git_commitish": "main",
            },
        )

        run_silver = DataformCreateWorkflowInvocationOperator(
            task_id="run_silver",
            project_id=PROJECT_ID,
            region=REGION,
            repository_id=DATAFORM_REPOSITORY,
            workflow_invocation={
                "compilation_result": "{{ task_instance.xcom_pull(task_ids='silver_transformations.compile_silver')['name'] }}",
                "invocation_config": {
                    "included_tags": ["silver", "sales"],
                    "transitive_dependencies_included": True,
                },
            },
        )

        compile_silver >> run_silver

    # --- Gold: Lógica de negócio Dataform ---
    with TaskGroup("gold_transformations") as gold:
        compile_gold = DataformCreateCompilationResultOperator(
            task_id="compile_gold",
            project_id=PROJECT_ID,
            region=REGION,
            repository_id=DATAFORM_REPOSITORY,
            compilation_result={
                "git_commitish": "main",
            },
        )

        run_gold = DataformCreateWorkflowInvocationOperator(
            task_id="run_gold",
            project_id=PROJECT_ID,
            region=REGION,
            repository_id=DATAFORM_REPOSITORY,
            workflow_invocation={
                "compilation_result": "{{ task_instance.xcom_pull(task_ids='gold_transformations.compile_gold')['name'] }}",
                "invocation_config": {
                    "included_tags": ["gold", "sales"],
                    "transitive_dependencies_included": True,
                },
            },
        )

        compile_gold >> run_gold

    # --- Fluxo do pipeline ---
    bronze >> silver >> gold
```

### Padrões Principais

| Padrão | Quando Usar |
|---------|-------------|
| Full domain refresh | Atualização diária/horária de um domínio inteiro (bronze → silver → gold) |
| Somente ingestão | Carregar dados no bronze sem acionar transformações downstream |
| Somente transformação | Re-executar Dataform para silver/gold sem re-ingerir |
| Cross-domain | Tabelas gold que fazem join de dados de múltiplos domínios — dependem de múltiplas DAGs de domínio via sensors |

---

## Integração com Dataform

### Operators

Usar os operators do Google Cloud Dataform para Airflow:

| Operator | Propósito |
|----------|---------|
| `DataformCreateCompilationResultOperator` | Compila o repositório Dataform em um git commitish específico |
| `DataformCreateWorkflowInvocationOperator` | Executa um workflow Dataform compilado |

### Filtragem por Tags

Invocações do Dataform são filtradas por **tags** para executar apenas o subconjunto relevante de transformações:

```python
"invocation_config": {
    "included_tags": ["silver", "sales"],
    "transitive_dependencies_included": True,
}
```

- Usar `included_tags` para limitar cada invocação a uma camada + domínio.
- Definir `transitive_dependencies_included: True` para que o Dataform resolva dependências upstream automaticamente.
- As tags devem corresponder às tags SQLX do Dataform definidas em [Transformações](transformations.md).

### Git Commitish

- **DAGs de produção**: Usar `"git_commitish": "main"` — sempre executar a partir da branch main.
- **Desenvolvimento/testes**: Usar o commitish de uma feature branch ao testar mudanças no pipeline.

---

## Tarefas de Ingestão

### GCS para BigQuery

Usar `BigQueryInsertJobOperator` para carregar arquivos do GCS em tabelas bronze:

```python
BigQueryInsertJobOperator(
    task_id="ingest_orders",
    configuration={
        "load": {
            "sourceUris": ["gs://bucket/path/*.parquet"],
            "destinationTable": {
                "projectId": PROJECT_ID,
                "datasetId": "bronze_{domain}",
                "tableId": "{entity}",
            },
            "sourceFormat": "PARQUET",
            "writeDisposition": "WRITE_APPEND",
        }
    },
    location=REGION,
)
```

**Regras**:
- Sempre usar `WRITE_APPEND` para bronze — preservar o histórico completo de ingestão.
- Preferir `PARQUET` ou `AVRO` para dados estruturados; usar `CSV` ou `NEWLINE_DELIMITED_JSON` quando restrições da fonte exigirem.
- URIs de origem devem usar padrões wildcard para capturar todos os arquivos em um diretório de landing.
- Colunas de metadados bronze (`_ingestion_timestamp`, `_source_file`, `_batch_id`) devem ser preenchidas no momento da ingestão — usar definições de schema ou etapas pós-carga do Dataform.

---

## Tratamento de Erros

### Retries

Configurados via `default_args` (veja Padrões de DAGs acima). Usar exponential backoff para evitar sobrecarregar serviços em falhas transientes.

### Callbacks de Falha

Usar `on_failure_callback` para alertas:

```python
def notify_on_failure(context):
    dag_id = context["dag"].dag_id
    task_id = context["task_instance"].task_id
    execution_date = context["execution_date"]
    log_url = context["task_instance"].log_url
    # Enviar alerta (email, Slack, PagerDuty, etc.)

default_args = {
    ...
    "on_failure_callback": notify_on_failure,
}
```

### SLAs

Definir SLAs em tasks críticas para detectar quando pipelines estão executando mais devagar que o esperado:

```python
from datetime import timedelta

ingest_orders = BigQueryInsertJobOperator(
    task_id="ingest_orders",
    sla=timedelta(hours=1),
    ...
)
```

---

## Padrões de Codificação

### Estilo Python

- Seguir PEP 8.
- Usar type hints para assinaturas de funções em utilitários de `dags/common/`.
- Importar operators de `airflow.providers.google.cloud.operators.*`.
- Manter arquivos de DAG focados — lógica de negócio pertence ao Dataform, não ao código Python da DAG.

### Task IDs

- Usar snake_case: `ingest_orders`, `compile_silver`, `run_gold`.
- Ser descritivo: task IDs devem indicar o que a task faz sem precisar ler o código.

### Documentação

- Todo arquivo de DAG deve ter uma docstring em nível de módulo explicando o propósito e agendamento do pipeline.
- Usar `doc_md=__doc__` para exibir isso na UI do Airflow.

### Variables e Connections

- Armazenar valores específicos de ambiente (project ID, região, nomes de buckets) como **Airflow Variables** ou em um módulo de constantes compartilhado (`dags/common/utils.py`).
- Usar **Airflow Connections** para autenticação de serviços — não incorporar credenciais em arquivos de DAG.
