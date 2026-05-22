# Topologia do Projeto

## Arquitetura de Projeto Único

Todos os serviços rodam dentro de um **único projeto GCP**. Isso simplifica IAM, rede, faturamento e integração entre serviços.

**Região preferencial**: `southamerica-east1` (São Paulo). Todos os recursos — datasets do BigQuery, repositório Dataform, ambiente do Cloud Composer e buckets do GCS — devem ser provisionados nesta região, salvo restrição técnica ou de negócio que justifique outra escolha.

```
┌───────────────────────────────────────────────────────┐
│                     GCP Project                       │
│                                                       │
│  ┌─────────────────┐                                  │
│  │  Cloud Composer  │──────────────────┐              │
│  │  (Orchestration) │                  │              │
│  └──┬──────────┬───┘                  │              │
│     │ triggers │ triggers             │ triggers     │
│     ▼          │                      ▼              │
│  ┌────────────┐│             ┌────────────┐          │
│  │ Cloud Run  ││             │  Dataform  │          │
│  │ Jobs (API  ││             │  (ELT)     │          │
│  │ Ingestion) ││             └─────┬──────┘          │
│  └─────┬──────┘│                   │                 │
│        │       │                   │                 │
│        ▼       │                   │                 │
│  ┌─────────┐   │                   │                 │
│  │   GCS   │   │                   │                 │
│  │(Landing)│   │                   │                 │
│  └────┬────┘   │                   │                 │
│       │ load   │ load              │ transforms     │
│       ▼        ▼                   ▼                 │
│  ┌──────────────────────────────────────┐            │
│  │            BigQuery                   │            │
│  │          (All Layers)                 │            │
│  └──────────────────────────────────────┘            │
│         │                                            │
│  ┌──────┴──────┐                                     │
│  │             │                                     │
│  ▼             ▼                                     │
│  bronze_*    silver_*                                │
│  datasets    datasets                                │
│       │                                              │
│       ▼                                              │
│     gold_*                                           │
│     datasets                                         │
│       │                                              │
│       ▼                                              │
│  ┌────────────────┐                                  │
│  │  Consumers     │                                  │
│  │  (BI, ML, API) │                                  │
│  └────────────────┘                                  │
└───────────────────────────────────────────────────────┘
```

---

## Serviços

### BigQuery

**Papel**: Data warehouse e armazenamento do lake para todas as camadas (bronze, silver, gold).

**Configuração**:
- **Localização**: `southamerica-east1` para todos os datasets. Todos os datasets devem compartilhar a mesma localização.
- **Datasets**: Criados por combinação de camada-domínio (veja [Definição do Lake](lake-definition.md)).
- **Expiração padrão de tabelas**: Não definida — tabelas persistem até serem explicitamente removidas.
- **Criptografia**: Chaves de criptografia gerenciadas pelo Google (padrão). Usar CMEK se conformidade exigir.

**Estrutura de datasets**:

```
project-id
├── bronze_erp
├── bronze_crm
├── silver_sales
├── silver_finance
├── gold_sales
├── gold_finance
└── ...
```

### Dataform

**Papel**: Motor exclusivo para todas as operações de dados no BigQuery — transformações, cópias e movimentações entre camadas e datasets. Nenhuma operação de escrita no BigQuery deve ocorrer fora do Dataform (exceto ingestão bronze via load jobs). Processos incrementais são preferidos quando aplicáveis (veja [Transformações](transformations.md)).

**Configuração**:
- **Repositório**: Um único repositório Dataform dentro do projeto GCP.
- **Workspace**: Um workspace por desenvolvedor ou feature branch.
- **Database padrão**: O ID do projeto GCP.
- **Schema padrão**: Definido por camada nas configurações SQLX.
- **Localização padrão**: Deve corresponder à localização dos datasets do BigQuery.

**Configurações de workflow** (`workflow_settings.yaml`):

```yaml
defaultProject: your-gcp-project-id
defaultLocation: southamerica-east1
defaultDataset: silver_sales
defaultAssertionDataset: dataform_assertions
```

**Agendamento**: Workflows do Dataform são acionados por DAGs do Cloud Composer (veja [Orquestração](orchestration.md)). Invocações manuais são usadas para execuções ad-hoc durante o desenvolvimento.

### Cloud Composer

**Papel**: Orquestração de pipelines. Agenda e coordena ingestão, workflows do Dataform e tarefas auxiliares.

**Configuração**:
- **Ambiente**: Cloud Composer 2 (Airflow gerenciado).
- **Localização**: `southamerica-east1` — mesma região dos datasets do BigQuery.
- **Versão da imagem**: Última imagem estável do Composer 2.
- **Configuração de nós**: Usar padrões de autoscaling do ambiente — ajustar com base na carga de trabalho.

**Detalhes**: Veja [Orquestração](orchestration.md) para padrões de DAGs, convenções de nomenclatura e padrões de pipeline.

### Cloud Run Jobs

**Papel**: Motor de execução para ingestão de dados de APIs externas. Cada job encapsula a lógica de extração de uma API, empacotada como container Docker, e é acionado pelo Cloud Composer.

**Configuração**:
- **Localização**: `southamerica-east1` — mesma região dos demais serviços.
- **Imagens**: Armazenadas no Artifact Registry (`{region}-docker.pkg.dev/{project_id}/ingestion/`).
- **Service account**: `ingestion-sa` com acesso ao bucket de landing e Secret Manager.
- **Secrets**: Montados via Secret Manager — nunca em variáveis de ambiente estáticas.

**Detalhes**: Veja [Ingestão via APIs](api-ingestion.md) para padrões de código, containerização e integração com Composer.

### Artifact Registry

**Papel**: Registro de imagens Docker para os Cloud Run Jobs de ingestão.

**Configuração**:
- **Repositório**: `ingestion` (formato Docker).
- **Localização**: `southamerica-east1`.
- **Nomenclatura de imagens**: `{region}-docker.pkg.dev/{project_id}/ingestion/ingest-{domain}-{source}:latest`.

### Cloud Storage (GCS) — Papel de Suporte

**Papel**: Área de staging para ingestão baseada em arquivos. Não é uma camada principal do lake.

**Uso**:
- Zona de landing para arquivos antes da ingestão no BigQuery (via load jobs).
- Destino de exportação para extrações de dados do BigQuery.
- Armazenamento temporário para jobs Dataflow ou Spark (se necessário).

**Nomenclatura de buckets**: `{project_id}-data-{purpose}` (ex.: `your-project-data-landing`, `your-project-data-export`).

---

## IAM e Controle de Acesso

### Service Accounts

| Service Account | Propósito | Roles Principais |
|----------------|---------|-----------|
| `dataform-sa` | Execução de pipelines do Dataform | `roles/bigquery.dataEditor`, `roles/bigquery.jobUser` |
| `composer-sa` | Orquestração do Cloud Composer | `roles/composer.worker`, `roles/dataform.editor`, `roles/bigquery.jobUser`, `roles/run.invoker` |
| `ingestion-sa` | Execução de Cloud Run Jobs de ingestão de APIs | `roles/storage.objectCreator` (bucket landing), `roles/secretmanager.secretAccessor` |

### Acesso em Nível de Dataset

- **Datasets bronze**: Acesso de escrita limitado a service accounts de ingestão. Acesso de leitura para a SA do Dataform.
- **Datasets silver**: Acesso de escrita apenas para a SA do Dataform. Acesso de leitura para a SA do Dataform e roles de analytics.
- **Datasets gold**: Acesso de escrita apenas para a SA do Dataform. Acesso de leitura para consumidores (ferramentas de BI, analistas, pipelines de ML).

### Princípio do Menor Privilégio

- Nenhuma conta de usuário tem acesso direto de escrita a qualquer dataset do lake.
- Todas as escritas passam por service accounts gerenciadas via Dataform.
- Analistas e ferramentas de BI recebem `roles/bigquery.dataViewer` apenas nos datasets gold.

---

## Ambientes

Mesmo dentro de um único projeto, separar ambientes lógicos usando sufixos de dataset:

| Ambiente | Padrão de Dataset | Propósito |
|-------------|----------------|---------|
| Produção | `{layer}_{domain}` | Dados em produção, pipelines agendados |
| Desenvolvimento | `{layer}_{domain}_dev` | Testes de desenvolvedor, workspaces do Dataform |

**Regras**:
- Datasets de dev são efêmeros — podem ser removidos e recriados.
- Datasets de produção nunca são modificados manualmente — apenas através de pipelines do Dataform.
- Workspaces do Dataform compilam contra datasets de dev por padrão; configurações de release apontam para produção.

---

## Monitoramento e Observabilidade

### BigQuery

- **INFORMATION_SCHEMA**: Consultar `INFORMATION_SCHEMA.JOBS` e `INFORMATION_SCHEMA.TABLE_STORAGE` para monitoramento de pipelines.
- **Logs de auditoria**: Habilitar logs de auditoria do BigQuery para rastreamento de acesso a dados.
- **Uso de slots**: Monitorar utilização de slots para controle de custos.

### Dataform

- **Logs de invocação de workflow**: Rastrear sucesso/falha de cada execução do Dataform.
- **Resultados de assertions**: Assertions com falha devem acionar alertas.
- **Erros de compilação do Dataform**: Monitorar compilação do repositório no CI/CD.

### Cloud Composer

- **Histórico de execução de DAGs**: Monitorar taxas de sucesso/falha e duração das execuções na UI do Airflow.
- **Duração de tasks**: Rastrear tempos de execução em nível de task para detectar regressões de performance.
- **Saúde do scheduler**: Monitorar a saúde do ambiente Composer via métricas do Cloud Monitoring.

### Alertas

- Falhas de pipeline (falhas de DAG/task, erros de workflow do Dataform) → alertar via Cloud Monitoring e `on_failure_callback` do Airflow.
- Problemas de qualidade de dados (falhas de assertion) → alertar e bloquear processamento downstream.
- Anomalias de custo (picos inesperados de slots ou armazenamento do BigQuery) → alertas de orçamento.
