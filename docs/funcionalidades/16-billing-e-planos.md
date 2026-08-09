# 16 — Billing e Planos (Stripe)

> A máquina de receita: Free/Pro/Total, checkout Stripe, e o "gating" que
> decide o que cada plano pode usar — com um interruptor para ligar a cobrança
> sem quebrar nada.

## Em palavras simples

A Nexa cobra do usuário, não do banco — é o que garante a neutralidade. Este
módulo implementa isso: o plano gratuito mostra o valor (e tem limites), o
Pro (R$ 19,90) libera o dia a dia, o Total (R$ 39,90) libera a defesa do
consumidor completa. A cobrança é pelo Stripe (checkout hospedado — cartão
nunca passa pela Nexa). E o bloqueio nasce **DESLIGADO** ("dark launch"): o
sistema registra o que TERIA bloqueado, para medirmos o impacto antes de
cobrar de verdade.

---

## Os planos (`app/billing/plans.py`)

| Plano | Preço | O que libera | Limites |
|---|---|---|---|
| **Free** | R$ 0 | 1 banco, dashboard, safe-to-spend, SVR assistido | 5 msgs IA/dia · 3 Compra Inteligente/mês · Negociador: 0 |
| **Pro** | R$ 19,90/mês | + bancos ilimitados, Raio-X, Radar OPP, chat ilimitado, digest, desafios | Negociador: 1/mês |
| **Total** | R$ 39,90/mês | + Defesa completa (dossiê), portabilidade, otimizador IR, Wrapped trimestral | sem limites |

**Hierarquia de tiers** (`plan_satisfies`):

```python
_TIER_ORDER = {"free": 0, "pro": 1, "total": 2}
plan_satisfies(user, required) = _TIER_ORDER[user] >= _TIER_ORDER[required]
```

`require_plan("pro")` → Pro **ou** Total. `require_plan("total")` → só Total.

**Contadores de uso** (`UsageLimit`: chave, limite, janela):

| Contador | Free | Pro | Janela |
|---|---|---|---|
| `chat_messages` | 5 | ilimitado | daily |
| `purchase_checks` | 3 | ilimitado | monthly |
| `connected_banks` | 1 | ilimitado | monthly |
| `negotiator_scripts` | **0** | **1** | monthly |

Detalhe de modelagem: `negotiator_scripts` aparece nos dois dicionários —
`FREE_LIMITS` com limite 0 ("disponível a partir do Pro") e `PRO_LIMITS` com
limite 1. Um limite de valor **zero** é como o produto expressa "bloqueado
neste plano" usando o mesmo mecanismo de contador, sem um caminho de código
especial.

---

## Como é calculado / aplicado

### Janelas dos contadores (`_window_bounds`)

O TTL é calculado para expirar exatamente na virada da janela, em **UTC**:

```python
daily:   suffix = "%Y%m%d"
         ttl    = segundos até 23:59:59 de hoje  (mínimo 60)

monthly: suffix = "%Y%m"
         ttl    = segundos até o dia 1º do mês seguinte às 00:00  (mínimo 60)
         (com tratamento de virada de ano: dezembro → janeiro do ano+1)
```

A chave do contador carrega o sufixo da janela, então a expiração e a troca de
chave são redundantes de propósito — mesmo que o TTL falhe, a chave nova é
outra.

Implementação: **Redis `INCR` + `EXPIRE`**, com **fallback em memória** se o
Redis estiver indisponível (o gating nunca derruba a requisição por falta de
cache).

### Dark launch

```python
def enforcement_enabled():
    return bool(settings.BILLING_ENFORCEMENT_ENABLED)   # default: False
```

Com a flag **desligada** (padrão), nada bloqueia — apenas loga:

```
[Gating] would_block user=X plan=free required=pro (enforcement off)
[Gating] would_block_usage user=X key=chat_messages used=6 limit=5 (enforcement off)
```

Isso permite **medir a receita na mesa** antes de ligar a cobrança. Com a flag
ligada, o mesmo caminho retorna **402 Payment Required** com o plano
necessário, o preço e o endpoint de checkout no corpo (`_upgrade_detail`) — o
frontend consegue montar a tela de upgrade direto da resposta.

`require_plan` é uma dependency FastAPI que **embute `require_owner`** — a
proteção IDOR (doc 17) continua valendo mesmo nos endpoints com gate de plano.

**Gates aplicados**: Defesa (4 endpoints) e `/tax/optimize` → Total; Radar
(3 endpoints) e Raio-X → Pro; contadores no chat, purchase e negociador.

### Verificação do webhook Stripe (`stripe_client.py`)

Implementa o esquema oficial **sem usar o SDK** (REST puro via httpx — mantém
o `pip-audit` enxuto):

```
header:  Stripe-Signature: t=<timestamp>,v1=<hmac>,...
hmac:    HMAC-SHA256(secret, f"{t}.{payload_bruto}")
```

Três verificações:

1. **Anti-replay**: `|agora − t| ≤ 300s` (5 min — o mesmo default do SDK
   oficial);
2. **Comparação em tempo constante**: `hmac.compare_digest` contra **todos** os
   candidatos `v1` do header (o Stripe pode enviar múltiplas assinaturas
   durante rotação de segredo);
3. **Fail-closed**: produção sem `whsec_` configurado → **503**, nunca aceita
   não-assinado.

O uso do **payload bruto** (bytes, antes de qualquer parse) é essencial —
re-serializar o JSON quebraria a assinatura.

### Ciclo de vida da assinatura (`service.py` + `user_subscriptions`)

| Evento Stripe | Ação |
|---|---|
| `checkout.session.completed` | ativa o plano (`client_reference_id` = user_id) |
| `customer.subscription.updated` | sincroniza status / plano / período |
| `customer.subscription.deleted` | volta para `free` |
| `invoice.payment_failed` | marca `past_due` — **acesso mantido** |

```python
_PAID_OK_STATUSES = {"active", "trialing", "past_due"}
```

**`past_due` conta como pago.** A decisão está comentada no código: é
"cortesia até o Stripe desistir das retries" — cartão recusado
transitoriamente não corta o acesso do usuário. Cortar imediatamente geraria
churn involuntário por um problema que costuma se resolver sozinho.

**Idempotência por `event_id`**: cada handler recebe o id do evento e a
gravação é idempotente — os retries automáticos do Stripe não duplicam
ativações.

---

## Endpoints

| Endpoint | Observação |
|---|---|
| `GET /billing/plans` | público |
| `GET /billing/subscription/{user_id}` | plano efetivo + `usage_snapshot()` dos contadores |
| `POST /billing/checkout/{user_id}` | Checkout Session em modo assinatura |
| `POST /billing/portal/{user_id}` | Billing Portal (trocar cartão/plano, cancelar) |
| `POST /billing/webhook` | verificado, fail-closed |

## O que NÃO faz

- **Não guarda dados de cartão** — o checkout é hospedado no Stripe (PCI é
  problema deles).
- **Não tem Pix Automático ainda** — Stripe BR cobre cartão; Pix recorrente
  (menos churn involuntário, 60M sem cartão) é o próximo meio a integrar.
- **Não faz trial com cartão** — Free é o funil; trial pago é decisão futura.
- **Não pró-rateia upgrades manualmente** — a troca de plano é feita no Portal
  do Stripe, que pró-rateia sozinho.

## Gaps e limitações

- **Falta para cobrar de verdade** (externo ao código): criar a conta/Products
  no dashboard Stripe, preencher `STRIPE_SECRET_KEY`, os price IDs e o
  `whsec_` no `.env`, apontar o webhook e ligar
  `BILLING_ENFORCEMENT_ENABLED`.
- **Janelas em UTC**: o contador diário do usuário brasileiro vira às 21h
  (horário de Brasília), não à meia-noite local. Para 5 mensagens/dia é
  irrelevante; para limites maiores seria confuso.
- **Fallback em memória dos contadores não é compartilhado entre instâncias** —
  com Redis fora do ar e múltiplos workers, o limite efetivo vira
  `limite × nº de workers`. Falha aberta e deliberada (não bloquear é melhor
  que errar bloqueando), mas é uma limitação real.
- **`past_due` mantém acesso indefinidamente** enquanto o Stripe não emitir
  `subscription.deleted` — não há timeout próprio.
- **R5 anti-churn** (tela de cancelamento com impacto calculado, modo pausa,
  win-back) ainda não existe — o Portal cobre o cancelamento cru.
- **Nota fiscal de serviço (NFS-e) não é emitida** — obrigação a resolver
  quando houver receita (gateway de NF ou emissão manual no começo).
