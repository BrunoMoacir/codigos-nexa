# 16 — Billing e Planos (Stripe)

> A máquina de receita: Free/Pro/Total, checkout Stripe, e o "gating" que
> decide o que cada plano pode usar — com um interruptor para ligar a cobrança
> sem quebrar nada.

## Em palavras simples

A Nexa cobra do usuário, não do banco — é o que garante a neutralidade. Este
módulo implementa isso: o plano gratuito mostra o valor (e tem limites), o
Pro (R$ 19,90) libera o dia a dia, o Total (R$ 39,90) libera a defesa do
consumidor completa. A cobrança é pelo Stripe (checkout hospedado — cartão
nunca passa pela Nexa). E tem um detalhe importante: o bloqueio nasce
DESLIGADO ("dark launch") — o sistema registra o que TERIA bloqueado, para
medirmos o impacto antes de cobrar de verdade.

## Os planos (`app/billing/plans.py`)

| Plano | Preço | O que libera | Limites |
|---|---|---|---|
| **Free** | R$ 0 | 1 banco, dashboard, safe-to-spend, SVR assistido | 5 msgs IA/dia · 3 Compra Inteligente/mês · Negociador: 0 |
| **Pro** | R$ 19,90/mês | + bancos ilimitados, Raio-X, Radar OPP, chat ilimitado, digest, desafios | Negociador: 1/mês |
| **Total** | R$ 39,90/mês | + Defesa completa (dossiê), portabilidade, otimizador IR, Wrapped trimestral | sem limites |

Gates aplicados no código: Defesa (4 endpoints) e `/tax/optimize` → Total;
Radar (3 endpoints) e Raio-X → Pro; contadores no chat, purchase e negociador.

## Como funciona (técnico)

- **Cliente Stripe** (`stripe_client.py`): REST puro via httpx (sem SDK — 
  mantém o `pip-audit` enxuto). Checkout Session em modo assinatura
  (`client_reference_id` = user_id), Billing Portal (trocar cartão/plano,
  cancelar), retrieve de subscription. **Webhook verificado** com o esquema
  oficial `Stripe-Signature` (HMAC-SHA256, comparação em tempo constante,
  tolerância anti-replay 5min); produção sem segredo → 503 fail-closed.
- **Ciclo de vida** (`service.py` + tabela `user_subscriptions`): eventos
  `checkout.session.completed` (ativa), `customer.subscription.updated`
  (sincroniza), `.deleted` (volta a free), `invoice.payment_failed`
  (past_due). **Idempotente por event id** (retries do Stripe não duplicam).
  `past_due` mantém o acesso durante as retries do Stripe — não cortamos
  usuário por cartão recusado transitório.
- **Gating** (`gating.py`): `require_plan("pro"|"total")` como dependency
  (embute `require_owner` — a proteção IDOR continua) devolve **402 Payment
  Required** com plano necessário, preço e endpoint de checkout; contadores
  de uso via Redis INCR+TTL com fallback em memória (janela diária expira à
  meia-noite UTC; mensal no dia 1º).
- **Dark launch**: `BILLING_ENFORCEMENT_ENABLED=false` (default) → nada
  bloqueia, tudo loga `would_block` (mede-se a receita na mesa); `true` →
  bloqueios ativos.
- **Endpoints**: `GET /billing/plans` (público), `GET
  /billing/subscription/{user_id}` (plano efetivo + uso dos contadores),
  `POST /billing/checkout/{user_id}`, `POST /billing/portal/{user_id}`,
  `POST /billing/webhook`.

## O que NÃO faz

- **Não guarda dados de cartão** — o checkout é hospedado no Stripe (PCI é
  problema deles).
- **Não tem Pix Automático ainda** — Stripe BR cobre cartão; Pix recorrente
  (menos churn involuntário, 60M sem cartão) é o próximo meio a integrar.
- **Não faz trial com cartão** — Free é o funil; trial pago é decisão futura.
- **Não pró-rateia upgrades manualmente** — troca de plano é feita no Portal
  do Stripe (que pró-rateia sozinho).

## Gaps e limitações

- **Falta para cobrar de verdade** (externo ao código): criar a conta/Products
  no dashboard Stripe, preencher `STRIPE_SECRET_KEY`, price IDs e `whsec_` no
  `.env`, apontar o webhook e ligar a flag.
- R5 anti-churn (tela de cancelamento com impacto calculado, modo pausa,
  win-back) ainda não existe — o Portal cobre o cancelamento cru.
- Nota fiscal de serviço (NFS-e) não é emitida — obrigação a resolver quando
  houver receita (gateway de NF ou emissão manual no começo).
