# Analytics Factory Sandbox

Setup básico para desenvolvimento agêntico de Data & Analytics em Google Cloud, apoiado por ferramentas como o **Gemini CLI** e extensões de IDE que aceleram a criação e manutenção de pipelines de dados com assistência de IA.

## Guidelines

O diretório `guidelines/` contém documentação de referência sobre arquitetura, nomenclaturas, padrões de transformação e orquestração. Esses guidelines servem como contexto para os agentes de IA e podem — e devem — ser ajustados para refletir as regras, ferramentas e convenções específicas de cada cenário ou organização.

Os arquivos de instrução para agentes (`GEMINI.md`, etc.) referenciam esses guidelines para garantir que o código gerado siga os padrões definidos.

## Setup

### Pré-requisito

Um **projeto GCP de desenvolvimento** onde você tenha permissões para habilitar APIs e criar recursos.

### 1. Configure o VSCode

Instale o [Visual Studio Code](https://code.visualstudio.com/) e configure seu ambiente local (terminal integrado, extensões básicas, tema, etc.).

### 2. Instale o Node.js e npm

O **npm** é necessário para instalar o Dataform CLI e o Gemini CLI. Ele é distribuído junto com o [Node.js](https://nodejs.org/).

Baixe e instale a versão **LTS** recomendada em: https://nodejs.org/en/download

Verifique a instalação:

```bash
node --version
npm --version
```

### 3. Configure o gcloud CLI

Instale o [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) e autentique com seu projeto de desenvolvimento:

```bash
gcloud auth login
gcloud config set project SEU_PROJETO_ID
gcloud auth application-default login
```

### 4. Configure o Dataform CLI

Instale o [Dataform CLI](https://cloud.google.com/dataform/docs/use-dataform-cli) globalmente:

```bash
npm install -g @dataform/cli
```

Verifique a instalação:

```bash
dataform --version
```

### 5. Configure o Gemini CLI

Instale o [Gemini CLI](https://github.com/google-gemini/gemini-cli) e autentique com seu projeto de desenvolvimento:

```bash
npm install -g @google/gemini-cli
```

Após a instalação, autentique:

```bash
gemini auth login
```

### 6. Extensões do VSCode

Instale as seguintes extensões:

- **Gemini CLI Companion** — integração do Gemini CLI com o VSCode.
- **Google Cloud Data Agent Kit** — assistente agêntico para desenvolvimento de dados em GCP.

Após instalar o **Data Agent Kit**:

1. Vá em **Settings** da extensão.
2. Aponte para seu **projeto GCP de desenvolvimento**.
3. Valide que as **APIs básicas estão habilitadas** (BigQuery, Dataform, Composer, etc.).
4. Instale a extensão do Data Agent Kit no Gemini CLI: vá em **Settings** → **Configure MCP Servers** → **Configure for CLI Agents**.

## Conversando com o Agente

1. Abra um **terminal integrado** no VSCode (`Ctrl+`` ` ou `Terminal > New Terminal`).

2. Inicie o Gemini CLI:

   ```bash
   gemini
   ```

3. Configure a autenticação para Vertex AI:

   ```
   /auth vertex
   ```

4. Selecione o modelo desejado:

   ```
   /model gemini-3.1-pro-preview
   ```

5. Quando estiver confiante no funcionamento do agente e quiser aprovar ações automaticamente, ative o **yolo mode** com `Ctrl+Y`.

   > No yolo mode o agente executa comandos sem pedir confirmação. Use com cuidado e apenas em ambientes de desenvolvimento.
