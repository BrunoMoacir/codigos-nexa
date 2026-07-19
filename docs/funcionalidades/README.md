# Funcionalidades da Nexa — Documentação Completa

> Auditada contra o código em **2026-07-18**. Cada arquivo segue o mesmo formato:
> **Em palavras simples** (para qualquer pessoa) · **O que faz** · **Como funciona
> (técnico)** · **O que NÃO faz** · **Gaps e limitações** — sem inflar nada:
> o que está parcial ou pendente está escrito como parcial ou pendente.

## Mapa

| # | Arquivo | O que cobre |
|---|---------|-------------|
| 01 | [Open Finance e ETL](01-open-finance-e-etl.md) | Conexão bancária (Pluggy), webhook assinado, pipeline de 8 estágios, **proteções contra dados ruins** (dedup, data quality, shadow invoices) |
| 02 | [Cashflow e Safe-to-Spend](02-cashflow-e-safe-to-spend.md) | F1 — projeção 30 dias, margem segura do dia, burn rate, alertas, widget PWA |
| 03 | [Otimizador de Cartões](03-otimizador-de-cartoes.md) | F2 — 81 cartões, ranking por perfil, multi-cartão, valoração de milhas, elegibilidade |
| 04 | [Architect (Simulações)](04-architect-simulacoes.md) | F3 — financiamento vs consórcio vs investir, VPL, Monte Carlo, sensibilidade |
| 05 | [Classificador PF/PJ](05-classificador-pf-pj.md) | F4 — Random Forest + regras para MEI separar gastos pessoais e da empresa |
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
- Status de teste: a suíte completa (2.285+ testes) é mantida 100% verde como política.
