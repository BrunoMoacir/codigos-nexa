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
- **Pipeline de 8 estágios** (`app/forecast/etl/runner.py`) — detalhado abaixo.

---

## Como é calculado — o pipeline estágio a estágio

### Estágio 1 — Data Ingestor (`etl/ingestor.py`)

Normalização em Polars, na ordem: `_to_dataframe` → `_normalize_texts` →
`_apply_bank_strategies` → `_convert_types` → `_enrich_columns`.

**Padrão Strategy por banco** (`etl/bank_strategy/`): o registry escolhe o
parser pelo `bank_id`; banco desconhecido cai no `default`. Cada estratégia
declara um **tier de confiabilidade** (`BankTier`) e implementa dois métodos:

| Método | O que faz |
|---|---|
| `normalize(df)` | Correções específicas do banco: extrair merchant da descrição, corrigir sinal de `amount`, padronizar status |
| `evaluate_quality(df)` | Devolve `TRUSTED` / `DEGRADED` / `UNTRUSTED` para o lote |

Exemplo concreto — `NubankStrategy` (TIER_1):
1. Extrai o merchant com `description.split("-").list.get(-1)`, remove tudo
   após `*` (regex `\*.*`) e apara espaços → `"COMPRA NO DÉBITO - UBER *1234"`
   vira `"uber"`;
2. **Descarta a categoria enviada pelo banco** (`pl.lit(None)`) — a categoria
   do Nubank é considerada não confiável, quem categoriza é o estágio 2;
3. `evaluate_quality`: qualquer `transaction_date` nula → `UNTRUSTED`; algum
   merchant nulo → `DEGRADED`; caso contrário → `TRUSTED`.

**Dedup hash** (`core/schemas/transaction.py`): cada transação recebe

```
dedup_hash = sha256( f"{account_id}|{date_iso}|{amount}|{desc[:20].strip().upper()}" )
```

Só os **20 primeiros caracteres** da descrição entram no hash, de propósito:
"PAG UBER SAO PAULO" e "PAG UBER RIO DE JANEIRO" colapsam no mesmo prefixo
"PAG UBER", então variações de sufixo do mesmo lançamento não escapam da
deduplicação. `DefaultDedupPolicy.apply()` faz `df.unique(subset=["dedup_hash"],
keep="first")` e retorna quantas linhas removeu. A tabela de destino tem
`dedup_hash TEXT UNIQUE` + `ON CONFLICT(dedup_hash) DO NOTHING` — a defesa
existe **duas vezes**: em memória e no banco.

### Estágio 2 — Transaction Classifier (`etl/classifier.py`)

Classificação por **regex de keywords**, não por ML (o modo `RULES` é o de
produção; `ML`/`HYBRID` existem como stubs para um CatBoost futuro).

`CATEGORY_KEYWORDS` é um dicionário `categoria → lista de regex`, avaliado em
ordem de inserção; **o primeiro padrão que casar vence** (não há pontuação
competitiva entre categorias). Exemplos reais dos padrões:

| Categoria | Padrões (amostra) |
|---|---|
| Transferências | `\b(pix\|transferencia\|ted\|doc)\b`, `\b(picpay\|pagbank\|mercado\s*pago)\b` |
| Investimentos | `\b(cdb\|lci\|lca\|tesouro\|fundo)\b`, `\b(bitcoin\|cripto)\b`, `\b(poupanca\|savings)\b` |
| Alimentação | `\b(ifood\|uber\s*eats\|rappi)\b`, `\b(supermercado\|mercado\|mercearia)\b`, `\b(zona\s*sul\|guanabara\|assai\|atacadao)\b` |
| Transporte | `\b(uber\|99\|cabify\|lyft)\b`, `\b(posto\|gasolina\|combustivel)\b` |

**A confiança é derivada da cobertura do match** (`_classify_text`):

```
text_coverage = len(trecho_casado) / len(texto_completo)

coverage > 0.5          → confidence = 0.95
len(trecho_casado) > 10 → confidence = 0.90
caso contrário          → confidence = 0.85
sem match               → ("Outros", 0.50)
```

A lógica é: se o padrão cobre mais da metade da descrição, ele *é* a
descrição — alta confiança. Um match curto dentro de um texto longo pode ser
coincidência — confiança menor. `"Outros"` com 0,50 é o piso honesto: não é
"tenho 50% de certeza de que é Outros", é "não sei classificar".

### Estágio 3 — Recurring Detector (`etl/recurring_detector.py`)

Roda dois sub-detectores e devolve o DataFrame original acrescido de 4 flags:
`is_recurring`, `is_installment`, `installment_info`, `recurring_confidence`.

**SubscriptionDetector v2 — os 5 critérios, TODOS obrigatórios**
(`subscriptions/shadow_invoices/subscription_detector.py`):

1. **Filtro negativo primeiro**: qualquer descrição contendo uma das 34
   `NEGATIVE_KEYWORDS` é eliminada — moradia (`aluguel`, `condominio`, `iptu`),
   concessionárias (`enel`, `cemig`, `copel`, `sabesp`, `cedae`, `comgas`),
   genéricos (`boleto`, `fatura`, `mensalidade`, `escola`, `plano saude`,
   `seguro`). É o que impede aluguel virar "assinatura".
2. **Categoria elegível OU keyword positiva**: `predicted_category ∈ {Lazer,
   Outros}` **ou** uma das 32 `POSITIVE_KEYWORDS` (`netflix`, `spotify`,
   `amazon prime`, `disney`, `hbo`, `globoplay`, `google one`, `icloud`,
   `dropbox`, `adobe`, `notion`, `slack`, `zoom`, `kindle unlimited`…).
3. **Exclusão de parcelamento**: descrição contendo `parc`, `parcela`, `x `,
   `/12`, `/24`, `/6`, `/10`, `installment` é removida.
4. **Frequência**: agrupa por descrição normalizada e exige
   `occurrences ≥ 3` **e** `months_span ≥ 2,5`, onde
   `months_span = (last_date − first_date).days / 30`.
5. **Valor fixo**: `variation = std(amount) / |mean(amount)| < 0,10` — variação
   abaixo de 10%.

Sobrevivendo aos cinco, vira shadow invoice com
`amount = mean(amount)`, `next_due_date = last_date + 30 dias` e
`confidence = 0,9` (constante — a confiança está nos critérios, não em um
score contínuo).

**Extração de parcela** (`_extract_installment_info`), três regex em cascata:

| Padrão | Regex | Resultado |
|---|---|---|
| "3/12" ou "3 / 12" | `(\d+)\s*/\s*(\d+)` | `"3/12"` |
| "10x" ou "10 x" | `(\d+)\s*x\b` | `"10/10"` (assume última parcela) |
| "parcela 3 de 12" | `parc\w*\s*(\d+)\s*de\s*(\d+)` | `"3/12"` |

### Estágio 4 — PF/PJ Context Classifier

Random Forest + regras — detalhado no [doc 05](05-classificador-pf-pj.md).
O runner loga a partição resultante (`PF=x, PJ=y, UNCERTAIN=z`) e aplica os
`context_overrides` do usuário por cima (`apply_user_overrides`).

### Estágio 5 — Shadow Invoice Detection (`core/shadow_invoices.py`)

Motor genérico complementar aos detectores do estágio 3. Regras do
`detect_shadow_invoices`:

1. Só despesas (`amount < 0`), convertidas para `abs_amount`;
2. **Teto de R$ 100** por lançamento (`abs_amount <= 100`) — o alvo aqui são
   assinaturas pequenas e esquecidas, não contas grandes;
3. `normalize_merchant(desc)` agrupa variações do mesmo comerciante:
   - remove `www.`, `.com`, `.br`, `.net`, `.io`;
   - remove **todos os dígitos** (`\d+`) — é o que faz "NETFLX 3/12" e
     "NETFLIX.COM 4/12" convergirem;
   - troca não-letras por espaço;
   - remove as palavras genéricas `compra`, `pagamento`, `debito`, `credito`,
     `recorrente`, `assinatura`;
   - colapsa espaços.
4. Agrupa por merchant normalizado e exige **≥ 3 meses distintos**
   (`month.n_unique() >= 3`, com o mês truncado via `dt.truncate("1mo")`).

Saída por compromisso: `avg_amount`, `months`, `occurrences`.

### Estágio 6 — Data Quality Validator (`etl/data_quality.py`)

Calcula uma **confiança global 0–1 como média ponderada de 4 fatores**:

```
confidence = 0,30 × cobertura_temporal
           + 0,25 × completude
           + 0,25 × consistência_de_saldo
           + 0,20 × ausência_de_anomalias
```

Cada fator:

- **Cobertura temporal (30%)** — `dias_com_dados / dias_analisados`, onde
  `dias_analisados = min(period_days, (max_date − min_date).days + 1)`.
  Registra como "lacuna" todo intervalo de **≥ 2 dias** sem transação entre
  duas datas consecutivas.
- **Completude (25%)** — média do `% de não-nulos` dos 4 campos obrigatórios:
  `transaction_id`, `amount`, `transaction_date`, `description`.
- **Consistência de saldo (25%)** — verifica se
  `balance[i] ≈ balance[i−1] + amount[i]` com **tolerância de R$ 0,01**;
  o score é a fração de linhas consistentes. Sem coluna `balance` ou com menos
  de 2 linhas, retorna **1.0 (neutro)** — não penaliza o que não dá para medir.
- **Ausência de anomalias (20%)** —
  `anomaly_score = max(0, 1 − (anomalias / total) × 10)`. O multiplicador 10
  significa: uma taxa de 10% de anomalias zera este fator.

O nível de qualidade sai por faixa: **EXCELLENT ≥ 0,90 · GOOD ≥ 0,70 ·
FAIR ≥ 0,50 · POOR < 0,50**.

### Estágio 7 — User Profile Analyzer

Monta o perfil de renda (`IncomeProfiler`) e o comportamental — ver
[doc 13](13-inteligencia-comportamental.md). O runner loga `profile_type` e
`score`.

### Estágio 8 — Save to Database

Persistência em `transactions_clean` (PostgreSQL, índice `user_id, date`), com
espelho DuckDB para dev/histórico analítico. `ON CONFLICT(dedup_hash) DO
NOTHING`.

---

## O Income Profiler — a base de todos os thresholds

`etl/income_profiler.py` resolve um bug de produto grave: somar créditos como
renda **infla 2–3×** quem tem múltiplos bancos (transferência Nubank → Inter
aparece como "renda" no Inter). Como a renda é o denominador de quase todo
threshold do produto, errar aqui contamina tudo.

**Passo 1 — exclusão por keyword.** Créditos cuja descrição casa com
`estorno|devoluc|reembolso|cashback|rendimento|juros cred|resgate|aplicac|cdb
|lci |lca |fundo |ted envio|pix envio|tarifa|anuidade|taxa admin|saque|
transferencia propria` são removidos.

**Passo 2 — exclusão de round-trips.** Um `join_asof` (backward,
`tolerance = 5 dias`) associa cada crédito ao débito mais recente na janela.
Se `|crédito − débito| / débito ≤ 2%`, é transferência interna e o crédito
sai. Vetorizado; a limitação declarada é comparar só o débito *mais recente*
da janela, não todos.

**Passo 3 — classificação do padrão.**

| Sinal | Como é detectado |
|---|---|
| CLT por keyword | `salario\|folha\|holerite\|remuneracao\|proventos\|vencimento…` |
| CLT por cadência | Pega o **maior crédito de cada mês**; exige `CV < 0,15` nos valores **e** desvio-padrão do dia de pagamento `< 5 dias` |
| PJ por keyword | `nota fiscal\|prestac\|honorario\|autonomo\|mei \|pj ` |
| PJ por diversidade | `≥ 3 payers distintos` (proxy = primeiros 30 chars da descrição) |

`is_clt AND is_pj → MIXED`; só CLT → `CLT`; só PJ → `PJ`; nenhum → `UNKNOWN`.

**Passo 4 — estabilidade e confiança.**

```
income_stability = 1 − CV(totais_mensais)      , limitado a [0,1]
                   (0,3 fixo se < 2 meses de dados)
```

```
confidence base:  UNKNOWN → 0,25
                  detectado só por cadência/payers (sem keyword) → 0,55
                  MIXED → 0,80
                  confirmado por keyword explícita → 0,85

penalidades:      < 2 meses de dados → × 0,5
                  estabilidade < 0,5 → × 0,8
```

Detalhe deliberado: `_detect_salary_cadence` usa `std(ddof=1)` (amostral,
infla o desvio com poucos meses → **conservador**, prefere rejeitar cadência
legítima a confirmar CLT sem dados), enquanto `_income_stability` usa
`ddof=0` (populacional, porque é descritivo e não decisório).

Contrato para quem consome: `confidence ≥ 0,7` usar direto (elegibilidade de
cartão); `0,4–0,7` usar com cautela; `< 0,4` preferir renda declarada.

---

## Spending Anomaly Detector (`etl/spending_anomaly_detector.py`)

Quatro detectores independentes, todos sobre despesas (sinal invertido para
positivo). Diferente do Data Quality (integridade estrutural), aqui a
pergunta é comportamental: "isso é incomum **para este usuário**".

| Tipo | Regra exata | Severidade |
|---|---|---|
| `UNUSUAL_AMOUNT` | `amount > média_categoria + 2σ`, só em categorias com **≥ 5** transações históricas; ignora `Transferência`, `Investimento`, `Outros` | WARNING |
| `NEW_MERCHANT` | `merchant_id` (ou descrição normalizada) inédito no histórico **e** `amount ≥ R$ 200` | INFO |
| `FREQUENCY_SPIKE` | transações do dia na categoria `≥ 3×` a média diária histórica | WARNING |
| `DUPLICATE_SUSPECT` | mesmo merchant **e** `|Δvalor| < R$ 0,01` dentro de **2 dias calendário** | ALERT |

**Calibração por renda** (quando `IncomeProfile.confidence ≥ 0,5`):
- `UNUSUAL_AMOUNT`: gasto `≥ 15% da renda mensal` ganha o sufixo explicativo
  "(X% da renda mensal)" — um gasto pode ser estatisticamente normal na
  categoria e ainda assim ser grande demais para a renda;
- `NEW_MERCHANT`: o piso vira `max(R$ 100, 2% da renda mensal)` em vez do
  fixo R$ 200 — R$ 200 é irrelevante para quem ganha R$ 15k e enorme para
  quem ganha R$ 2k.

O uso de `merchant_id` (quando disponível) em vez da descrição crua é o que
faz "PG*NETFLIX" e "NETFLIX.COM" serem reconhecidos como o mesmo comerciante
— tanto para não alertar falso "merchant novo" quanto para *pegar* a
duplicata real.

Saída ordenada por severidade (ALERT → WARNING → INFO), exposta em
`GET /alerts/{user_id}`.

---

## As proteções contra dados ruins — resumo

| Proteção | Onde | O que protege |
|---|---|---|
| **Dedup** | `etl/dedup/` + `UNIQUE` no banco | SHA-256 de `account_id\|data\|valor\|desc[:20]`; reconexão ou webhook repetido não vira gasto dobrado |
| **Data Quality Validator** | `etl/data_quality.py` | Score ponderado 30/25/25/20; marca POOR abaixo de 0,50 antes de contaminar projeções |
| **Shadow Invoices** | `core/shadow_invoices.py` + estágio 5 | O extrato só mostra o passado; parcelas e assinaturas comprometem o caixa FUTURO |
| **Detector de assinaturas v2** | `subscriptions/shadow_invoices/` | 5 critérios TODOS obrigatórios — evita marcar aluguel ou conta de luz como "assinatura" |
| **Spending Anomaly Detector** | `etl/spending_anomaly_detector.py` | 4 regras estatísticas com baseline pessoal, calibradas por renda |
| **Income Profiler** | `etl/income_profiler.py` | Renda real ≠ soma de créditos: keywords + round-trip por `join_asof` |
| **Mixed-use Detector** | `etl/mixed_use_detector.py` | Estabelecimentos usados tanto para PF quanto PJ (mercado que é estoque do MEI) |
| **Webhook assinado** | `core/webhook_security.py` | Segredo comparado em tempo constante; produção sem segredo → 503 fail-closed; identidade resolvida server-side pelo `item_id`, nunca confiada no payload |

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
- **Classificador de categorias é 100% regex** — os modos `ML`/`HYBRID` do
  `TransactionClassifier` são stubs; o modelo treinado em produção é o PF/PJ.
  Consequência prática: descrição sem keyword conhecida cai em
  `("Outros", 0.50)`, e categoria nova exige editar `CATEGORY_KEYWORDS`.
- **Primeiro match vence** na classificação: não há desempate entre categorias
  que casariam ambas. A ordem do dicionário é, de fato, a regra de prioridade.
- **Shadow invoice genérico tem teto de R$ 100** — compromissos recorrentes
  maiores dependem do `SubscriptionDetector`/`InstallmentDetector`.
- **Round-trip cross-bank não é detectável** com dados de um único banco; a
  exclusão por keyword (`ted envio`, `pix envio`) mitiga parcialmente.
- **`DUPLICATE_SUSPECT` compara datas, não timestamps** — a janela de "48h" é
  aproximada como 2 dias calendário (limite do schema).
- **Webhook não tem fila** — processamento síncrono; volume alto de webhooks
  simultâneos seria melhor servido por fila (Redis/worker) no futuro.
