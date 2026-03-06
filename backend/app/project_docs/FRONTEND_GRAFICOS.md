# Nexa — Especificação de Componentes Visuais (Frontend)

> Documento de referência para o time de frontend.
> Cada componente está mapeado ao endpoint de backend que o alimenta.
> Cores seguem o sistema de design Nexa (paleta azul escalonada).

---

## Paleta de Cores

| Nome | Hex | Uso |
|---|---|---|
| Azul Claro | `#6BAEFA` | Abaixo do limite / bem dentro do orçamento |
| Azul Médio | `#0978F6` | Próximo do limite / entre R$10–R$50 |
| Azul Escuro | `#0762C7` | Acima do limite / acima de R$50 |
| Verde Positivo | `#27AE60` | Saldo positivo / dentro do esperado |
| Vermelho Negativo | `#E74C3C` | Saldo negativo / estouro |
| Cinza Base | `#F4F6F9` | Fundo de cards e barras vazias |
| Texto Principal | `#1A1A2E` | Títulos e valores |
| Texto Secundário | `#6B7280` | Labels e descrições |

---

## 1. Safe-to-Spend — Medidor de Orçamento

### Descrição
Gauge circular (ou barra de progresso) mostrando o quanto do orçamento mensal seguro já foi consumido. Inclui quanto resta gastar por dia para manter o plano.

### Layout
```
  [Gauge circular / barra]
  De R$ 3.000,00 você já gastou R$ 2.401,25
  Você está em 80% do seu orçamento mensal
  Para manter o plano, você pode gastar até R$ 36,00/dia
```

### Lógica de Cores
| % Consumido | Cor da barra | Significado |
|---|---|---|
| 0 – 60% | `#6BAEFA` | Confortável |
| 61 – 85% | `#0978F6` | Atenção |
| 86 – 100% | `#0762C7` | Crítico |
| > 100% | `#E74C3C` | Estourou |

### Cálculo do gasto diário restante
```
dias_restantes = dias_no_mes - dia_atual
valor_restante = safe_to_spend_total - total_gasto
gasto_diario_maximo = valor_restante / dias_restantes
```

### Endpoint
```
GET /api/v1/safe-to-spend/{user_id}

Campos retornados:
  safe_to_spend_total   → orçamento mensal total (denominador do gauge)
  spent_to_date         → total gasto no mês corrente (numerador do gauge)
  pct_consumed          → percentual consumido já calculado (0–100+)
  safe_to_spend_daily   → limite diário calculado pelo backend
  current_balance       → saldo atual da conta
  risk_level            → "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
  month                 → mês de referência "YYYY-MM"
```

---

## 2. Aba de Categorias — Breakdown por Gasto

### Descrição
Lista de categorias com barra de progresso horizontal, percentual consumido do orçamento da categoria e valor absoluto gasto.

### Layout por item
```
[Ícone] Cuidados Pessoais
        ████████████████████░░  89%   R$ 4.273,62
```

### Lógica de Cores da barra
| % da categoria | Cor |
|---|---|
| 0 – 70% | `#6BAEFA` |
| 71 – 90% | `#0978F6` |
| > 90% | `#0762C7` |

### Ordenação
Exibir ordenado do maior percentual para o menor (categorias mais estouradas no topo).

### Endpoint
```
GET /api/v1/budget/{user_id}?monthly_income=8000

⚠️  PARÂMETRO OBRIGATÓRIO: monthly_income (renda mensal do usuário em R$).
    Sem ele o endpoint retorna 422. O frontend deve obter esse valor no onboarding.

Campos reais retornados (dentro de allocations[]):
  category           → nome da categoria  (doc dizia: category_name)
  current_amount     → valor gasto no mês (doc dizia: spent)
  suggested_amount   → orçamento sugerido 50/30/20 (doc dizia: budget)
  current_pct        → % da renda gasta na categoria (doc dizia: pct_used)
                       ⚠ É percentual da RENDA, não do orçamento da categoria.
                         Para pct_used real: current_amount / suggested_amount * 100
  group              → "essenciais" | "desejos" | "poupanca"
  status             → "WITHIN" | "OVER" | "UNDER"
  suggested_pct      → % alvo da regra 50/30/20

Outros campos úteis no response:
  group_summary[]    → resumo por grupo (essenciais / desejos / poupança)
  actionable_cuts[]  → cortes concretos ordenados por potencial de economia
  summary_text       → texto explicativo em português
```

> Os valores são baseados na regra 50/30/20 adaptada ao histórico real (BudgetAdvisor).
> Ordenar por `current_amount / suggested_amount` decrescente para as mais estouradas no topo.

---

## 3. Visão dos Gastos Diários — Gráfico de Colunas

### Descrição
Gráfico de barras verticais com um ponto por transação ou agregado por hora/período do dia. O eixo X é o horário ou dia, o eixo Y é o valor. A cor de cada barra varia pelo valor da transação.

### Sistema de Cores por Valor
| Valor da transação | Cor | Hex |
|---|---|---|
| Abaixo de R$ 10,00 | Azul Claro | `#6BAEFA` |
| Entre R$ 10,00 e R$ 50,00 | Azul Médio | `#0978F6` |
| Acima de R$ 50,00 | Azul Escuro | `#0762C7` |

### Dois modos de visualização
- **Por hora do dia** (padrão): agrupa transações em slots de 1h (00h–23h), soma os valores por slot.
- **Por dia do mês**: uma barra por dia com o total gasto naquele dia.

### Interatividade
- Tap/hover em uma barra: exibe tooltip com lista das transações do período, hora, valor e estabelecimento.
- Filtro de período: hoje / 7 dias / 30 dias / mês atual.

### Endpoint
```
GET /api/v1/transactions/{user_id}?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD

Query params opcionais:
  start_date       → YYYY-MM-DD
  end_date         → YYYY-MM-DD
  category         → ex: "alimentacao", "transporte"
  transaction_type → "debit" ou "credit"
  limit            → 1–1000 (padrão: 200)

Campos retornados por transação (dentro de transactions[]):
  transaction_id   → ID único da transação
  description      → estabelecimento / descrição
  amount           → valor (negativo = débito, positivo = crédito)
  date             → data no formato "YYYY-MM-DD"
  category         → categoria classificada pelo ETL
  transaction_type → "debit" | "credit"
  is_recurring     → booleano
  is_installment   → booleano

Campos de resumo na raiz:
  total            → total de transações retornadas
  debit_count      → quantidade de débitos (use para "passadas de cartão")
  credit_count     → quantidade de créditos

⚠ Campo "time" (hora) AUSENTE: o schema atual armazena "date" como DATE,
  sem hora. O agrupamento por slot de 1h no gráfico de colunas não está
  disponível. Workaround: usar modo "por dia do mês" como padrão inicial.
```

---

## 4. Relatório Mensal

### 4a. Resumo Financeiro do Mês

#### Descrição
Card com receitas, despesas e saldo resultante. O saldo é exibido em verde (positivo) ou vermelho (negativo).

#### Layout
```
  Maio 2026
  ┌─────────────────────────────┐
  │ Recebeu       R$ 8.500,00  │
  │ Gastou        R$ 6.742,15  │
  │ ─────────────────────────  │
  │ Saldo  +R$ 1.757,85        │  ← Verde
  └─────────────────────────────┘
```
Se negativo:
```
  │ Saldo  -R$ 342,15          │  ← Vermelho
```

#### Endpoint
```
GET /api/v1/dashboard/{user_id}?month=MM&year=YYYY

❌ BACKEND NÃO IMPLEMENTADO para este formato.
   Rota atual: GET /api/v1/dashboard/summary (sem user_id, sem filtro por mês,
   valores hardcoded: income=7200, expenses=5300).

   Campos retornados HOJE (mock):
     income        → (doc dizia: total_income)
     expenses      → (doc dizia: total_expenses)
     savings_rate  → taxa de poupança em %
     health_score  → score de saúde financeira (0-100)
     ⚠ net_balance não é retornado diretamente (calcular: income - expenses)

   Para dados reais enquanto o dashboard não for refatorado, usar:
     financial_health.total_income e financial_health.total_expenses
     via GET /api/v1/forecast/{user_id}
```

---

### 4b. Assinaturas Ativas

#### Descrição
Lista compacta de assinaturas recorrentes detectadas automaticamente. Exibe nome, valor e periodicidade.

#### Layout por item
```
  [Logo] Netflix              R$ 55,90 / mês
  [Logo] Spotify              R$ 21,90 / mês
  [Logo] iCloud+              R$ 17,90 / mês
  ───────────────────────────────────────────
  Total em assinaturas:      R$ 95,70 / mês
```

#### Endpoint
```
GET /api/v1/subscriptions/{user_id}

Endpoint funcional. Campos reais retornados (dentro de subscriptions[]):
  merchant              → nome do serviço  (doc dizia: name)
  monthly_amount        → valor cobrado    (doc dizia: amount)
  last_seen             → data da última cobrança  (doc dizia: last_charge)
  subscription_category → categoria: "streaming_video" | "fitness" | etc.
  first_seen            → data da primeira detecção
  occurrences           → quantidade de cobranças detectadas

⚠ CAMPOS AUSENTES:
  frequency  → não retornado. O detector identifica apenas recorrência mensal.
               Usar "mensal" como valor fixo por enquanto.
  logo_url   → não implementado. Usar subscription_category para selecionar
               um ícone/logo local no frontend.

Campos do report raiz:
  total_subscriptions   → total de assinaturas detectadas
  total_monthly_cost    → soma das mensalidades (R$)
  summary_text          → texto explicativo em português
  alerted[]             → assinaturas com alertas (DUPLICATE_CATEGORY, LOW_VALUE, PRICE_INCREASE)
```

---

### 4c. Passadas de Cartão no Mês (Informativo)

#### Descrição
Número simples, exibido em destaque. Sem julgamento de valor — apenas informativo para o usuário ter consciência do volume de transações.

#### Layout
```
  Você passou o cartão
  ┌──────┐
  │  47  │  vezes este mês
  └──────┘
```

#### Endpoint
```
GET /api/v1/transactions/{user_id}?start_date=YYYY-MM-01&end_date=YYYY-MM-31

O campo debit_count já vem calculado no response — não é necessário filtrar no frontend:
  debit_count → número de débitos no período (use diretamente como contagem)

Alternativa (se quiser o número bruto sem filtro de data no backend):
  count = transactions.filter(amount < 0).length
```

---

### 4d. Agenda Financeira — Próximos Compromissos

#### Descrição
Lista de eventos financeiros futuros ordenada por proximidade de data. Quanto mais próximo, mais no topo. Inclui vencimentos, cobranças recorrentes previstas e metas com prazo.

#### Layout por item
```
  [Urgente] Amanhã
  Fatura Nubank vence          R$ 1.240,00

  [Em 5 dias]
  Aluguel                      R$ 1.800,00

  [Em 12 dias]
  Parcela financiamento carro  R$   893,00

  [Em 18 dias]
  Spotify                      R$    21,90
```

#### Indicadores visuais por urgência
| Prazo | Cor da tag | Ícone |
|---|---|---|
| Hoje / Amanhã | `#E74C3C` vermelho | Alerta |
| 2–5 dias | `#F39C12` laranja | Atenção |
| 6–14 dias | `#0978F6` azul | Normal |
| 15+ dias | `#6B7280` cinza | Informativo |

#### Ordenação
Sempre ascendente por `due_date` — o mais urgente no topo.

#### Endpoint
```
GET /api/v1/forecast/{user_id}

Campos reais (dentro de shadow_invoices.invoices[]):
  description    → nome do compromisso
  amount         → valor (negativo para débito)
  next_due_date  → data do vencimento  (doc dizia: due_date)
  type           → "SUBSCRIPTION" | "INSTALLMENT"
                   (doc dizia: boleto / recorrencia / meta / parcela — tipos mais amplos)
  confidence     → confiança da detecção (0.0–1.0)

⚠ Tipos ausentes: "boleto" e "meta" não são detectados pelo pipeline atual.
  O backend só detecta SUBSCRIPTION (assinaturas) e INSTALLMENT (parcelamentos).
  Ordenar por next_due_date ascendente no frontend.
```

---

### 4e. Ritmo de Gastos vs. Orçamento do Mês — Barra de Progresso

#### Descrição
Barra horizontal que mostra o ritmo de gastos comparado com o esperado para o período do mês (proporcional aos dias decorridos).

#### Lógica
```
dias_decorridos  = dia_atual / dias_no_mes
gasto_esperado   = orçamento_total * dias_decorridos
gasto_real       = total_gasto_ate_hoje

ritmo = gasto_real / gasto_esperado  (1.0 = exatamente no ritmo)
```

#### Sistema de Cores
| Ritmo | Cor | Hex | Significado |
|---|---|---|---|
| < 0.80 | Azul Claro | `#6BAEFA` | Bem abaixo — ótimo ritmo |
| 0.80 – 1.05 | Azul Médio | `#0978F6` | Pouco abaixo ou no limite |
| > 1.05 | Azul Escuro | `#0762C7` | Acima do ritmo esperado |
| > 1.20 | Vermelho | `#E74C3C` | Ritmo crítico |

#### Layout
```
  Ritmo de Gastos — Maio 2026
  Dia 18 de 31 (58% do mês)

  Esperado até hoje: R$ 4.930,00
  Gasto até hoje:    R$ 6.742,15   ← acima

  [████████████████████████░░░░░░]  137%
                             ^ Azul escuro
```

#### Texto auxiliar
- Abaixo: *"Parabéns! Você está gastando menos que o esperado para este ponto do mês."*
- No limite: *"Você está no ritmo. Continue assim para fechar o mês equilibrado."*
- Acima: *"Atenção: seu ritmo de gastos está X% acima do esperado. Reduza para equilibrar o mês."*

#### Endpoint
```
GET /api/v1/safe-to-spend/{user_id}

Mesma rota do componente 1. Campos usados aqui:
  safe_to_spend_total   → orçamento mensal total (gasto_esperado usa esse valor)
  spent_to_date         → total gasto até hoje (gasto_real)
  pct_consumed          → ritmo já calculado se dia for exatamente meio do mês
  (dia_atual e dias_no_mes calculados no frontend via Date())
```

---

## Mapa de Endpoints por Componente

| Componente | Método | Endpoint | Status |
|---|---|---|---|
| Safe-to-Spend gauge | GET | `/api/v1/safe-to-spend/{user_id}` | ✅ Funciona |
| Categorias / breakdown | GET | `/api/v1/budget/{user_id}?monthly_income=X` | ⚠ Funciona; campos com nomes diferentes |
| Gastos diários (colunas) | GET | `/api/v1/transactions/{user_id}` | ⚠ Funciona; sem campo "time" (hora) — usar modo por dia |
| Resumo do mês | GET | `/api/v1/forecast/{user_id}` → `financial_health` | ⚠ Dashboard mock; usar financial_health do forecast |
| Assinaturas ativas | GET | `/api/v1/subscriptions/{user_id}` | ⚠ Funciona; campos com nomes diferentes |
| Passadas de cartão | GET | `/api/v1/transactions/{user_id}` | ✅ Usa campo `debit_count` do response |
| Agenda financeira | GET | `/api/v1/forecast/{user_id}` → `shadow_invoices.invoices` | ✅ Funciona |
| Ritmo de gastos | GET | `/api/v1/safe-to-spend/{user_id}` | ✅ Funciona |

---

## Status de Implementação do Backend

### Pronto para uso
- `GET /api/v1/subscriptions/{user_id}` — detecta assinaturas recorrentes (nomes de campos divergem — ver seção 4b)
- `GET /api/v1/budget/{user_id}?monthly_income=X` — orçamento 50/30/20 por categoria (nomes divergem — ver seção 2)
- `GET /api/v1/forecast/{user_id}` — safe-to-spend + agenda financeira + saúde financeira

### Incompleto / workaround necessário
- ~~**Safe-to-spend gauge e ritmo de gastos**~~: implementado em `GET /api/v1/safe-to-spend/{user_id}` com `spent_to_date` e `pct_consumed`.
- **Resumo mensal**: usar `/forecast/{user_id}` → `financial_health` (`total_income`, `total_expenses`). Filtro por mês não suportado (retorna sempre os últimos 90 dias).

### Não implementado (❌ blocker)
- ~~`GET /api/v1/transactions/{user_id}`~~: implementado com filtros de data, categoria e tipo. Retorna `debit_count` para passadas de cartão. Limitação: sem campo `time` (hora) — gráfico de colunas por hora indisponível, usar modo por dia.
- `GET /api/v1/dashboard/{user_id}?month=&year=` — rota não tem `user_id` nem filtro por mês.

---

## Notas de Implementação

- **Todos os valores monetários** devem ser formatados como `R$ X.XXX,XX` (locale pt-BR).
- **Valores negativos** exibidos com sinal explícito: `-R$ 342,15` em vermelho.
- **Valores positivos** em contexto de saldo: `+R$ 1.757,85` em verde.
- **Loading state**: usar skeleton screens (não spinner) em todos os componentes.
- **Empty state**: quando não há dados suficientes, exibir mensagem amigável + CTA para conectar banco (Pluggy).
- **Refresh**: dados atualizados em pull-to-refresh ou polling de 5 minutos.

---

*Última atualização: 2026-03-06 — verificação de aderência backend incluída*
*Versão do backend de referência: codigos-nexa-11*
