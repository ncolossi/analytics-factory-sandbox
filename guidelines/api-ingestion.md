# Ingestão via APIs

## Motor de Execução: Cloud Run Jobs

**Cloud Run Jobs** é o motor de execução para ingestão de dados de APIs externas. Cada job encapsula a lógica de extração de uma API específica, empacotada como container Docker, e é acionado pelo **Cloud Composer** como parte do pipeline de orquestração.

O Cloud Composer gerencia **quando** e **em qual ordem** os jobs de ingestão executam. O Cloud Run Job gerencia **como** extrair os dados da API e onde depositá-los.

```
API Externa → [Cloud Run Job] → GCS (landing zone) → [BigQuery Load Job] → bronze_*
                                                         (orquestrado pelo Composer)
```

---

## Arquitetura

### Fluxo Padrão

1. **Composer aciona** o Cloud Run Job via `CloudRunExecuteJobOperator`.
2. **Cloud Run Job extrai** dados da API e grava arquivos no GCS (landing zone).
3. **Composer aciona** o load job do BigQuery para carregar os dados do GCS na tabela bronze.
4. **Dataform transforma** os dados nas camadas silver e gold (fluxo existente).

### Por que Cloud Run Jobs

| Aspecto | Cloud Run Jobs | Alternativas (Cloud Functions, código na DAG) |
|---------|---------------|----------------------------------------------|
| Timeout | Até 24h | Cloud Functions: 9min. Código na DAG: bloqueia o worker |
| Recursos | Até 32 GiB RAM, 8 vCPUs | Limitado pelo worker do Composer |
| Dependências | Container isolado — qualquer runtime | Restrito ao ambiente do Composer |
| Retry | Retry nativo por task attempt | Gerenciado manualmente |
| Escalabilidade | Múltiplas tasks paralelas | Limitado ao paralelismo do Composer |
| Isolamento | Falha no job não afeta o Composer | Falha no worker impacta outras DAGs |

---

## Estrutura do Repositório

```
ingestion/
└── cloudrun/
    ├── {domain}/
    │   └── {source}/
    │       ├── Dockerfile
    │       ├── main.py
    │       ├── requirements.txt
    │       └── cloudbuild.yaml        # (opcional) build e deploy automatizado
    ├── sales/
    │   └── api_orders/
    │       ├── Dockerfile
    │       ├── main.py
    │       └── requirements.txt
    ├── marketing/
    │   └── api_campaigns/
    │       ├── Dockerfile
    │       ├── main.py
    │       └── requirements.txt
    └── common/
        ├── base.py                    # Classe base para extração
        └── gcs_writer.py             # Utilitário para escrita no GCS
```

**Regras**:
- Espelhar a estrutura de domínios do lake: `ingestion/cloudrun/{domain}/{source}/`.
- Um diretório por source/API.
- Cada diretório contém um `Dockerfile`, `main.py` e `requirements.txt` autocontidos.
- Código compartilhado entre jobs fica em `ingestion/cloudrun/common/`.

---

## Nomenclatura

### Nome do Cloud Run Job

**Padrão**: `ingest-{domain}-{source}`

| Componente | Descrição | Exemplos |
|-----------|-------------|----------|
| `domain` | Domínio de negócio | `sales`, `marketing`, `finance` |
| `source` | API ou sistema de origem | `api-orders`, `api-campaigns`, `api-invoices` |

**Exemplos**:
- `ingest-sales-api-orders` — extração de pedidos da API de vendas
- `ingest-marketing-api-campaigns` — extração de campanhas da API de marketing
- `ingest-finance-api-invoices` — extração de faturas da API financeira

**Regras**:
- Tudo em minúsculas, usando hífens como separadores (convenção de recursos Cloud Run).
- Prefixo `ingest-` obrigatório para identificar jobs de ingestão.

### Diretórios no GCS (Landing Zone)

**Padrão**: `gs://{project_id}-data-landing/cloudrun/{domain}/{source}/{execution_date}/`

**Exemplos**:
- `gs://my-project-data-landing/cloudrun/sales/api_orders/2025-01-15/`
- `gs://my-project-data-landing/cloudrun/marketing/api_campaigns/2025-01-15/`

**Regras**:
- Particionar arquivos por data de execução para facilitar rastreabilidade e reprocessamento.
- Formato dos arquivos: preferir `JSONL` (newline-delimited JSON) para dados de API. Usar `PARQUET` quando a API já fornecer dados estruturados com schema estável.

---

## Padrões de Código

### Estrutura do main.py

```python
"""Ingestão de pedidos da API de vendas.

Extrai pedidos da API de vendas e grava como JSONL no GCS.
Suporta extração incremental por data.
"""

import json
import os
from datetime import datetime

import requests
from google.cloud import storage


def extract_from_api(
    base_url: str,
    api_key: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Extrai registros da API com paginação."""
    records = []
    page = 1

    while True:
        response = requests.get(
            f"{base_url}/orders",
            headers={"Authorization": f"Bearer {api_key}"},
            params={
                "start_date": start_date,
                "end_date": end_date,
                "page": page,
                "per_page": 100,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if not data["results"]:
            break

        records.extend(data["results"])
        page += 1

    return records


def write_to_gcs(
    records: list[dict],
    bucket_name: str,
    destination_path: str,
) -> str:
    """Grava registros como JSONL no GCS."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_path)

    jsonl_content = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    blob.upload_from_string(jsonl_content, content_type="application/jsonl")

    return f"gs://{bucket_name}/{destination_path}"


def main():
    project_id = os.environ["PROJECT_ID"]
    api_key = os.environ["API_KEY"]
    base_url = os.environ["API_BASE_URL"]
    execution_date = os.environ.get("EXECUTION_DATE", datetime.now().strftime("%Y-%m-%d"))

    bucket_name = f"{project_id}-data-landing"
    destination_path = f"cloudrun/sales/api_orders/{execution_date}/orders.jsonl"

    records = extract_from_api(base_url, api_key, execution_date, execution_date)

    if records:
        gcs_uri = write_to_gcs(records, bucket_name, destination_path)
        print(f"Gravados {len(records)} registros em {gcs_uri}")
    else:
        print(f"Nenhum registro encontrado para {execution_date}")


if __name__ == "__main__":
    main()
```

### Regras de Implementação

- **Paginação**: Sempre implementar paginação completa. Nunca assumir que a API retorna todos os registros em uma única chamada.
- **Timeout**: Definir timeout explícito em todas as chamadas HTTP (`timeout=30` como padrão).
- **Idempotência**: O job deve ser idempotente — re-executar com os mesmos parâmetros produz o mesmo resultado sem duplicar dados no GCS (sobrescrever o mesmo path).
- **Parâmetros via variáveis de ambiente**: Configurações (URLs, datas, project ID) são passadas via variáveis de ambiente, injetadas pelo Composer no momento da execução.
- **Sem lógica de transformação**: O job de ingestão extrai e grava dados brutos. Qualquer limpeza ou transformação pertence ao Dataform.
- **Logging**: Usar `print()` ou `logging` padrão do Python — Cloud Run captura stdout/stderr automaticamente no Cloud Logging.
- **Exit code**: Encerrar com exit code 0 em sucesso e diferente de 0 em falha. Cloud Run e Composer usam isso para determinar o status da task.

---

## Containerização

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

### requirements.txt

```
requests>=2.31.0
google-cloud-storage>=2.14.0
```

**Regras**:
- Usar imagens base slim para reduzir tamanho e superfície de ataque.
- Fixar versões de dependências para builds reproduzíveis.
- Não incluir credenciais na imagem — usar Workload Identity ou o service account padrão do Cloud Run.

### Build e Deploy

As imagens são armazenadas no **Artifact Registry**:

```bash
# Build e push
gcloud builds submit \
  --tag {region}-docker.pkg.dev/{project_id}/ingestion/ingest-{domain}-{source}:latest \
  ingestion/cloudrun/{domain}/{source}/

# Criar/atualizar o Cloud Run Job
gcloud run jobs create ingest-{domain}-{source} \
  --image {region}-docker.pkg.dev/{project_id}/ingestion/ingest-{domain}-{source}:latest \
  --region {region} \
  --service-account ingestion-sa@{project_id}.iam.gserviceaccount.com \
  --set-secrets "API_KEY=api-key-{source}:latest" \
  --set-env-vars "PROJECT_ID={project_id}" \
  --memory 512Mi \
  --cpu 1 \
  --task-timeout 3600s \
  --max-retries 1
```

---

## Integração com Composer

### Operator

Usar `CloudRunExecuteJobOperator` para acionar Cloud Run Jobs a partir de DAGs do Airflow:

```python
from airflow.providers.google.cloud.operators.cloud_run import (
    CloudRunExecuteJobOperator,
)

ingest_orders = CloudRunExecuteJobOperator(
    task_id="ingest_orders",
    project_id=PROJECT_ID,
    region=REGION,
    job_name="ingest-sales-api-orders",
    overrides={
        "container_overrides": [
            {
                "env": [
                    {"name": "EXECUTION_DATE", "value": "{{ ds }}"},
                    {"name": "PROJECT_ID", "value": PROJECT_ID},
                ],
            }
        ],
    },
    deferrable=True,
)
```

**Regras**:
- Usar `deferrable=True` para não bloquear o worker do Airflow enquanto o job executa.
- Passar `EXECUTION_DATE` como variável de ambiente usando o template `{{ ds }}` do Airflow para garantir idempotência.
- Não duplicar secrets no Composer — os secrets são configurados no Cloud Run Job e herdados na execução.

### Padrão de Pipeline com Ingestão via API

```python
"""Sales daily refresh pipeline.

Ingests order data from the sales API via Cloud Run Job,
loads into bronze layer, then triggers Dataform for silver and gold.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.google.cloud.operators.bigquery import (
    BigQueryInsertJobOperator,
)
from airflow.providers.google.cloud.operators.cloud_run import (
    CloudRunExecuteJobOperator,
)
from airflow.providers.google.cloud.operators.dataform import (
    DataformCreateCompilationResultOperator,
    DataformCreateWorkflowInvocationOperator,
)
from airflow.utils.task_group import TaskGroup

PROJECT_ID = "your-gcp-project-id"
REGION = "your-region"
DATAFORM_REPOSITORY = "your-dataform-repo"
LANDING_BUCKET = f"{PROJECT_ID}-data-landing"

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
    tags=["sales", "daily", "api-ingestion"],
    max_active_runs=1,
    doc_md=__doc__,
) as dag:

    # --- Extração: Cloud Run Job ---
    with TaskGroup("api_extraction") as extraction:
        extract_orders = CloudRunExecuteJobOperator(
            task_id="extract_orders",
            project_id=PROJECT_ID,
            region=REGION,
            job_name="ingest-sales-api-orders",
            overrides={
                "container_overrides": [
                    {
                        "env": [
                            {"name": "EXECUTION_DATE", "value": "{{ ds }}"},
                            {"name": "PROJECT_ID", "value": PROJECT_ID},
                        ],
                    }
                ],
            },
            deferrable=True,
        )

    # --- Bronze: Carga do GCS para BigQuery ---
    with TaskGroup("bronze_ingestion") as bronze:
        load_orders = BigQueryInsertJobOperator(
            task_id="load_orders",
            configuration={
                "load": {
                    "sourceUris": [
                        f"gs://{LANDING_BUCKET}/cloudrun/sales/api_orders/{{{{ ds }}}}/orders.jsonl"
                    ],
                    "destinationTable": {
                        "projectId": PROJECT_ID,
                        "datasetId": "bronze_sales",
                        "tableId": "orders",
                    },
                    "sourceFormat": "NEWLINE_DELIMITED_JSON",
                    "writeDisposition": "WRITE_APPEND",
                }
            },
            location=REGION,
        )

    # --- Silver e Gold: Transformações Dataform ---
    with TaskGroup("silver_transformations") as silver:
        compile_silver = DataformCreateCompilationResultOperator(
            task_id="compile_silver",
            project_id=PROJECT_ID,
            region=REGION,
            repository_id=DATAFORM_REPOSITORY,
            compilation_result={"git_commitish": "main"},
        )

        run_silver = DataformCreateWorkflowInvocationOperator(
            task_id="run_silver",
            project_id=PROJECT_ID,
            region=REGION,
            repository_id=DATAFORM_REPOSITORY,
            workflow_invocation={
                "compilation_result": (
                    "{{ task_instance.xcom_pull("
                    "task_ids='silver_transformations.compile_silver')['name'] }}"
                ),
                "invocation_config": {
                    "included_tags": ["silver", "sales"],
                    "transitive_dependencies_included": True,
                },
            },
        )

        compile_silver >> run_silver

    with TaskGroup("gold_transformations") as gold:
        compile_gold = DataformCreateCompilationResultOperator(
            task_id="compile_gold",
            project_id=PROJECT_ID,
            region=REGION,
            repository_id=DATAFORM_REPOSITORY,
            compilation_result={"git_commitish": "main"},
        )

        run_gold = DataformCreateWorkflowInvocationOperator(
            task_id="run_gold",
            project_id=PROJECT_ID,
            region=REGION,
            repository_id=DATAFORM_REPOSITORY,
            workflow_invocation={
                "compilation_result": (
                    "{{ task_instance.xcom_pull("
                    "task_ids='gold_transformations.compile_gold')['name'] }}"
                ),
                "invocation_config": {
                    "included_tags": ["gold", "sales"],
                    "transitive_dependencies_included": True,
                },
            },
        )

        compile_gold >> run_gold

    # --- Fluxo do pipeline ---
    extraction >> bronze >> silver >> gold
```

---

## Configuração e Secrets

### Variáveis de Ambiente

| Variável | Origem | Descrição |
|----------|--------|-----------|
| `PROJECT_ID` | Composer override | ID do projeto GCP |
| `EXECUTION_DATE` | Composer override (`{{ ds }}`) | Data de referência da execução |
| `API_BASE_URL` | Cloud Run Job env | URL base da API |
| `API_KEY` | Secret Manager (montado no Cloud Run) | Chave de autenticação da API |

**Regras**:
- Variáveis dinâmicas (datas, project ID) são injetadas pelo Composer via `overrides`.
- Variáveis estáticas (URLs base) são configuradas diretamente no Cloud Run Job.
- **Secrets nunca ficam em variáveis de ambiente estáticas** — usar montagem do Secret Manager via `--set-secrets`.

### Secret Manager

```bash
# Criar o secret
echo -n "your-api-key-value" | gcloud secrets create api-key-{source} --data-file=-

# Conceder acesso à service account de ingestão
gcloud secrets add-iam-policy-binding api-key-{source} \
  --member="serviceAccount:ingestion-sa@{project_id}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

---

## Tratamento de Erros

### No Cloud Run Job

- Usar `response.raise_for_status()` para falhar explicitamente em respostas HTTP não-2xx.
- Implementar retry com backoff exponencial para erros transientes da API (429, 500, 502, 503):

```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
```

- Registrar métricas de extração (registros extraídos, páginas percorridas, tempo total) via logging estruturado para diagnóstico.

### No Composer

- Retries de task são gerenciados via `default_args` (conforme padrão de orquestração existente).
- Se o Cloud Run Job falhar, o Composer registra o erro e aciona o `on_failure_callback`.
- Usar `deferrable=True` no operator para evitar que falhas de jobs longos bloqueiem workers do Airflow.

---

## IAM

### Service Account de Ingestão

| Service Account | Propósito | Roles Principais |
|----------------|---------|-----------|
| `ingestion-sa` | Execução de Cloud Run Jobs de ingestão | `roles/storage.objectCreator` (bucket de landing), `roles/secretmanager.secretAccessor` |

**Regras**:
- A SA de ingestão tem acesso de **escrita apenas no bucket de landing** — nunca diretamente no BigQuery.
- A carga no BigQuery bronze é feita pela SA do Composer via `BigQueryInsertJobOperator`.
- Cada secret da API é acessível apenas pela SA de ingestão (princípio do menor privilégio).

