# Analytics Factory Sandbox

Um **harness** para desenvolvimento agêntico de Data & Analytics no Google Cloud:
o conjunto de instruções, skills, guardrails e avaliações que cercam o modelo de
IA e o mantêm focado, seguro e produtivo ao construir data pipelines (Medallion
Bronze → Silver → Gold com Dataform, Cloud Composer e Cloud Run).

> **Nota:** repositório em desenvolvimento ativo.

> Conceito de harness baseado em *Harness Engineering* (`Agent = Model + Harness`):
> o modelo é só um dos insumos; o que determina o comportamento do agente é o que
> o cerca — instruções, ferramentas, sandbox, orquestração, guardrails e
> observabilidade.

## Como o harness funciona

| Componente | Onde vive | Papel |
|------------|-----------|-------|
| **Constituição** | [AGENTS.md](AGENTS.md) | Instruções canônicas, neutras de ferramenta — arquivo único, lido diretamente pelo agente. |
| **Overrides** | [guidelines/](guidelines/) | Regras específicas da organização **sobre** as skills (não duplicam o how-to). |
| **Skills** | `.agents/skills/` | Data Agent Kit + Cloud Run — o how-to de Dataform, Composer, ingestão. |
| **Guardrails** | [tools/checks/](tools/checks/) | Validadores que aplicam as regras inegociáveis via **pre-commit + CI**. |
| **Evals** | [evals/](evals/) | Self-test determinístico (golden + casos negativos) + golden tasks de agente. |
| **Workflows** | `.agents/workflows/` | Procedimentos slash do Antigravity (`/scaffold-domain`, `/review`, `/run-evals`). |

**Idioma:** instruções e código em inglês; **descrições de dados no BigQuery
(dataset/tabela/coluna) sempre em português** (regra 6 do AGENTS.md).

## Setup

### Pré-requisitos

Um **projeto GCP de desenvolvimento** com permissão para habilitar APIs e criar
recursos, além do [Antigravity 2.0](https://antigravity.google/),
[Git](https://git-scm.com/), [Node.js LTS](https://nodejs.org/) (npm),
[Python 3.12+](https://www.python.org/) e o
[Google Cloud SDK](https://cloud.google.com/sdk/docs/install).

> **Git** é necessário localmente — os guardrails rodam via `pre-commit` e o gate
> de CI é acionado por `git push`.

```bash
gcloud auth login
gcloud config set project SEU_PROJETO_ID
gcloud auth application-default login
npm install -g @dataform/cli      # Dataform CLI
```

### Configurando o Antigravity

O [Antigravity 2.0](https://antigravity.google/) é a IDE agêntica usada neste
repositório. Ao abrir o projeto, ele carrega automaticamente a constituição
`AGENTS.md`, as regras em `.agents/rules/`, os procedimentos slash em
`.agents/workflows/` e as skills em `.agents/skills/`.

1. Abra este repositório no Antigravity.
2. Faça **login com seu projeto do Google Cloud** de desenvolvimento
   (autenticação via Google Cloud / Vertex AI), apontando o agente para o
   projeto onde você tem permissão de criar recursos — em vez de uma conta
   pessoal.
3. Valide que as APIs básicas (BigQuery, Dataform, Composer) estão habilitadas
   no projeto.
4. Acione os procedimentos com `/` (ex.: `/scaffold-domain`, `/review`,
   `/run-evals`).

## Guardrails e Evals

As regras inegociáveis do [AGENTS.md](AGENTS.md) são aplicadas por código
determinístico — não por confiança — de forma **agnóstica à ferramenta** (vale
para o agente e para commits humanos):

```bash
python3 tools/checks/run_checks.py     # guardrails (padrões proibidos + Dataform)
python3 evals/run_evals.py             # evals (golden + casos negativos)
```

Ative o bloqueio local e replique o gate no CI:

```bash
pip install pre-commit && pre-commit install   # .pre-commit-config.yaml
```

O CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) roda os mesmos checks
em todo push/PR. **Antigravity não tem mecanismo de hooks**, por isso a aplicação
determinística vive no git (pre-commit) + CI, e não na ferramenta.

## Custos de Nuvem

O uso de BigQuery, Dataform, Cloud Composer, Cloud Storage e dos modelos de IA
(via Vertex AI) é cobrado conforme os [preços do Google Cloud](https://cloud.google.com/pricing).
Configure [alertas de orçamento](https://console.cloud.google.com/billing) — o
consumo de tokens cresce rápido em sessões longas e em modo autônomo.

## Licença

Apache 2.0 — veja o arquivo [LICENSE](LICENSE).
