# Funcionalidades da Nexa — Documentação Completa

> Auditada contra o código em **2026-08-09**. Cada arquivo segue o mesmo formato:
> **Em palavras simples** (para qualquer pessoa) · **Como é calculado** (fórmulas,
> constantes e thresholds reais extraídos do código) · **Como funciona (técnico)** ·
> **O que NÃO faz** · **Gaps e limitações** — sem inflar nada: o que está parcial
> ou pendente está escrito como parcial ou pendente.
>
> A seção **Como é calculado** traz as fórmulas exatas, os valores das constantes e
> a ordem de precedência das regras, com o *porquê* das decisões quando o código o
> documenta. Onde a implementação diverge do que se esperaria, isso está marcado
> explicitamente (ver, em especial, o doc 05).

## Mapa

| # | Arquivo | O que cobre |
|---|---------|-------------|
| 01 | [Open Finance e ETL](01-open-finance-e-etl.md) | Conexão bancária (Pluggy), webhook assinado, pipeline de 8 estágios, **proteções contra dados ruins** (dedup, data quality, shadow invoices) |
| 02 | [Cashflow e Safe-to-Spend](02-cashflow-e-safe-to-spend.md) | F1 — projeção 30 dias, margem segura do dia, burn rate, alertas, widget PWA |
| 03 | [Otimizador de Cartões](03-otimizador-de-cartoes.md) | F2 — 81 cartões, ranking por perfil, multi-cartão, valoração de milhas, elegibilidade |
| 04 | [Architect (Simulações)](04-architect-simulacoes.md) | F3 — financiamento vs consórcio vs investir, VPL, Monte Carlo, sensibilidade |
| 05 | [Classificador PF/PJ](05-classificador-pf-pj.md) | F4 — regras determinísticas para MEI separar gastos pessoais e da empresa (⚠️ o Random Forest treinado **não** está no caminho de inferência) |
| 06 | [Raio-X de Custos](06-raio-x-de-custos.md) | F5 — detecção de tarifas, benchmark de mercado, histórico por banco |
| 07 | [Compra Inteligente](07-compra-inteligente.md) | F7/R1.a — Pix vs débito vs crédito vs parcelado; checkout-context; revisão retroativa |
| 08 | [Negociador](08-negociador.md) | F13 — detecção de oportunidades + roteiros de negociação gerados por IA |
| 09 | [Radar de Oportunidades](09-radar-de-oportunidades.md) | OPP — dinheiro parado, catálogo vivo Open Finance, ranking líquido pós-IR, Bank Match |
| 10 | [Defesa do Consumidor](10-defesa-do-consumidor.md) | D1–D6 — venda casada, cobranças indevidas, juros abusivos, dossiê PROCON/JEC |
| 11 | [Direitos Esquecidos](11-direitos-esquecidos.md) | T3 — consulta REAL do SVR (assistida) e restituição IRPF (SERPRO), FGTS/PIS guiados |
| 12 | [Impostos e Calendário Fiscal](12-impostos-e-calendario-fiscal.md) | T1/T2/R2.c — otimizador de IR, imposto zero, sazonalidade, relatório MEI |
| 13 | [Inteligência Comportamental](13-inteligencia-comportamental.md) | 8 clusters, eventos de vida, perfil de renda, FSS, filtro de relevância |
| 14 | [Engajamento e Retenção](14-engajamento-e-retencao.md) | Health score, metas, desafios/badges, peers, orçamento 50/30/20, notificações, digest, Wrapped |
| 15 | [Agente de IA](15-agente-de-ia.md) | LangGraph ReAct, 31 ferramentas, memória Redis, mitigação de prompt injection |
| 16 | [Billing e Planos](16-billing-e-planos.md) | Free/Pro/Total, Stripe, gating em dark launch, limites de uso |
| 17 | [Segurança, Conta e LGPD](17-seguranca-conta-lgpd.md) | Auth, reset de senha, verificação de e-mail, IDOR, headers, export/erase LGPD, audit |
| 18 | [Infraestrutura e Plataforma](18-infraestrutura-e-plataforma.md) | Scheduler/jobs, cache, A/B testing, explicabilidade, stack, testes, deploy |

## Convenções

- **Caminhos** são relativos a `backend/` (ex.: `app/forecast/etl/runner.py`).
- **Endpoints** têm prefixo `/api/v1` omitido nas tabelas.
- "**Gap**" = limitação conhecida e assumida; não é bug escondido.
- **Constantes e fórmulas** citadas são as do código no momento da auditoria;
  o nome da constante é dado (ex.: `_WAIVER_ACHIEVABILITY_GATE = 0.80`) para que
  a verificação seja direta.
- Status de teste: a suíte completa (**2.489 testes coletados**) é mantida 100%
  verde como política.

## Onde encontrar as fórmulas principais

| Pergunta | Doc |
|---|---|
| Como o safe-to-spend é calculado? | [02](02-cashflow-e-safe-to-spend.md#como-é-calculado) — `min(saldo projetado) − max(15% das obrigações, R$ 200)` |
| Como um cartão é ranqueado? | [03](03-otimizador-de-cartoes.md#8-ranking--o-score-final) — 8 etapas, do ganho líquido às penalidades de elegibilidade |
| Como financiamento vs consórcio vs investir são comparados? | [04](04-architect-simulacoes.md) — VPL + VAR(1) macro + dominância estocástica de 2ª ordem |
| Como o IR regressivo entra no ranking de investimentos? | [09](09-radar-de-oportunidades.md#3-ir-regressivo-real-fiscalir_pf_calculatorpy) e [12](12-impostos-e-calendario-fiscal.md) |
| Como o "indício" de juros abusivos é medido? | [10](10-defesa-do-consumidor.md#d3--juros-abusivos-abusive_interest_detectorpy) — múltiplo da taxa de mercado (3,0× / 1,5× / 1,0×) |
| Como o cluster comportamental é decidido? | [13](13-inteligencia-comportamental.md#2-os-8-clusters--scores-por-regra) — scores por regra + ML destilado com 2 guardrails |
| Como o health score é composto? | [14](14-engajamento-e-retencao.md#mx1--health-score-e-resilience-score-etlprofilespy) — 3 fatores (legado) vs 6 fatores (resilience) |
