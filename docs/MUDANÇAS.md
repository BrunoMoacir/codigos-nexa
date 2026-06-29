# Nexa — O Que Precisa Mudar para Chegar no Roadmap

Este documento mapeia cada mudança técnica necessária para implementar as features do ROADMAP.md,
organizado por camada: infraestrutura → banco de dados → módulos existentes → novos módulos.

> **Auditoria de 2026-06-24:** conferido linha a linha contra `backend/app/`, `backend/alembic/versions/` e
> `backend/tests/`. Correções estão marcadas com "↳ verificado". Nenhum conteúdo original foi removido.

> **Revisão complementar de 2026-06-24:** corrigidas inconsistências de contagem, unidades das séries BACEN,
> maturidade do frontend e viabilidade presumida de APIs externas. Este documento descreve uma proposta técnica;
> itens externos ou jurídicos só podem virar compromisso de sprint depois de uma spike de validação.

---

## 1. INFRAESTRUTURA — Bloqueadores Críticos

Estas são as mudanças que desbloqueiam múltiplas features ao mesmo tempo.
Sem elas, 60%+ do roadmap não pode ser entregue.

---

### 1.1 Scheduler de Jobs (bloqueia: D2, D4, R1.c, OPP, V2) ✅ INFRAESTRUTURA PRONTA — jobs ainda são stubs

**Implementado em:**
- `backend/requirements.txt` e `backend/requirements.railway.txt` — `apscheduler>=3.10.0` adicionado em ambos
- `backend/app/core/scheduler.py` — `AsyncIOScheduler` + `register_jobs()` com 5 jobs e seus horários
- `backend/app/jobs/_base.py` — `get_active_user_ids()` + `@job_guard` com **lock distribuído Redis** (`SET NX EX 7200`) e fallback em memória
- `backend/app/jobs/fee_snapshot.py` — stub 02h00 (D2/D4)
- `backend/app/jobs/opportunity_scan.py` — stub 03h00 (OPP)
- `backend/app/jobs/health_score_snapshot.py` — stub 04h00 (MX.1)
- `backend/app/jobs/notification_scheduler.py` — stub a cada 6h (MX.3)
- `backend/app/jobs/daily_digest.py` — stub 07h00 (R1.c)
- `backend/app/core/config.py` — `SCHEDULER_ENABLED: bool = False` (ativa com env var em produção)
- `backend/app/main.py` — lifespan sobe/derruba o scheduler conforme a flag

**Status dos jobs:**
- ✅ Lógica real de `fee_snapshot` → item 3.1 (costs/) — FEITO
- ✅ Lógica real de `opportunity_scan` → item 2.8 (opportunity_snapshots) — FEITO
- ✅ Lógica real de `health_score_snapshot` → item 3.4 (health_score/) — FEITO
- ✅ Lógica real de `notification_scheduler` → item 3.3 (notifications/) — FEITO
- ✅ Lógica real de `daily_digest` → item 1.2 (sistema de envio) — FEITO

---

### 1.2 Sistema de Envio (bloqueia: R1.c Daily Digest) ✅ INFRAESTRUTURA PRONTA

**Implementado em:**
- `backend/app/core/notifications/email_sender.py` — dois backends: SendGrid (HTTP API v3 via `requests`) e SMTP (`smtplib` nativo). Se nenhum estiver configurado, ignora silenciosamente com log WARNING.
- `backend/app/core/notifications/delivery_service.py` — consulta `user_settings.notification_channels` (quando a tabela existir, item 2.x); fallback: email se algum backend estiver configurado, senão `in_app`. Canal `push` reservado para quando o app mobile existir.
- `backend/app/core/config.py` — novas vars: `EMAIL_FROM`, `EMAIL_FROM_NAME`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SENDGRID_API_KEY`.

**Status:**
- ✅ Lógica real do `daily_digest.py` que chama `delivery_service.deliver()` — FEITO (jobs/daily_digest.py implementado com 4 coletores de eventos, formatter HTML, idempotência e log)
- ⏳ `push_sender.py` (FCM) → depende de app mobile (sem prazo)

---

## 2. BANCO DE DADOS — Tabelas a Criar ✅ FEITO

Novas tabelas via Alembic migration. Nenhuma tabela existente precisa ser removida.

**Implementado em:** `backend/alembic/versions/e1a2b3c4d5f6_add_nexa_roadmap_tables.py`
- Todas as 8 tabelas criadas com `upgrade()` + `downgrade()` completo
- Índices criados: `idx_bank_fee_history_user`, `idx_notif_delivery_user`, `idx_notif_delivery_notif_id`, `idx_user_badges_user`, `idx_negotiation_history_user`, `idx_opp_snapshots_user`
- Constraints de unicidade: `uq_bank_fee_history`, `uq_bank_fee_trends`, `uq_daily_digest_log`, `uq_user_badges`
- Tipos seguem o padrão do projeto: `sa.String(36)` para IDs, `sa.Text()` para JSON, `sa.DateTime(timezone=True)` para timestamps
- Chain Alembic verificada: `e1a2b3c4d5f6 ← f3a2b1c0d4e5`

**Regras de modelagem antes da migration:**
- alinhar `user_id` ao tipo `String` usado por `users.user_id` e adicionar foreign keys onde aplicável;
- preferir `DATE` para competência mensal em vez de `VARCHAR(7)`;
- não usar uma restrição que elimine cobranças duplicadas, pois duplicidade é evidência necessária para D2;
- padronizar timestamps com timezone, índices, retenção e política de exclusão;
- incluir idempotency key, tentativas e último erro nos fluxos de jobs e entrega;
- documentar a extensão PostgreSQL necessária antes de usar `gen_random_uuid()`.

---

### 2.1 `bank_fee_history` — Histórico de Tarifas por Usuário ✅ FEITO (DDL + código)
**Necessária para:** D1, D2, D4

**Implementado em:**
- Migration `e1a2b3c4d5f6` — tabela criada
- `backend/app/costs/bank_fee_analyzer.py` — `INSERT INTO bank_fee_history` após análise de tarifas
- `backend/app/jobs/fee_snapshot.py` — job diário popula histórico por usuário

```sql
CREATE TABLE bank_fee_history (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     VARCHAR NOT NULL,
    month       VARCHAR(7) NOT NULL,       -- "YYYY-MM"
    bank_name   VARCHAR NOT NULL,
    fee_type    VARCHAR NOT NULL,           -- FeeType enum
    amount      DECIMAL(10, 2) NOT NULL,
    description VARCHAR,
    captured_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, month, bank_name, fee_type)
);
CREATE INDEX idx_bank_fee_history_user ON bank_fee_history(user_id, month);
```

---

### 2.2 `bank_fee_trends` — Baseline de Mercado por Banco ✅ FEITO (DDL + código)
**Necessária para:** D4 (detectar aumento unilateral), D2 (o que é normal vs. indevido)

**Implementado em:**
- Migration `e1a2b3c4d5f6` — tabela criada
- `backend/app/jobs/fee_snapshot.py` — `INSERT INTO bank_fee_trends` agrega baseline de mercado por banco/tipo

```sql
CREATE TABLE bank_fee_trends (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_name   VARCHAR NOT NULL,
    fee_type    VARCHAR NOT NULL,
    month       VARCHAR(7) NOT NULL,
    market_avg  DECIMAL(10, 2),            -- média de mercado (de todos os usuários Nexa, anonimizado)
    market_p25  DECIMAL(10, 2),
    market_p75  DECIMAL(10, 2),
    sample_size INT,
    captured_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (bank_name, fee_type, month)
);
```

---

### 2.3 `notification_delivery_log` — Log de Entrega de Notificações ✅ FEITO (DDL + código)
**Necessária para:** MX.3 (proativo), R1.c, R5.c

**Implementado em:**
- Migration `e1a2b3c4d5f6` — tabela criada
- `backend/app/core/notifications/delivery_service.py` — grava log a cada entrega (status sent/failed/in_app)
- `backend/app/jobs/daily_digest.py` — lê log para verificar se já foi entregue nas últimas 24h

```sql
CREATE TABLE notification_delivery_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR NOT NULL,
    notification_id VARCHAR NOT NULL,
    channel         VARCHAR NOT NULL,    -- "email" | "push" | "in_app"
    status          VARCHAR NOT NULL,    -- "sent" | "delivered" | "failed" | "opened"
    sent_at         TIMESTAMP,
    delivered_at    TIMESTAMP,
    opened_at       TIMESTAMP,
    error_msg       VARCHAR
);
```

---

### 2.4 `daily_digest_log` — Controle de Digests Enviados ✅ FEITO (DDL + código)
**Necessária para:** R1.c

**Implementado em:**
- Migration `e1a2b3c4d5f6` — tabela criada
- `backend/app/jobs/daily_digest.py` — verifica idempotência antes de enviar (`_already_sent_today`) e grava log após entrega (`_log_digest`); constraint `uq_daily_digest_log (user_id, date)` garante 1 digest/dia

```sql
CREATE TABLE daily_digest_log (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    VARCHAR NOT NULL,
    date       DATE NOT NULL,
    events_qty INT,
    sent_at    TIMESTAMP,
    UNIQUE (user_id, date)
);
```

---

### 2.5 `user_badges` — Badges e Gamificação ✅ FEITO (DDL + código)
**Necessária para:** R2.b (Health Score gamificado)

**Implementado em:**
- Migration `e1a2b3c4d5f6` — tabela criada
- `backend/app/health_score/badge_service.py` — `BadgeService.evaluate_badges()` persiste badges com `ON CONFLICT DO NOTHING` (idempotente); 7 tipos: PRIMEIRO_INSIGHT, 3_MESES_VERDE, 6_MESES_VERDE, NEGOCIADOR, ECONOMIZOU_100/500/1000
- `backend/app/health_score/router.py` — hook após cálculo de score + `GET /health-score/badges/{user_id}`
- `backend/app/jobs/health_score_snapshot.py` — avalia badges para todos os usuários ativos

```sql
CREATE TABLE user_badges (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     VARCHAR NOT NULL,
    badge_type  VARCHAR NOT NULL,     -- ex: "PRIMEIRO_INSIGHT", "ECONOMIZOU_500", "3_MESES_VERDE"
    earned_at   TIMESTAMP NOT NULL,
    metadata    JSONB,
    UNIQUE (user_id, badge_type)      -- cada badge é ganho uma vez
);
CREATE INDEX idx_user_badges_user ON user_badges(user_id);
```

**Badge types planejados:**
- `PRIMEIRO_INSIGHT` — primeiro uso do app
- `NEGOCIADOR` — usou F13 pela primeira vez
- `ECONOMIZOU_100` / `_500` / `_1000` — marcos de economia
- `3_MESES_VERDE` / `6_MESES_VERDE` — score acima de 70 por N meses consecutivos
- `TARIFA_ELIMINADA` — conseguiu isenção de anuidade
- `META_ATINGIDA` — completou uma meta financeira

---

### 2.6 `user_settings` — Preferências de Usuário ✅ FEITO (DDL + código)
**Necessária para:** MX.3 proativo, R1.c, R5.b (pause)

**Implementado em:**
- Migration `e1a2b3c4d5f6` — tabela criada
- `backend/app/settings/router.py` — `GET /settings/{user_id}` (retorna defaults quando linha não existe) + `PUT /settings/{user_id}` (upsert com merge de campos) + `create_default_settings()` helper
- `backend/app/api/v1/router.py` — `settings_router` registrado
- `backend/app/api/v1/routes/auth.py` — hook no `register` cria linha padrão (try/except — nunca bloqueia cadastro)

```sql
CREATE TABLE user_settings (
    user_id                 VARCHAR PRIMARY KEY,
    notification_channels   JSONB DEFAULT '["email"]',   -- ["email", "push"]
    notification_frequency  VARCHAR DEFAULT 'daily',     -- "realtime" | "daily" | "weekly" | "off"
    digest_time             TIME DEFAULT '07:00',
    subscription_status     VARCHAR DEFAULT 'active',    -- "active" | "paused" | "cancelled"
    paused_until            TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT NOW()
);
```

---

### 2.7 `negotiation_history` — Histórico de Negociações ✅ FEITO (DDL + código)
**Necessária para:** F13 (follow-up), futura detecção de sucesso pós-negociação

**Implementado em:**
- Migration `e1a2b3c4d5f6` — tabela criada
- `backend/app/negotiator/router.py` — `_persist_negotiation()` insere ao gerar roteiro + `GET /negotiator/history/{user_id}` (lista histórico com totais) + `PATCH /negotiator/history/{record_id}` (usuário reporta resultado: sucesso/parcial/recusado/nao_tentou; preenche `result_status`, `result_gain`, `resolved_at`)

```sql
CREATE TABLE negotiation_history (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        VARCHAR NOT NULL,
    bank_name      VARCHAR NOT NULL,
    trigger_type   VARCHAR NOT NULL,     -- NegotiationTrigger enum
    potential_gain DECIMAL(10, 2),
    generated_at   TIMESTAMP NOT NULL,
    result_status  VARCHAR,              -- "sucesso" | "parcial" | "recusado" | "nao_tentou"
    result_gain    DECIMAL(10, 2),
    resolved_at    TIMESTAMP
);
CREATE INDEX idx_negotation_history_user ON negotiation_history(user_id, generated_at);
```

---

### 2.8 `opportunity_snapshots` — Histórico do Radar de Oportunidades ✅ FEITO (DDL + código)
**Necessária para:** OPP, V2 (Wrapped)

**Implementado em:**
- Migration `e1a2b3c4d5f6` — tabela criada
- `backend/app/jobs/opportunity_scan.py` — stub substituído por implementação completa: calcula `idle_amount` (avg_income_3m − avg_expenses_3m), CDI via AnbimaConnector, seleciona `top_opportunity` (LCI/LCA ou CDB), persiste snapshot por usuário ativo

```sql
CREATE TABLE opportunity_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR NOT NULL,
    captured_at     TIMESTAMP NOT NULL,
    idle_amount     DECIMAL(10, 2),
    monthly_loss    DECIMAL(10, 2),
    top_opportunity VARCHAR,             -- banco recomendado
    top_gain_brl    DECIMAL(10, 2),
    cdi_at_capture  DECIMAL(5, 4)
);
CREATE INDEX idx_opp_snapshots_user ON opportunity_snapshots(user_id, captured_at);
```

---

## 3. MÓDULOS EXISTENTES — O Que Muda

Módulos que já existem mas precisam ser modificados para suportar o roadmap.

---

### 3.1 `backend/app/costs/` — F5: Raio-X de Custos ✅ FEITO
**Mudanças necessárias para:** D1, D2, D4

**Problema atual:**
`BankFeeAnalyzer.analyze()` calcula snapshot do período mas não persiste.
Sem histórico, não dá para detectar D4 (aumento unilateral) nem D2 (cobrança indevida nova).

↳ **verificado 2026-06-24:** já existe `backend/app/costs/market_fees_db.py` com uma `MarketFeesDB` — uma tabela
estática hardcoded (`_BANK_FEES_DB`) com a tarifa mensal média por banco, usada hoje pelo `BankFeeAnalyzer` para
calcular `_calc_savings_opportunity`. Ou seja, **já existe comparação com benchmark de mercado** — o que falta não
é a comparação em si, é (a) tornar esse benchmark dinâmico/histórico em vez de estático no código, e (b) persistir
o histórico **por usuário** (`bank_fee_history`) para poder detectar variação mês a mês, que é o que realmente
falta para D2/D4.

**O que muda:**

1. **Persistir resultado em `bank_fee_history`**
   ```python
   # bank_fee_analyzer.py — adicionar após o cálculo
   async def _persist_snapshot(self, report: BankCostReport, db: Session): ...
   ```

2. **Novo método: comparar mês atual vs. histórico**
   ```python
   def detect_new_fees(self, user_id: str, current_fees: list[FeeEntry]) -> list[FeeEntry]:
       """Retorna tarifas que apareceram este mês e não existiam no histórico."""
   ```

3. **Novo método: comparar vs. baseline de mercado**
   ```python
   def compare_to_market_baseline(self, user_id: str, bank_name: str) -> dict:
       """Compara tarifas do usuário com mediana anônima de outros usuários no mesmo banco."""
   ```

4. **Novo FeeType:** `SEGURO_EMBUTIDO` para detectar D1 (venda casada)
   - Padrão: tarifa de seguro cobrada no mesmo mês em que produto de crédito foi contratado

---

### 3.2 `backend/app/negotiator/` — F13: Negociador ✅ FEITO
**Mudanças necessárias para:** D3

**Problema atual (corrigido — verificado 2026-06-24):**
A descrição original deste documento estava imprecisa. O que existe de fato em
`backend/app/negotiator/opportunity_detector.py`:

- `_detect_juros_rotativo()` (linha 126) **já busca a taxa de mercado dinamicamente** via
  `_fetch_market_rate_monthly()` (linha 291), que chama `BacenConnector().get_selic()` e soma um spread fixo de
  2,5 p.p. — com fallback de 3,99% a.m. se a API do BACEN cair. **Não é hardcoded.**
- `_ANUIDADE_MARKET_MONTHLY_AVG = 30.0` (linha 36) existe, sim, mas é usado por `_detect_anuidade_alta()`
  (trigger de anuidade alta), um detector **diferente** do de juros rotativo.

O problema real não é "hardcode vs. BACEN" — é que a taxa usada para juros rotativo é uma aproximação genérica
(SELIC + spread de CDC), e não a série SGS específica de crédito rotativo PF (20714/20715) ou cheque especial
(20706), que o BACEN publica e que dão um benchmark muito mais preciso para alegar abuso. **Esse conector
específico não existe.**

**O que muda:**

1. **Novo conector BACEN para crédito rotativo**
   ```python
   # backend/app/architect/connectors/bacen_credit.py
   class BacenCreditConnector(BaseConnector):
       # SGS 20714 = taxa média de juros no crédito rotativo PF
       # SGS 20715 = taxa máxima no crédito rotativo
       _ROTATIVO_SERIES = 20714
       _ROTATIVO_MAX_SERIES = 20715
   ```

2. **Trocar a aproximação SELIC+spread pela série SGS real**
   ```python
   # opportunity_detector.py
   # ANTES (linha 291): SELIC + spread de 2.5 p.p., fallback 3.99% a.m.
   # DEPOIS:
   @staticmethod
   def _fetch_market_rate_monthly() -> float:
       rates = BacenCreditConnector().get_rates()
       return rates["rotativo_monthly"]   # SGS 20714 já vem em % a.m.; normalizar para decimal sem dividir por 12
   ```
   (a anuidade continua usando seu próprio benchmark — ver nota acima; não precisa de conector BACEN,
   mas pode evoluir para usar dados reais de mercado de anuidades se houver fonte confiável)

3. **Novo trigger: `CHEQUE_ESPECIAL_ALTO`**
   - Comparar a taxa efetiva do contrato com a série BACEN e com a norma aplicável ao perfil/produto.
   - O possível teto de 8% a.m. deve ser validado por jurídico com fonte, vigência, escopo e exceções antes
     de ser codificado; não atribuir automaticamente essa regra à Lei 14.905/2024.

4. **Persistir em `negotiation_history`** após geração de script

---

### 3.3 `backend/app/notifications/` — MX.3: Notificações ✅ FEITO
**Mudanças necessárias para:** D4, R1.c

**Problema atual:**
Notificações são geradas apenas quando o usuário chama `GET /notifications/{user_id}`.
São reativas, não proativas.

**O que muda:**

1. **Novo `NotificationType.TARIFA_AUMENTO_UNILATERAL`**
   ```python
   # notifier.py — novo método
   def _gen_tarifa_aumento(self, fee_delta: FeeDelta) -> Optional[Notification]:
       """Gera notificação quando tarifa aumentou mais de 10% vs. mês anterior."""
   ```

2. **Desacoplar geração de notificações do request HTTP**
   - Criar `NotificationEngine` independente que pode ser chamado pelo scheduler
   ```python
   # backend/app/notifications/engine.py
   class NotificationEngine:
       async def run_for_user(self, user_id: str) -> list[Notification]: ...
       async def run_for_all_users(self) -> dict[str, list[Notification]]: ...
   ```

3. **Integrar com `delivery_service.py`** (novo, da seção 1.2)
   - Após gerar notificação → entrega via canal configurado em `user_settings`

---

### 3.4 `backend/app/health_score/` — MX.1: Health Score ✅ FEITO
**Mudanças necessárias para:** R2.b

**Problema atual:**
Score calculado sem gamificação. Não há badges, desafios nem marcos.

**Implementado em:**
- `backend/app/health_score/badge_service.py` — `BadgeService.evaluate_badges()` com 7 tipos de badge; persiste em `user_badges` com ON CONFLICT DO NOTHING (idempotente)
- `backend/app/health_score/router.py` — novo `GET /health-score/badges/{user_id}` + hook após cálculo de score
- `backend/app/jobs/health_score_snapshot.py` — stub substituído por implementação completa: calcula score para todos os usuários ativos, salva snapshot e avalia badges

**O que muda:**

1. **Novo serviço de badges**
   ```python
   # backend/app/health_score/badge_service.py
   class BadgeService:
       def evaluate_badges(self, user_id: str, current_score: int, history: list) -> list[Badge]:
           """Avalia se algum badge novo foi conquistado. Persiste em user_badges."""
   ```

2. **Novo endpoint de badges**
   ```
   GET /api/v1/health-score/badges/{user_id}
   ```

3. **Hook no cálculo de score** — após calcular, chamar `BadgeService.evaluate_badges()`

---

### 3.5 `backend/app/agent/` — LangGraph Agent ✅ FEITO
**Mudanças necessárias para:** OPP, T3, V2, D1–D3

**Problema atual:**
Agent tem 15 tools mas não tem tools para as novas verticais.

**Implementado em:**
- `backend/app/agent/tools/get_opportunities.py` — OPP: detecta dinheiro parado (avg_income−avg_expenses), compara CDB vs LCI/LCA com breakeven
- `backend/app/agent/tools/get_forgotten_rights.py` — T3: orienta SVR BACEN, FGTS, PIS/PASEP, Restituição IR via canais oficiais (sem scraping)
- `backend/app/agent/tools/get_annual_wrapped.py` — V2: retrospectiva financeira anual por score, tarifas, negociações e badges
- `backend/app/agent/tools/detect_abusive_fees.py` — D1: venda casada (seguro embutido em crédito) via BankFeeAnalyzer
- `backend/app/agent/tools/detect_wrongful_charges.py` — D2: tarifas duplicadas, cobranças pós-cancelamento, bancos sem transações há 60 dias
- `backend/app/agent/tools/detect_abusive_interest.py` — D3: juros acima de BACEN SGS via BacenCreditConnector
- `backend/app/agent/graph.py` — atualizado para 21 tools; SYSTEM_PROMPT expandido com instruções para cada nova tool

**O que muda — novas tools a adicionar:**

```python
# backend/app/agent/tools/
get_opportunities()           # OPP: radar de dinheiro parado + comparação de bancos
get_forgotten_rights()        # T3: SVR BACEN, FGTS, PIS/PASEP
get_annual_wrapped()          # V2: resumo anual vs. bancos
detect_abusive_fees()         # D1: detector de venda casada
detect_wrongful_charges()     # D2: cobranças indevidas
detect_abusive_interest()     # D3: juros acima da taxa BACEN
```

---

### 3.6 `backend/app/fiscal/` — M4.1: Fiscal ✅ FEITO
**Mudanças necessárias para:** T1, T2

**Problema atual:**
Suporta apenas MEI/PJ (DAS, receita de serviços). Sem IR pessoa física.

**Implementado em:**
- `backend/app/fiscal/ir_pf_calculator.py` — `IRPFCalculator` completo: `calc_ir_on_cdb()`, `calc_ir_on_lci_lca()`, `calc_breakeven_lci()`, `compare()`; tabela regressiva Lei 8.981/1995 (22,5%→15%); isenção total para LCI/LCA/CRI/CRA
- `backend/app/fiscal/router.py` — dois novos endpoints: `GET /fiscal-report/ir-pf/compare` (CDB vs LCI/LCA) e `GET /fiscal-report/ir-pf/breakeven` (taxa mínima de LCI equivalente)
- `backend/app/settings/router.py` — **gap adicional**: `GET /settings/{user_id}` e `PUT /settings/{user_id}` + `create_default_settings()` chamado no cadastro; preenche `user_settings` que ficava sempre vazia

**O que muda:**

1. **Novo `FiscalPFService`** para cálculo de IR em investimentos
   ```python
   # backend/app/fiscal/services/ir_pf_calculator.py
   class IRPFCalculator:
       def calc_ir_on_cdb(self, amount: float, holding_months: int) -> float:
           """Calcula alíquota progressiva (22.5% → 15%)"""
       def calc_ir_on_lci_lca(self, amount: float) -> float:
           """Sempre 0% — isento"""
       def calc_breakeven_lci(self, cdb_rate_pct: float) -> float:
           """Taxa mínima de LCI que equivale ao CDB após IR"""
   ```

---

## 4. NOVOS MÓDULOS A CRIAR

Features inteiramente novas que não têm base no código atual.

---

### 4.1 `backend/app/opportunities/` — OPP: Radar de Oportunidades ✅ FEITO

**Implementado em:**
- `backend/app/opportunities/__init__.py`
- `backend/app/opportunities/models.py` — `OpportunityItem`, `OpportunitiesResponse`, `CompareRequest`, `CompareResponse`
- `backend/app/opportunities/services/idle_money_detector.py` — `IdleMoneyDetector.detect()` calcula avg_income_3m − avg_expenses_3m
- `backend/app/opportunities/services/bank_comparator.py` — `BankComparator.rank()` carrega catálogo JSON, calcula taxa líquida via `IRPFCalculator`, ranqueia por `annual_rate_net_pct`
- `backend/app/opportunities/services/opportunity_engine.py` — `OpportunityEngine.analyze()` orquestra detector + comparador + snapshot
- `backend/app/opportunities/router.py` — `GET /opportunities/{user_id}` e `POST /opportunities/compare`
- `backend/data/bank_products.json` — 20 produtos de 10 bancos (taxas em % do CDI)
- `backend/app/api/v1/router.py` — `opportunities_router` registrado
- `backend/app/jobs/opportunity_scan.py` — job diário delegado ao `OpportunityEngine`

**Proposta de estrutura:**
```
backend/app/opportunities/
  __init__.py
  models.py                        # OpportunitiesRequest / OpportunitiesResponse
  router.py                        # GET /opportunities/{user_id}
  services/
    idle_money_detector.py         # calcula dinheiro parado via histórico DuckDB
    bank_comparator.py             # compara CDB/LCI/LCA de 12+ bancos
    opportunity_engine.py          # orquestra e ranqueia por retorno líquido após IR
backend/data/bank_products.json    # catálogo curado de produtos bancários
```

**Lógica central:**
- Idle = avg_income_3m − avg_expenses_3m (acumulado por meses sem uso)
- Ranqueia por `annual_rate_net_pct` (após IR, não taxa bruta)
- CDI via `AnbimaConnector` já existente (BCB SGS série 12); a série 432 do `BacenConnector` é SELIC meta
- Para LCI/LCA: equivalência bruta = taxa_lci / (1 − aliquota_ir)

**Endpoint:**
```
GET /api/v1/opportunities/{user_id}
POST /api/v1/opportunities/compare  # comparação ad hoc com valor específico
```

---

### 4.2 `backend/app/defense/` — D1–D5: Defesa do Consumidor ✅ FEITO

**Implementado em:**
- `backend/app/defense/models.py` — `DefenseFinding`, `MonetaryCorrection`, `EvidenceDossier`, `DefenseResponse`
- `backend/app/defense/services/tied_sale_detector.py` — D1: detecta venda casada via BankFeeAnalyzer + bank_fee_history
- `backend/app/defense/services/wrongful_charge_detector.py` — D2: duplicatas + bancos inativos cobrando + tarifas novas sem histórico
- `backend/app/defense/services/abusive_interest_detector.py` — D3: juros acima BACEN SGS via negotiation_history + transações
- `backend/app/defense/services/unilateral_change_detector.py` — D4: compara bank_fee_history mês atual vs anterior, flag >10%
- `backend/app/defense/services/evidence_builder.py` — D5: correção monetária (IPCA/SELIC), renderiza 3 templates
- `backend/app/defense/router.py` — `GET /defense/{user_id}` e `GET /defense/{user_id}/dossier`
- `backend/templates/contestation_letter.md`, `procon_dossier.md`, `jec_petition.md`
- `backend/app/api/v1/router.py` — `defense_router` registrado

**Proposta de estrutura:**
```
backend/app/defense/
  __init__.py
  models.py                             # DefenseAnalysis, EvidenceDossier, ContestationLetter
  router.py                             # /defense/* endpoints
  services/
    tied_sale_detector.py               # D1: venda casada — seguro embutido em crédito
    wrongful_charge_detector.py         # D2: tarifas duplicadas, pós-cancelamento, sem contrato
    abusive_interest_detector.py        # D3: taxa implícita vs. BACEN SGS 20714/20715
    unilateral_change_detector.py       # D4: tarifa que subiu >10% sem notificação prévia
    evidence_builder.py                 # D5: monta dossiê com timeline e cálculo de correção
templates/
  contestation_letter.md               # D2: template de carta de contestação
  procon_dossier.md                    # D5: template de dossiê para PROCON
  jec_petition.md                      # D5: modelo de petição para juizado especial
```

**D5 — Cálculo de Correção Monetária:**
```python
# evidence_builder.py
def calc_monetary_correction(
    original_value: float,
    charge_date: date,
    reference_date: date,
    index: Literal["IPCA", "SELIC", "INPC"]
) -> float:
    """Usa IpcaConnector (já existe) para calcular correção acumulada."""
```

---

### 4.3 `backend/app/rights/` — T3: Monitor de Direitos Esquecidos ✅ FEITO

**Implementado em:**
- `backend/app/rights/__init__.py`
- `backend/app/rights/models.py` — `ForgottenRight`, `RightsResponse` (Pydantic)
- `backend/app/rights/services/svr_bacen_client.py` — heurística via bank_fee_history + orientação portal SVR
- `backend/app/rights/services/fgts_checker.py` — detecta padrão CLT nas transações, estima 8% × meses
- `backend/app/rights/services/pis_pasep_checker.py` — verifica elegibilidade abono salarial (≤5 SM), orienta CEF/BB
- `backend/app/rights/services/ir_restituicao_checker.py` — escaneia transações por IRRF retido, orienta e-CAC
- `backend/app/rights/router.py` — `GET /rights/{user_id}` (require_owner)
- `backend/app/api/v1/router.py` — `rights_router` registrado

**Abordagem:** sem scraping e sem chamadas a APIs privadas — toda verificação real é feita pelo usuário
nos canais oficiais. Os checkers usam transações Pluggy para contextualizar relevância e estimar valores.

**Proposta de estrutura:**
```
backend/app/rights/
  __init__.py
  models.py                         # RightsCheckResult, ForgottenRight
  router.py                         # GET /rights/{user_id}
  services/
    svr_bacen_client.py             # SVR BACEN: integração condicionada a canal oficial autorizado
    fgts_checker.py                 # FGTS: viabilidade/autorização a validar; fallback para orientação ao usuário
    pis_pasep_checker.py            # PIS/PASEP: viabilidade/autorização a validar
    ir_restituicao_checker.py       # Restituição IR via Receita Federal
```

**Spike obrigatória de viabilidade:**
- confirmar documentação oficial, autenticação, autorização de uso e tratamento de CPF para cada fonte;
- os caminhos anteriormente tratados como APIs retornaram HTML ou não resolveram DNS na auditoria, portanto
  não devem ser usados como contrato de integração;
- quando não houver API oficial, oferecer link/orientação ao usuário em vez de scraping de área autenticada;
- registrar análise LGPD, consentimento, retenção e base legal antes de armazenar resultados.

---

### 4.4 `backend/app/tax/` — T1/T2: Otimização de IR em Investimentos ✅ FEITO

**Implementado em:**
- `backend/app/tax/__init__.py`
- `backend/app/tax/models.py` — `InvestmentPosition`, `TaxOpportunity`, `TaxAnalysisResponse`, `BreakevenRequest/Response`
- `backend/app/tax/services/investment_profiler.py` — lê `pluggy_items` DB → `PluggyClient.get_investments()` → mapeia para `InvestmentPosition` com IR calculado via `IRPFCalculator`
- `backend/app/tax/services/ir_calculator.py` — `calc_portfolio_ir()`, `calc_breakeven()`, `ir_rate_for_months()` — delega ao `IRPFCalculator` existente
- `backend/app/tax/services/tax_loss_harvesting.py` — T1: detecta posições com perda não realizada (harvest_loss) e posições perto do próximo bracket IR (hold_longer)
- `backend/app/tax/services/zero_tax_mode.py` — T2: CDB→LCI/LCA usando `BankComparator` para verificar breakeven real; come-cotas → CDB para diferir IR semestral
- `backend/app/tax/router.py` — `GET /tax/optimize/{user_id}` (require_owner) + `POST /tax/breakeven` (get_current_user)
- `backend/app/api/v1/router.py` — `tax_router` registrado

**Proposta de estrutura:**
```
backend/app/tax/
  __init__.py
  models.py                            # TaxAnalysis, TaxOpportunity, BreakevenCalc
  router.py                            # GET /tax/optimize/{user_id}
  services/
    ir_calculator.py                   # alíquotas progressivas, equivalência LCI/LCA
    tax_loss_harvesting.py             # T1: identifica oportunidades de vender com prejuízo para abater IR
    zero_tax_mode.py                   # T2: CDB→LCI/LCA, come-cotas→CDB, breakeven
    investment_profiler.py             # usa Pluggy investimentos para mapear carteira atual
```

**Fonte de dados:** Pluggy já retorna investimentos (CDB, LCI, LCA, fundos, ações) via Open Finance

---

### 4.5 `backend/app/viral/` — V1/V2: Viral & Wrapped

**Proposta de estrutura:**
```
backend/app/viral/
  __init__.py
  models.py                        # SavingsCard, WrappedReport
  router.py                        # GET /viral/savings-card/{user_id}, GET /viral/wrapped/{user_id}/{year}
  services/
    savings_consolidator.py        # agrega insights de F2, F5, F13 em um único valor
    wrapped_generator.py           # gera relatório anual "Banco vs Você"
    card_renderer.py               # gera imagem PNG/SVG compartilhável (pode usar Pillow ou HTML→screenshot)
```

**V1 — Consolidação de economia:**
- F2 Optimizer → `net_gain_expected` por ano
- F5 Costs → `savings_opportunity` mensal × 12
- F13 Negotiator → `potential_saving_monthly` × 12
- Total = soma auditada, exibida como "A Nexa te ajudou a guardar R$X em Y meses"

**V2 — Dados do Wrapped:**
- Maior desperdício identificado
- Tarifa mais absurda paga
- Cartão que mais renderia (se tivesse usado)
- Oportunidade de investimento que ficou na conta corrente
- Score de evolução financeira no ano

---

## 5. CONECTORES — Novas Integrações Externas

---

### 5.1 BACEN SGS — Séries de Crédito (D3)

```python
# backend/app/architect/connectors/bacen_credit.py
class BacenCreditConnector(BaseConnector):
    _ROTATIVO_PF_SERIES = 20714      # Juros crédito rotativo PF (% a.m.)
    _ROTATIVO_MAX_SERIES = 20715     # Juros máximos rotativo PF (% a.m.)
    _CHEQUE_ESPECIAL_SERIES = 20706  # Juros cheque especial (% a.m.)
    _CONSIGNADO_SERIES = 25433       # Juros crédito consignado INSS (% a.m.)
```

---

### 5.2 SVR BACEN — Valores a Receber (T3)

```python
# backend/app/rights/services/svr_bacen_client.py
# A definir somente após confirmação de uma API oficial documentada e autorizada.
# A URL pública do portal não deve ser presumida como endpoint JSON por CPF.
# Fallback seguro: direcionar o usuário ao serviço oficial sem coletar credenciais GOV.BR.
```

---

### 5.3 Open Finance Webhook (opcional — upgrade futuro)

```
POST /api/v1/webhooks/pluggy
  → Recebe eventos de novas transações em tempo real
  → Dispara fee_snapshot e opportunity_scan para o usuário afetado
  → Elimina necessidade de polling diário para usuários ativos
```

---

## 6. RESUMO: O QUE MUDA E EM QUAL ORDEM

### Mudanças que desbloqueiam mais coisas (fazer primeiro)

| # | O que muda | Arquivo(s) | Desbloqueia |
|---|-----------|------------|-------------|
| 1 | Criar scheduler APScheduler | `core/scheduler.py` + `main.py` | D2, D4, R1.c, OPP, V2 |
| 2 | Migration: 8 tabelas novas | Alembic `versions/` | D1–D4, R2.b, R1.c, OPP |
| 3 | Novo conector BACEN crédito | `connectors/bacen_credit.py` | D3 (juros abusivos reais) |
| 4 | Persistir F5 em `bank_fee_history` | `costs/bank_fee_analyzer.py` | D1, D2, D4 |
| 5 | `NotificationEngine` desacoplado | `notifications/engine.py` | D4, R1.c, R1.d |

### Mudanças em módulos existentes

| Módulo | O que muda | Para quê |
|--------|-----------|----------|
| `costs/` | Persistir snapshot + `detect_new_fees()` | D1, D2, D4 |
| `negotiator/` | Trocar hardcode por BacenCreditConnector | D3 |
| `notifications/` | Novo tipo `TARIFA_AUMENTO` + desacoplar de HTTP | D4, R1.c |
| `health_score/` | Badge service + hook no cálculo | R2.b |
| `agent/` | +6 tools novas | OPP, T3, V2, D1–D3 |
| `fiscal/` | Novo `IRPFCalculator` para PF | T1, T2 |
| `main.py` | Registrar scheduler no lifespan | todos os jobs |
| `router.py` | Registrar routers dos 5 novos módulos | OPP, defense, rights, tax, viral |
| `config.py` | SMTP/SendGrid, SVR_BACEN_BASE_URL | R1.c, T3 |

### Novos módulos a criar do zero

| Módulo | Features | Complexidade |
|--------|----------|-------------|
| `opportunities/` | OPP — dinheiro parado + comparação bancos | Média |
| `defense/` | D1–D5 — defesa do consumidor | Alta |
| `rights/` | T3 — direitos esquecidos | Média |
| `tax/` | T1/T2 — IR optimizer | Alta |
| `viral/` | V1/V2 — wrapped + placar compartilhável | Média |
| `jobs/` | Todos os jobs do scheduler | Baixa |

---

## 7. BASES EXISTENTES A REUTILIZAR

Módulos existentes que podem ser reutilizados. “Reutilizar” não significa que estejam completos para todos os
cenários do roadmap; cada integração nova ainda exige contrato, testes e critérios de aceite.

- `backend/app/forecast/` — ETL, cashflow, safe-to-spend: completo
- `backend/app/architect/` — simulador de financiamento/consórcio: completo
- `backend/app/optimizer/` — otimizador de cartões: completo
- `backend/app/divider/` — classificador PF/PJ: completo
- `backend/app/purchase/` — F7 modo compra: completo
- `backend/app/budget/` — orçamento 50/30/20: completo
- `backend/app/subscriptions/` — detector de assinaturas: completo
- `backend/app/goals/` — metas financeiras: completo
- `backend/app/peers/` — comparação com pares: completo
- `backend/app/core/security.py` — JWT auth: completo
- `backend/app/core/cache.py` — Redis cache: completo
- `backend/app/architect/connectors/` — BACEN/ANBIMA/IPCA: completo
- `frontend-react/` — frontend funcional com 7 páginas, autenticação e integrações de API; a visão de 2 páginas
  é um redesign futuro e precisa de plano de migração, não de descarte automático

---

## 8. Checklist de Verificação (auditoria 2026-06-24)

Itens conferidos diretamente no código e confirmados como **corretos sem alteração** (além das correções já
marcadas com "↳ verificado" nas seções acima):

| Item | Confirmado |
|------|-----------|
| Scheduler de jobs (§1.1) | Não existe nada — nem `core/scheduler.py`, nem `app/jobs/`, nem APScheduler/Celery no projeto |
| Sistema de envio (§1.2) | Não existe — `notifications/` tem só `notifier.py`, `router.py`, `state_store.py`, `relevance_filter.py`; nenhum `email_sender`/`push_sender`/`delivery_service` |
| As 8 tabelas novas (§2) | Nenhuma existe; migrations atuais (6 arquivos em `alembic/versions/`) cobrem `users`, `health_score_history`, `transactions_clean`, `context_overrides`, goals/architect/optimizer, `chat_messages`, feedback/calibration e (mais recente) `recommendation_feedback` — nenhuma delas é uma das 8 propostas aqui |
| `negotiation_history` não é persistido (§3.2) | Confirmado — `opportunity_detector.py` só retorna lista em memória |
| Notificações são só reativas (§3.3) | Confirmado — geradas só no `GET /notifications/{user_id}` |
| Health Score sem badges (§3.4) | Confirmado — `health_score/` só tem `models.py`/`router.py`, sem gamificação |
| Agent com 15 tools (§3.5) | Confirmado — 15 arquivos em `app/agent/tools/`, nomes batem com a lista do ROADMAP.md |
| Fiscal só MEI/PJ, sem IRPF (§3.6) | Confirmado — `fiscal/` só tem DAS/Simples Nacional, sem cálculo de IR sobre CDB/LCI/LCA |
| `opportunities/`, `defense/`, `rights/`, `tax/`, `viral/` (§4) | Nenhuma dessas pastas existe — 100% greenfield (corrige a seção "Arquivos Criados como Base Técnica" do ROADMAP.md, que afirmava o contrário) |
| Conectores BACEN existentes (§5.1) | 8 conectores em `architect/connectors/`: `bacen.py` (SELIC, séries 432/4390), `anbima.py` (CDI, série 12), `ipca.py` (série 433 + IBGE SIDRA), `market_rates.py` (CETs, séries 25497/25501/20722), `abac.py`, `consortium_rate_provider.py`, `real_estate.py`, `base.py`. Nenhum cobre as séries de rotativo/cheque especial (20714/20715/20706/25433) |
| Seção 7 "Bases existentes" | Os módulos listados existem e seus routers aplicáveis estão registrados. Nem todos possuem pasta `services/`, e “existente” não equivale a “completo”. O `optimizer/` ganhou `life_stage_detector.py`, `personal_baseline.py`, `trend_detector.py` e `opportunity_score.py` |
| Frontend | 7 páginas reais (`home`, `dashboard`, `goals`, `strategies`, `connections`, `chat`, `profile`) e 4 arquivos de teste frontend; não é apenas um frontend de teste |
| Testes | 1.757 testes coletados via `pytest --collect-only` (2026-06-24), mas a coleção termina com 3 erros; isso não deve ser descrito como suíte passando nem como cobertura comprovada |

---

## 9. Gaps Transversais Ainda Não Detalhados

1. **Fonte única de dependências:** `pyproject.toml` e `requirements.txt` divergem em versões e bibliotecas.
   Definir qual arquivo governa build, CI e produção antes de adicionar scheduler ou novos SDKs.
2. **Critérios de aceite:** cada feature deve declarar entrada, saída, regra de negócio, fallback, observabilidade,
   testes mínimos e definição de pronto.
3. **Segurança e LGPD:** documentar consentimento, minimização de CPF/dados bancários, retenção, exclusão,
   auditoria de acesso e proibição de armazenar credenciais GOV.BR.
4. **Operação:** definir retries, timeout, circuit breaker, idempotência, métricas, alertas e runbook para jobs e APIs.
5. **Frontend:** mapear as 7 páginas atuais para a futura experiência de Feed + Chat e preservar funções sem
   concentrar toda a complexidade em uma única tela.
