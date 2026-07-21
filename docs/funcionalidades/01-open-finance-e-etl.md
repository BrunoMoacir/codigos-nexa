# 01 — Open Finance e Pipeline ETL

> A porta de entrada dos dados: conecta os bancos do usuário e transforma o
> extrato bruto (bagunçado, duplicado, incompleto) em transações limpas e
> classificadas que alimentam TODO o resto do produto.

## Em palavras simples

Quando você conecta seu banco na Nexa, os dados chegam "sujos": descrições
crípticas ("PGTO *NETFLX 3/12"), lançamentos duplicados, categorias erradas ou
ausentes, parcelas futuras invisíveis. O ETL é a "estação de tratamento de
água" do produto: tudo passa por 8 etapas de limpeza e enriquecimento antes de
qualquer análise. Se essa camada falhar, todas as outras recomendam bobagem —
por isso ela tem as proteções mais paranoicas do projeto.

## O que faz

- **Conexão bancária** via Pluggy (agregador Open Finance): lista instituições,
  conecta contas, busca transações e saldos.
- **Webhook de transações**: o Pluggy avisa quando há dados novos; a Nexa
  processa sem o usuário abrir o app.
- **Pipeline de 8 estágios** (`app/forecast/etl/runner.py`):
  1. **Data Ingestor** — normalização Polars + `BankStrategy` (parsing
     específico por banco: Nubank, Itaú, Inter, default);
  2. **Transaction Classifier** — categorização por regras/ML;
  3. **Recurring Detector** — assinaturas e parcelamentos;
  4. **PF/PJ Context Classifier** — separa pessoal × empresa (ver doc 05);
  5. **Shadow Invoice Detection** — obrigações futuras (ver abaixo);
  6. **Data Quality Validator** — valida o resultado antes de persistir;
  7. **User Profile Analyzer** — perfil de renda e comportamento;
  8. **Save to Database** — persistência em `transactions_clean`.

## As proteções contra dados ruins (o que torna o resto confiável)

| Proteção | Onde | O que protege |
|---|---|---|
| **Dedup** | `app/forecast/etl/dedup/` | O mesmo lançamento vindo duas vezes (reconexão, webhook repetido) não vira gasto dobrado |
| **Data Quality Validator** | `etl/data_quality.py` | Transação sem data/valor, valores absurdos, datas futuras — descartadas ou marcadas antes de contaminar projeções |
| **Shadow Invoices** | `core/shadow_invoices.py` + estágio 5 | O extrato só mostra o passado; parcelas e assinaturas comprometem o caixa FUTURO. O detector projeta essas obrigações ("faturas-sombra") para o safe-to-spend não prometer dinheiro já comprometido. `normalize_merchant()` limpa a descrição (remove números, domínios, palavras genéricas) para agrupar "NETFLX 3/12" e "NETFLIX.COM 4/12" como o mesmo compromisso |
| **Detector de assinaturas v2** | `subscriptions/shadow_invoices/subscription_detector.py` | 5 critérios TODOS obrigatórios (valor fixo ±10%, 3+ meses consecutivos, categoria elegível OU keyword positiva, sem keyword negativa, sem keyword de parcela) — evita marcar aluguel ou conta de luz como "assinatura" |
| **Spending Anomaly Detector** | `etl/spending_anomaly_detector.py` | Gasto ≥2,5× o padrão histórico vira alerta, não distorção silenciosa da média |
| **Income Profiler** | `etl/income_profiler.py` | Renda real ≠ soma de créditos: filtra transferências entre contas próprias e entradas não-recorrentes. TODOS os thresholds do produto dependem desse número |
| **Mixed-use Detector** | `etl/mixed_use_detector.py` | Estabelecimentos usados tanto para PF quanto PJ (mercado que é estoque do MEI) |
| **Webhook assinado** | `core/webhook_security.py` | Segredo comparado em tempo constante; produção sem segredo → 503 fail-closed; a identidade do usuário é resolvida server-side pelo `item_id`, nunca confiada no payload |

## Como funciona (técnico)

- **Endpoints**: `GET /pluggy/institutions`, `POST /pluggy/connect`,
  `GET /pluggy/accounts/{user_id}`, `GET /pluggy/transactions/{user_id}`,
  `POST /transactions/webhook` (assinado).
- **Integração**: `app/core/integrations/pluggy.py` (+ `pluggy_mock.py` para
  dev sem credenciais). Itens conectados em `pluggy_items`; saldos em
  `account_balances`.
- **DataFrames**: Polars em todo o pipeline (performance em séries grandes).
- **Persistência**: PostgreSQL (`transactions_clean`, índice `user_id, date`)
  com espelho DuckDB para dev/histórico analítico.
- **Padrão Strategy**: `etl/bank_strategy/` — cada banco com parser próprio;
  banco desconhecido usa o default.

## O que NÃO faz

- **Não faz screen scraping** — só Open Finance regulado via Pluggy.
- **Não inicia pagamentos** (Open Finance fase 4 / F6 sweep está no roadmap).
- **Não corrige categoria retroativamente sozinho** quando o usuário discorda —
  existe `context_overrides` para correção manual PF/PJ, mas não um fluxo
  geral de re-categorização ensinada pelo usuário.
- **Não sincroniza em tempo real** — depende do ciclo de atualização do Pluggy
  e do webhook; não há long-polling/streaming.

## Gaps e limitações

- **Dependência de um único agregador** (Pluggy): custo por conexão e risco de
  fornecedor. Mitigação futura: conector direto às APIs Open Finance (esforço
  alto — certificação).
- **Classificador de categorias é majoritariamente regras** — docstring do
  estágio 2 menciona CatBoost, mas o modelo treinado em produção é o PF/PJ;
  categorias vêm de regras + o que o banco já manda.
- Alguns TODOs históricos no forecast mencionam "conectar Postgres" — o
  pipeline já lê de `transactions_clean` (DuckDB/PG); os comentários estão
  defasados em relação ao código.
- **Webhook não tem fila** — processamento síncrono; volume alto de webhooks
  simultâneos seria melhor servido por fila (Redis/worker) no futuro.
