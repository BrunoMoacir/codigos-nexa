# 🏗️ Nexa AI: Core Engine (Funcionalidade 1) FLUXO DE CAIXA E PREVISÃO

> **Status:** MVP (Fase 1) | **Stack:** Python, Polars, PyTorch, LangGraph

Este documento descreve a arquitetura de engenharia da Nexa. Nosso objetivo não é apenas criar um "chatbot", mas um **Agente Financeiro Autônomo** que conversa com dados estruturados. A premissa central é: **IA Generativa explica, Matemática Determinística calcula.**

---

## 🛠️ Tech Stack & Decisões de Engenharia 

| Componente | Tecnologia | Por que escolhemos isso? (Decision Log) |
| :--- | :--- | :--- |
| **Linguagem** | `Python 3.11+` | Padrão da indústria para IA e Engenharia de Dados. |
| **Processamento** | `Polars` (Rust) | Substitui o Pandas. Processamento paralelo, memória eficiente e *lazy execution*. Vital para escalar transações bancárias. |
| **Orquestração** | `LangGraph` | Evolução do LangChain. Permite fluxos cíclicos e gestão de estado (memória) para conversas longas. |
| **Classificação** | `CatBoost` | Modelo *State-of-the-art* para dados tabulares. Vence Redes Neurais em dados financeiros sujos. |
| **Previsão** | `NeuralProphet` | Baseado em PyTorch. Híbrido de séries temporais com regressão linear. Ideal para sazonalidade financeira. |
| **Validação** | `Pydantic` | Garante tipagem estrita. A IA não pode alucinar tipos de dados (ex: retornar string onde deve ser float). |

---

## 🌊 O Pipeline de Dados (Data Flow)

O ciclo de vida do dado na Nexa segue 4 estágios críticos, desenhados para garantir velocidade e consistência.

### Estágio 1: A Ingestão (Raw Ingest)
*Objective: Zero data loss.*

1.  **Entrada:** Webhooks de Open Finance (Pluggy/Belvo) recebem o evento.
2.  **Ação:** O JSON cru é salvo imediatamente no **Data Lake** (`raw_events`).
    * *Regra:* Nunca processamos o dado na entrada. Salvamos primeiro para auditoria e *replay* em caso de erro.

### Estágio 2: A Refinaria (Refinement & Waterfall)
*Objective: Transformar JSON sujo em Tabela Estruturada (`transactions_clean`).*

Utilizamos uma estratégia de classificação em **Cascata (Waterfall)** para otimizar custos e latência:

1.  **Nível 0 (Override Manual):** Verifica se o usuário já classificou este estabelecimento antes. Se sim, aplica a regra dele.
2.  **Nível 1 (Regex/Hard-coded):** Verifica padrões óbvios (ex: "Uber", "Netflix"). Custo zero, latência < 1ms.
3.  **Nível 2 (CatBoost/Modelo):** Se falhar no Regex, passa pelo modelo treinado.
4.  **Nível 3 (LLM Fallback):** Último recurso. Envia para GPT-4o-mini classificar. O resultado é salvo para treinar o CatBoost futuramente (*Active Learning*).

### Estágio 3: O Motor de Previsão (The Oracle)
*Objective: Projetar Fluxo de Caixa para 30 dias.*

Não usamos apenas IA. Usamos uma abordagem híbrida:
* **Motor Determinístico (Python):** Identifica padrões exatos (`is_recurring=True`). Se o aluguel é dia 10, ele projeta exatamente dia 10.
* **Motor Probabilístico (NeuralProphet):** Analisa gastos variáveis (Mercado, Lazer). Entende tendências e sazonalidade (ex: gasta mais no fim de semana).
* **Resultado:** Soma dos dois motores gera o *Saldo Projetado*.

### Estágio 4: A Interface do Agente (Chat)
*Objective: Explicar os números com empatia.*

1.  Usuário pergunta -> **LangGraph** identifica a intenção.
2.  **Tool Calling:** O Agente executa funções Python (ex: `get_forecast()`). **A IA não calcula nada de cabeça.**
3.  **Resposta:** O LLM recebe o JSON calculado e gera a resposta em texto natural ("Você vai fechar o mês no azul...").

---

## 💾 Schema de Dados (Core)

A tabela `transactions_clean` é o coração do sistema.

| Coluna | Tipo (Polars) | Descrição e Regras |
| :--- | :--- | :--- |
| `transaction_id` | String | Hash único. Chave primária. |
| `date` | Date | Data de competência. |
| `amount` | Float64 | Positivo (Entrada), Negativo (Saída). |
| `description_raw` | String | O texto original sujo do banco. |
| `merchant_clean` | String | Nome higienizado para exibição (ex: "Padaria do Zé"). |
| `category_level_1` | Categorical | Categoria Macro (Alimentação, Transporte, Lazer). |
| `is_recurring` | Boolean | Se `True`, alimenta o Motor Determinístico. |
| `status` | Categorical | `POSTED` (Confirmado) ou `PENDING` (Não impacta saldo final ainda). |
| `is_manual_override`| Boolean | Se `True`, a IA está proibida de reclassificar essa linha. |
| `confidence_score` | Float32 | 0.0 a 1.0. Se < 0.7, o Chat deve pedir confirmação ao usuário. |

---

## 🚨 Regras de Ouro (Engineering Principles)

1.  **Regras > IA:** Se podemos resolver com `if/else` ou Regex, não usamos LLM. É mais rápido, barato e previsível.
2.  **A IA não inventa números:** Todo número mostrado no chat deve vir de uma função Python determinística (`tool`). O LLM apenas lê o número e o coloca numa frase.
3.  **Cold Start Strategy:** No dia 1, não temos modelo treinado. Dependemos pesadamente de Regex e LLM Fallback até termos dataset suficiente (5k records) para treinar o CatBoost.
4.  **Privacy First:** Identificadores pessoais (PII) são mascarados antes de qualquer envio para APIs de LLM externas.


---

## 💾 Schema de Dados (`transactions_clean`)

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `transaction_id` | String | PK. Hash único. |
| `date` | Date | Data de competência. |
| `amount` | Float64 | (-) Saída, (+) Entrada. |
| `merchant_clean` | String | Nome higienizado (ex: "iFood"). |
| `category` | Categorical | Macro categoria. |
| `is_recurring` | Boolean | Define qual motor de previsão usará este dado. |
| `status` | Categorical | `POSTED` ou `PENDING`. |
| `is_manual_override`| Boolean | Se `True`, a IA não toca mais. |
| `confidence_score` | Float32 | 0.0 a 1.0. |

---

# 🚀 Parte 2: Roteiro de Implementação (Passo a Passo)

Siga esta ordem para construir o módulo.

## 📂 1. Estrutura de Pastas

```bash
/nexa-core
├── /app
│   ├── /api            # Endpoints FastAPI (Webhooks, Chat)
│   ├── /core           # Configs (Env vars, DB connection)
│   ├── /services
│   │   ├── ingestor.py # Lógica Polars (Limpeza)
│   │   ├── classifier.py # Lógica Waterfall
│   │   ├── forecaster.py # Motor Híbrido
│   │   └── agent.py    # LangGraph Logic
│   ├── /models         # Pydantic Schemas & SQL Models
│   └── /utils          # Helpers
├── requirements.txt
└── docker-compose.yml


🛠️ 2. Tarefas de Desenvolvimento
Passo 2.1: Engenharia de Dados (Ingestão)

[ ] Criar tabela transactions no Postgres com o schema definido acima.

[ ] Implementar NexaIngestor em services/ingestor.py usando Polars.

[ ] Implementar lógica de Regex em services/classifier.py para classificar "Uber", "Ifood", "Netflix".

Passo 2.2: O Motor de Previsão

[ ] Criar função detect_recurring(): Agrupa transações e identifica padrões fixos.

[ ] Criar função generate_cashflow_projection():

Gera dataframe de 30 dias futuros.

Preenche com recorrências fixas (Motor Determinístico).

(Opcional MVP) Roda NeuralProphet para variáveis.

Retorna JSON: [{date: '2025-10-01', balance: 1500}, ...].

Passo 2.3: O Agente (LangGraph)

[ ] Definir Tools em services/agent.py:

@tool get_current_balance(user_id)

@tool get_forecast_analysis(user_id)

[ ] Configurar Grafo: Nó de Agente (LLM) -> Nó de Ferramenta -> Nó de Resposta.

[ ] Prompt de Sistema: "Você é um Economista Chefe. Não invente números. Use as ferramentas."

Passo 2.4: API Externa

[ ] Endpoint POST /webhook/transaction: Recebe JSON e chama Ingestor.

[ ] Endpoint POST /chat/message: Recebe texto do usuário e invoca LangGraph.
