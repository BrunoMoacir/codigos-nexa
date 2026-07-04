# OPP.1 — Detecção de Dinheiro Parado em Conta Corrente — Plano de Desenvolvimento

> **Escopo:** este documento cobre exclusivamente a sub-feature OPP.1 (detecção de dinheiro
> ocioso). Não repete o que já está descrito em `docs/OPP.md` sobre catálogo de produtos, motor
> de IR, scorecard por banco ou Tesouro Direto — para isso, ver `docs/OPP.md` seções 5, 7 e 8.
> **Fontes:** `docs/OPP.md` (seções 2, 6, 12, 14) e `docs/ROADMAP.md` (seção "OPP — Radar de
> Oportunidades", linhas 100–118). Auditado contra o código real em 2026-07-04.
> **Status geral do módulo:** MVP backend implementado (`backend/app/opportunities/`) — este plano
> trata apenas da evolução da lógica de detecção, não é um módulo greenfield nem uma reescrita do
> Radar de Oportunidades.
> **Superfícies de produto do roadmap:** OPP.1 deve alimentar somente (1) Feed/Notificações de
> oportunidades e (2) Agente IA com tools financeiras. Não criar tela standalone nem experiência
> paralela fora desses dois canais.

---

## 1. Especificação alvo vs. implementação real

`docs/ROADMAP.md` define a lógica de detecção assim:

> - Compara saldo médio dos últimos 3 meses com média de gastos mensais
> - Ocioso = saldo − (N meses de gastos) − reserva de emergência
> - Threshold mínimo: R$500 por 30+ dias
> - Ranking por retorno líquido real após IR (não por taxa bruta)

| Requisito do ROADMAP | Estado real | Onde |
|---|---|---|
| Saldo médio de conta (stock) | **Não implementado.** Usa `avg_income_3m − avg_expenses_3m` (fluxo), não saldo em conta | `idle_money_detector.py:38-97` |
| Subtrair N meses de gastos | **Não implementado** — não há esse termo na fórmula atual | idem |
| Subtrair reserva de emergência | **Não implementado** — `idle_amount` não distingue reserva de sobra | idem |
| Threshold R$500 por 30+ dias | **Não implementado** — cada chamada recalcula do zero, sem checar persistência no tempo | idem |
| Ranking líquido pós-IR | ✅ **Implementado corretamente**, fora do escopo deste doc | `bank_comparator.py` + `IRPFCalculator` |

O ranking pós-IR (o motor mais complexo do módulo) já está correto. O problema é inteiramente na
etapa anterior — **como decidir quanto está ocioso** — que é o que este documento planeja resolver.

---

## 2. Por que a fórmula atual é um proxy, e não o que o ROADMAP pede

`idle_amount = avg_income_3m − avg_expenses_3m` mede **sobra de fluxo mensal** (quanto entra a mais
do que sai, em média) — um indicador válido de capacidade de poupança, mas diferente de **saldo
parado** (quanto dinheiro já está fisicamente parado na conta agora, sem remuneração).

Isso não foi uma escolha de design: é uma limitação de dados. Investigação no código confirma que
**não existe hoje, em nenhum lugar do backend, saldo real de conta persistido e consultável**:

- `PluggyClient.get_accounts(item_id)` (`backend/app/core/integrations/pluggy.py:117`) já retorna
  `balance` por conta na resposta da API — mas todo chamador (`app/runner.py`,
  `app/architect/router.py`, `app/api/v1/routes/pluggy.py`) descarta esse campo e só extrai o
  `account_id` para buscar transações. Não existe tabela `accounts` nem coluna `balance` em
  `app/core/db/models.py`.
- `app.core.db.queries.get_transactions_for_user()` — a função que `IdleMoneyDetector` consome —
  seleciona só campos de fluxo (`amount`, `date`, `category`, ...); não expõe saldo.
- `app/forecast/` também precisa de um "saldo" para projetar cashflow, mas resolve isso com um
  proxy próprio e frágil: `current_balance = sum(transactions_df["amount"])` (soma cumulativa de
  *todas* as transações históricas — `forecast/router.py:109`) ou, quando o conector do banco
  fornece (ex.: Inter, `etl/bank_strategy/strategies/inter.py`), um campo `balance` por transação
  que não é garantido em todos os bancos/mocks.

Ou seja: mesmo se quiséssemos copiar a solução do `forecast/`, ela não é confiável o suficiente
para basear uma recomendação financeira — ver decisão na seção 4.

---

## 3. Peça que já existe e pode ser reaproveitada: reserva de emergência

O projeto já tem um perfil comportamental maduro que calcula `fss_level` (Financial Stress Score:
`"SAUDAVEL" | "ATENCAO" | "ALERTA" | "CRITICO"`) a partir de 90 dias de transações:

```python
# app/optimizer/profiler.py
class ConsumptionProfiler:
    def build(self, transactions_df: pl.DataFrame, ...) -> UserProfile: ...
        # UserProfile.fss_level já vem calculado
```

`ConsumptionProfiler().build()` recebe o **mesmo `transactions_df`** que `IdleMoneyDetector` já
carrega via `get_transactions_for_user()` — não exige nova query nem chamada de rede, só passar o
DataFrame adiante.

**Atenção — não reaproveitar literalmente `_EMERGENCY_MONTHS_BY_FSS` de
`app/goals/profile_advisor.py:28-33`.** Essa tabela (`CRITICO: 3, ALERTA: 3, ATENCAO: 6,
SAUDAVEL: 6`) responde a uma pergunta diferente: "quantos meses de reserva é uma **meta realista**
para este usuário construir" (por isso é *menor* para quem está em crise — meta de curto prazo
alcançável). O OPP precisa do oposto: "quantos meses eu devo **proteger e nunca sugerir investir**",
que deveria ser *maior* justamente para quem está mais frágil financeiramente (margem de segurança,
não meta). Usar a mesma tabela para os dois propósitos inverteria a lógica de proteção. `docs/OPP.md`
seção 6.2 já esboça uma tabela própria para este uso (6 meses padrão, 9 meses quando
`fss_level in {"ALERTA", "CRITICO"}`) — este plano adota essa proposta como ponto de partida, a
validar com produto (ver Riscos, seção 8).

---

## 4. Decisão de arquitetura: evoluir o proxy ou construir saldo real primeiro?

Duas opções, não mutuamente exclusivas:

**Opção A — Evoluir o proxy atual (sem nova infraestrutura).**
Mantém `avg_income_3m − avg_expenses_3m` como base, mas adiciona reserva de emergência e o
threshold de 30 dias sobre esse número. Não é literalmente "saldo em conta" como o ROADMAP pede,
mas é uma melhoria real, sem custo de infra nova, entregável em ~2 semanas.

**Opção B — Persistir saldo real via Pluggy (nova infraestrutura).**
Criar tabela `accounts` (`user_id`, `account_id`, `bank_name`, `balance`, `account_type`,
`synced_at`), popular a cada sync do Pluggy (`get_accounts()` já retorna o dado, só não é
persistido hoje), e recalcular `idle = saldo_atual − N meses de gastos − reserva`. Isso é a
arquitetura correta segundo o ROADMAP e também resolveria a fragilidade do proxy do `forecast/` —
mas é um projeto de infraestrutura compartilhada entre módulos, não algo exclusivo do OPP.

**Recomendação:** fazer a Opção A primeiro (tickets OPP1-A a OPP1-D abaixo). A Opção B vira uma
iniciativa de infraestrutura à parte (seção 7), fora deste plano — beneficia `opportunities/` e `forecast/` ao
mesmo tempo e merece seu próprio desenho técnico e critérios de aceite.

---

## 5. Contrato de entrega da Opção A

Esta seção transforma a recomendação em contrato de implementação. O objetivo é impedir que a
feature termine como "melhorou a fórmula" sem ficar observável para API, chat, testes e futuro feed.

### 5.0 Canais de consumo no produto

OPP.1 é uma capacidade de backend, não uma nova página de produto. A entrega deve aparecer em dois
canais:

| Canal | Como OPP.1 aparece | Arquivos/módulos |
|---|---|---|
| Feed/Notificações | Card priorizado quando houver oportunidade `CONFIRMED`; aviso preliminar quando `PRELIMINARY` e valor relevante | `opportunities/`, `notifications/`, futuro Feed |
| Agente IA | Tool responde perguntas sobre dinheiro parado, investimento de reserva e custo de oportunidade | `app/agent/tools/get_opportunities.py` |

**Fora de escopo:** página dedicada de OPP, dashboard novo, fluxo de onboarding separado ou UI de
investimentos fora do Feed/Notificações e do Agente IA.

### 5.1 Campos novos de domínio

`IdleMoneyResult` passa a representar três números diferentes, com nomes explícitos:

```python
@dataclass
class IdleMoneyResult:
    # Valor bruto do proxy atual: avg_income_3m - avg_expenses_3m
    gross_idle_amount: float

    # Reserva protegida que NÃO deve virar oportunidade de investimento
    emergency_reserve: float
    reserve_months_applied: int

    # Valor final usado pelo ranking de produtos
    idle_amount: float

    avg_income_3m: float
    avg_expenses_3m: float
    months_analyzed: int
    has_sufficient_data: bool
    is_confirmed_idle: bool
    days_tracked: int
```

**Compatibilidade:** `idle_amount` continua existindo e passa a significar o valor final, já
protegido por reserva e threshold. O valor bruto fica em `gross_idle_amount` para auditoria.

### 5.2 Contrato de API

`GET /api/v1/opportunities/{user_id}` é contrato interno de backend para Feed/Notificações e Agente
IA. Ele mantém os campos atuais e adiciona:

```json
{
  "gross_idle_amount": 2400.0,
  "emergency_reserve": 18000.0,
  "reserve_months_applied": 6,
  "idle_amount": 0.0,
  "is_confirmed_idle": false,
  "days_tracked": 12,
  "idle_detection_status": "PRELIMINARY",
  "idle_detection_reason": "Reserva de emergencia protegida; historico de snapshots menor que 30 dias"
}
```

Valores permitidos para `idle_detection_status`:

| Status | Quando usar | Produto |
|---|---|---|
| `NO_DATA` | Sem transações suficientes | Não recomendar investimento |
| `PRELIMINARY` | Tem estimativa, mas < 30 dias de snapshots | Mostrar com aviso |
| `CONFIRMED` | `idle_amount >= 500` em >= 90% dos snapshots dos últimos 30 dias | Mostrar como oportunidade priorizada |
| `NO_IDLE_MONEY` | Valor final zerado após despesas/reserva | Mostrar educação financeira, não produto |

### 5.3 Contrato do chat

A tool `get_opportunities` deve consumir o mesmo resultado da API/engine. O texto precisa deixar
claro o nível de confiança:

- `CONFIRMED`: "Identifiquei R$ X ociosos de forma recorrente nos últimos 30 dias..."
- `PRELIMINARY`: "Ainda é uma estimativa inicial; preciso de 30 dias de histórico para confirmar..."
- `NO_IDLE_MONEY`: "Não identifiquei dinheiro ocioso depois de proteger sua reserva..."
- `NO_DATA`: "Conecte sua conta por pelo menos 2 meses..."

**Proibição:** a tool do chat não pode manter uma segunda fórmula de `idle_amount`.

### 5.3.1 Contrato do Feed/Notificações

O Feed/Notificações deve consumir o mesmo `OpportunitiesResponse` e aplicar as regras:

- `CONFIRMED` + `idle_amount >= 500`: gerar card/notification priorizável por impacto financeiro.
- `PRELIMINARY`: gerar no máximo card discreto ou resposta no agente; evitar push/email agressivo.
- `NO_IDLE_MONEY`: não gerar card de oportunidade; pode virar educação financeira de baixa prioridade.
- `NO_DATA`: não gerar oportunidade; sugerir conexão/manutenção do Open Finance apenas quando fizer
  sentido no fluxo do usuário.

O card deve mostrar no mínimo: valor ocioso final, valor protegido como reserva, perda mensal
estimada e nível de confiança. O detalhe expandido deve explicar a fórmula e por que parte do valor
foi protegida.

### 5.4 Regras de liquidez

Enquanto a feature estiver na Opção A (proxy de fluxo, não saldo real), a recomendação deve ser
conservadora:

- Valor classificado como reserva protegida não entra no ranking.
- Para usuário `fss_level in {"ALERTA", "CRITICO"}`, qualquer recomendação com
  `liquidity_days > 1` deve vir abaixo de produtos com liquidez diária, mesmo se o retorno líquido
  for maior.
- Se `idle_detection_status != "CONFIRMED"`, o texto deve preferir "simular" ou "avaliar" em vez de
  "migrar agora".

### 5.5 Fixtures mínimas de teste

Criar fixtures pequenas e explícitas, sem depender de seed global:

| Fixture | Entradas | Resultado esperado |
|---|---|---|
| `stable_surplus_healthy` | 3 meses, renda 10k, gasto 6k, `SAUDAVEL` | reserva 36k, idle final 0 |
| `large_surplus_confirmed` | snapshots 30/30 dias acima de 500 | `CONFIRMED`, `days_tracked=30` |
| `surplus_not_persistent` | snapshots oscilando, só 20/30 acima de 500 | `PRELIMINARY` ou `NO_IDLE_MONEY`, nunca `CONFIRMED` |
| `critical_fss_protected` | renda 12k, gasto 7k, `CRITICO` | reserva 63k, produto de baixa liquidez não priorizado |
| `cold_start` | 12 dias de snapshots | `PRELIMINARY`, recomendação visível com aviso |
| `no_transactions` | DataFrame vazio | `NO_DATA` |

### 5.6 Definition of Done

OPP.1 Opção A só deve ser marcada como concluída quando:

- `idle_amount` for calculado em uma única implementação compartilhada por API e chat.
- `OpportunitiesResponse` expuser valor bruto, reserva, valor final, status e dias rastreados.
- Feed/Notificações e Agente IA consumirem o mesmo contrato, sem criar nova superfície de produto.
- A reserva de emergência for subtraída com base em `fss_level`.
- O threshold de R$500/30 dias for testado contra `opportunity_snapshots`.
- O chat não tiver helper próprio `_calc_idle_amount`.
- Existirem testes em `backend/tests/opportunities/`.
- A recomendação textual nunca sugerir investir a reserva protegida.

---

## 6. Plano de Desenvolvimento (Opção A)

### Ticket OPP1-A — Unificar a lógica de ocioso (pré-requisito)

**Problema confirmado:** `app/agent/tools/get_opportunities.py:90-116` (`_calc_idle_amount`) é uma
cópia quase idêntica de `IdleMoneyDetector._calculate` (`idle_money_detector.py:64-106`) — mesmo
corte de 3 meses, mesma soma de renda/despesa. São dois lugares calculando a mesma coisa de forma
independente; qualquer mudança de fórmula (Tickets OPP1-B e OPP1-C) feita só em um dos dois diverge
silenciosamente do outro.

- **Ação:** `get_opportunities.py` (tool do chat) passa a chamar `IdleMoneyDetector.detect()` (ou
  `OpportunityEngine.analyze()`) em vez de ter sua própria função `_calc_idle_amount`.
- **Critério de aceite:** existe uma única implementação de `idle_amount` no repositório; chat e
  API retornam o mesmo valor para o mesmo usuário no mesmo instante.
- **Teste:** paridade — dado o mesmo `transactions_df` sintético, tool do chat e
  `IdleMoneyDetector` retornam o mesmo `idle_amount`.
  ✅ **Feito** (`backend/tests/opportunities/test_chat_api_parity.py`): compara o valor embutido no
  texto do chat com o retorno do `OpportunityEngine`, sem `_calc_idle_amount` duplicado. **Escopo
  reconhecidamente parcial:** cobre paridade de valor chat↔engine, não faz chamada HTTP real ao
  endpoint (`GET /opportunities/{user_id}`). Um teste de integração HTTP fica para quando OPP1-B/C
  estabilizarem o contrato de resposta (seção 5.2) — testar contrato antes disso arriscaria quebrar
  a cada campo novo (`gross_idle_amount`, `idle_detection_status`, etc.).
- **Arquivos esperados:** `backend/app/agent/tools/get_opportunities.py`,
  `backend/app/opportunities/services/opportunity_engine.py`,
  `backend/tests/opportunities/test_chat_api_parity.py`.
- **Esforço:** 1–2 dias.
- **Por que primeiro:** sem isso, os Tickets OPP1-B e OPP1-C teriam que ser implementados (e mantidos) em
  dois lugares.
- **Status:** ✅ concluído. A tool não tem mais `_calc_idle_amount`/`_get_cdi_monthly` próprios;
  chama `OpportunityEngine().analyze(..., persist_snapshot=False)` (sem persistir snapshot a cada
  pergunta do chat, diferente do GET da API e do job diário).

### Ticket OPP1-B — Proteção de reserva de emergência

- Estender `IdleMoneyResult` (`idle_money_detector.py:17-23`) com dois campos novos:
  `gross_idle_amount: float`, `emergency_reserve: float`, `reserve_months_applied: int`, sem quebrar
  a assinatura atual de `detect(user_id)`.
- `detect()` passa a aceitar `user_profile: UserProfile | None = None` opcional; quando fornecido,
  calcula a reserva e subtrai do `idle_amount` bruto.
- `OpportunityEngine.analyze()` monta o `UserProfile` chamando
  `ConsumptionProfiler().build(transactions_df)` com o mesmo DataFrame que já buscou para o
  detector — **sem query adicional**.
- Tabela de proteção (proposta inicial, ver seção 3 e seção 8):
  ```python
  _RESERVE_MONTHS_BY_FSS = {
      "SAUDAVEL": 6, "ATENCAO": 6,
      "ALERTA": 9, "CRITICO": 9,
  }
  ```
- `idle_amount_final = max(0.0, idle_bruto − reserve_months_applied × avg_expenses_3m)`.
- **Critério de aceite:** um usuário com `fss_level in {"ALERTA", "CRITICO"}` não recebe
  recomendação de investir em produto de baixa liquidez o valor que corresponde à sua reserva de
  segurança; `OpportunitiesResponse` expõe `emergency_reserve` para transparência (o usuário
  precisa entender por que o valor sugerido é menor do que ele "acha" que tem sobrando).
- **Teste:** fixtures para os 4 níveis de `fss_level`, verificando que a reserva correta é
  subtraída e que `idle_amount_final` nunca fica negativo.
- **Arquivos esperados:** `backend/app/opportunities/services/idle_money_detector.py`,
  `backend/app/opportunities/models.py`, `backend/tests/opportunities/test_idle_money_detector.py`.
- **Esforço:** 3–5 dias (inclui integrar `ConsumptionProfiler` no fluxo do `OpportunityEngine`).

### Ticket OPP1-C — Threshold de persistência (R$500 / 30 dias)

- Hoje nada verifica se o saldo ocioso é estável no tempo — cada chamada recalcula do zero sobre a
  janela de 3 meses.
- Fonte de dados: `opportunity_snapshots`. A tabela já existe e `OpportunityEngine` já persiste
  snapshots quando chamado; se o job diário ainda não estiver executando o engine para todos os
  usuários ativos, isso deve ser tratado como pré-requisito operacional deste ticket.
- **Ação:** nova consulta em `OpportunityEngine` (ou serviço próprio) que lê os últimos 30 dias de
  `opportunity_snapshots` do usuário e verifica se `idle_amount ≥ R$500` se manteve (ex.: em pelo
  menos 90% dos snapshots, para tolerar ruído de um dia atípico).
- Novos campos em `OpportunitiesResponse`: `is_confirmed_idle: bool`, `days_tracked: int`,
  `idle_detection_status: str`, `idle_detection_reason: str`.
- **Cold start:** usuário novo (< 30 dias de snapshots) não tem como ser "confirmado" — reaproveitar
  o padrão já existente de `has_sufficient_data` (`idle_money_detector.py:23`) para rotular a
  recomendação como "estimativa preliminar" em vez de bloquear a resposta.
- **Decisão de produto pendente:** manter a recomendação visível mesmo sem confirmação (como hoje),
  só com o rótulo diferente, ou suprimir até completar 30 dias? Recomendo manter visível — supressão
  atrasa o primeiro insight do usuário, que é uma métrica de sucesso do produto
  (`docs/ROADMAP.md`, "Tempo até primeiro insight < 30s").
- **Teste:** série temporal sintética de snapshots cobrindo os casos limite (exatamente 30 dias,
  29 dias, valor oscilando acima/abaixo de R$500).
- **Arquivos esperados:** `backend/app/opportunities/services/opportunity_engine.py`,
  `backend/app/jobs/opportunity_scan.py`, `backend/tests/opportunities/test_opportunity_engine.py`.
- **Esforço:** 3–4 dias.

### Ticket OPP1-D — Testes e regressão (transversal)

Confirmado: **não existe `tests/opportunities/`** hoje (só há testes de outro módulo,
`tests/optimizer/test_opportunity_cost.py` e `test_opportunity_score.py`, que não tocam este
código). Isso já é apontado como Gap 4 em `docs/OPP.md` seção 14.

- Cobrir, à medida que cada etapa acima é implementada:
  `tests/opportunities/test_idle_money_detector.py` (fluxo puro, com reserva, com threshold),
  `tests/opportunities/test_opportunity_engine.py` (orquestração, persistência de snapshot),
  teste de paridade chat vs. API (Ticket OPP1-A).
- Rodar ao menos:
  ```bash
  cd backend
  python -m pytest tests/opportunities tests/agent/test_agent_router.py -q
  ```
- **Esforço:** não é uma etapa isolada — orçar +1 dia por etapa acima para os testes específicos,
  já embutido nas estimativas.

---

## 7. Backlog explícito da Opção B (saldo real Pluggy)

Esta parte fica fora da entrega de ~2 semanas, mas precisa existir para não perder a direção
arquitetural correta do ROADMAP.

| Ticket | Entrega | Observação |
|---|---|---|
| OPP1-E | Criar tabela `accounts` / `account_snapshots` | Separar saldo atual de histórico de saldo |
| OPP1-F | Persistir `balance` de `PluggyClient.get_accounts()` | Integrar no sync Pluggy sem quebrar transações |
| OPP1-G | Expor saldo confiável para `forecast/` e `opportunities/` | Substitui `sum(transactions)` em fluxos críticos |
| OPP1-H | Recalcular fórmula literal do ROADMAP | `idle = saldo_atual - N meses de gastos - reserva` |

**Critério de promoção:** quando Opção B existir, Opção A deixa de ser "detecção" e vira apenas
fallback para bancos sem saldo disponível.

---

## 8. Riscos e decisões em aberto

- **Valores da tabela de reserva (6/9 meses) não são validados** — são a proposta de
  `docs/OPP.md` seção 6.2, herdada aqui. Validar com produto/jurídico antes de codar o Ticket OPP1-B,
  já que isso afeta diretamente quanto o app recomenda investir.
- **Custo de rodar `ConsumptionProfiler` a cada chamada de `/opportunities/{user_id}`** — o
  profiler processa 90 dias de transações; se o endpoint for chamado com frequência alta por
  usuário, pode valer cachear o `UserProfile` (o `optimizer/` já deve ter esse resultado calculado
  em algum outro fluxo — checar antes de recalcular do zero).
- **Cold start de 30 dias (Ticket OPP1-C)** — como comunicar ao usuário, no chat e num futuro card de
  feed, que a recomendação ainda é "preliminar"? Requer decisão de UX, não só de backend.
- **Opção B (saldo real via Pluggy, seção 4)** fica deliberadamente fora deste plano — é uma
  decisão de infraestrutura compartilhada com o `forecast/`, não algo para decidir dentro do
  escopo de OPP.1.
- **Semântica de "dinheiro parado" no MVP** — no texto público, chamar de "estimativa de dinheiro
  ocioso" enquanto a Opção B não existir. Evitar prometer saldo real em conta corrente.
- **Risco de recomendação inadequada** — se o status não for `CONFIRMED`, o produto deve priorizar
  educação/simulação em vez de call-to-action agressiva para migrar dinheiro.

---

## 9. Resumo e estimativa

| Etapa | Entrega | Esforço | Bloqueia |
|---|---|---|---|
| OPP1-A | Unificar `idle_amount` (chat + API) | 1–2 dias | B, C (evita retrabalho duplicado) |
| OPP1-B | Reserva de emergência via `fss_level` | 3–5 dias | — |
| OPP1-C | Threshold R$500 / 30 dias | 3–4 dias | — |
| OPP1-D | Testes dedicados | embutido nas etapas acima | — |
| OPP1-UX | Mapear consumo no Feed/Notificações e Agente IA | 1 dia | Não cria tela nova |
| **Total (Opção A)** | | **~2 semanas** | |
| Opção B (saldo real Pluggy) | fora deste plano — iniciativa própria | não estimado aqui | — |

---

## 10. Checklist final para revisão de PR

- [ ] `git grep "_calc_idle_amount"` não encontra implementação ativa fora de testes ou histórico.
- [ ] `IdleMoneyResult` diferencia valor bruto, reserva protegida e valor final.
- [ ] `OpportunitiesResponse` inclui status de detecção e motivo legível.
- [ ] Chat e endpoint usam o mesmo engine.
- [ ] Feed/Notificações e Agente IA são os únicos canais de exposição planejados.
- [ ] Usuário `CRITICO` ou `ALERTA` recebe proteção de 9 meses de gastos.
- [ ] `CONFIRMED` exige janela de 30 dias e tolerância documentada.
- [ ] Produtos de baixa liquidez não são priorizados para reserva protegida.
- [ ] Testes cobrem DataFrame vazio, cold start, 4 FSS levels, 30 dias confirmados e oscilação abaixo do threshold.
- [ ] Texto do produto usa "estimativa" enquanto não houver saldo real Pluggy.
