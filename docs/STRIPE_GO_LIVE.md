# Go-live da cobrança (Stripe)

Este é o roteiro para ligar a cobrança de Pro (R$ 19,90) e Total (R$ 39,90) e
depois o **enforcement** dos limites. O código está pronto e testado em
`backend/tests/billing/test_go_live.py`. O que falta é a conta Stripe, as
variáveis de ambiente e uma assinatura de teste de ponta a ponta.

> **Regra de ouro:** só ligue `BILLING_ENFORCEMENT_ENABLED=true` **depois** de
> uma assinatura de teste ter passado pelo fluxo inteiro (passo 4). Mesmo se a
> flag for ligada antes, o backend não bloqueia ninguém enquanto faltar
> `STRIPE_SECRET_KEY` ou `STRIPE_WEBHOOK_SECRET`. Nesse caso ele loga um erro,
> porque bloquear sem um caminho para pagar seria pior do que não cobrar.

---

## 1. Preparar a conta (modo teste)

```bash
cd backend
export STRIPE_SECRET_KEY=sk_test_...     # do ambiente — nunca como argumento
python3 -m scripts.stripe_setup --dry-run
python3 -m scripts.stripe_setup --webhook-url https://api.seu-dominio.com.br/api/v1/billing/webhook
```

O script é idempotente e cria, ou reaproveita:

| Recurso | Detalhe |
|:---|:---|
| Produtos | `hive_pro` e `hive_total` |
| Prices | Mensais em BRL, com lookup_key `hive_pro_mensal` / `hive_total_mensal`. O valor vem de `app/billing/plans.py`. Se o valor mudar, o script cria um price novo e transfere o lookup_key, e quem já assina continua no preço antigo |
| Portal do cliente | Troca Pro↔Total com proporcionalidade, cancelamento no fim do período, troca de cartão, faturas |
| Webhook | Versão de API **fixada** (`STRIPE_API_VERSION`, 2024-06-20) e só os eventos que o backend trata |

Ele recusa uma chave `sk_live_` sem `--live` e uma URL de webhook que não seja
https ou não termine em `/billing/webhook`.

**O segredo do webhook (`whsec_…`) só aparece na criação do endpoint.** Guarde
direto no gerenciador de segredos do deploy, nunca em chat, ticket ou commit.

## 2. Variáveis de ambiente (Railway → Variables)

| Variável | Valor | Segredo? |
|:---|:---|:---:|
| `STRIPE_SECRET_KEY` | `sk_test_…` (depois `sk_live_…`). No deploy, prefira uma **restricted key** (`rk_…`) só com o que o backend usa: escrita em Checkout Sessions e Customer Portal; leitura de Subscriptions, Prices, Customers e Invoices. O `stripe_setup.py` precisa de mais (Products, Prices, Webhook Endpoints, Portal Configurations): rode-o com a chave secreta completa **na sua máquina**, não no servidor. Teste a restricted key em modo teste: permissão faltando aparece como 403 do Stripe no log | ✅ |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…` impresso pelo script | ✅ |
| `STRIPE_PORTAL_CONFIGURATION` | `bpc_…` impresso pelo script | — |
| `STRIPE_API_VERSION` | `2024-06-20` (padrão; não mude sem rodar `tests/billing`) | — |
| `STRIPE_PRICE_PRO_MONTHLY` / `STRIPE_PRICE_TOTAL_MONTHLY` | Opcionais. Vazios, o backend resolve pelos lookup_keys | — |
| `FRONTEND_BASE_URL` | URL do site (retorno do Checkout e do portal) | — |
| `BILLING_ENFORCEMENT_ENABLED` | `false` até o passo 5 | — |

Com a chave e o segredo preenchidos, `GET /billing/subscription/{id}` passa a
responder `billing_enabled: true`, e os botões de `/planos` são habilitados.

## 3. Como o backend trata o Stripe (para depurar)

- **O webhook é só um aviso.** Para cada evento tratado, o backend **busca a
  assinatura no Stripe** e grava o estado dela. Por isso evento fora de ordem,
  repetido ou de uma versão de API diferente não corrompe o plano.
- **Eventos tratados:**
  - `checkout.session.completed`, `checkout.session.async_payment_succeeded` e
    `checkout.session.async_payment_failed`;
  - `customer.subscription.created` / `updated` / `deleted` / `paused` /
    `resumed`;
  - `invoice.paid`, `invoice.payment_succeeded` e `invoice.payment_failed`.

  Qualquer outro recebe 200 e é ignorado.
- **Deduplicação:** cada `event.id` é gravado em `billing_webhook_events`. A
  reentrega responde 200 sem reprocessar.
- **Falhas:**
  - uma falha **nossa** (Stripe fora, banco fora) responde 500, e o Stripe tenta
    de novo;
  - uma assinatura sem dono identificável é ignorada com log `unknown_owner`;
  - um conflito de dono (metadata diz A, registro diz B) **não** muda nada.
- **Boleto:** `incomplete` = Free até o pagamento compensar.
  `async_payment_succeeded` libera o plano.
- **Inadimplência:** `past_due` mantém o plano por até **7 dias** depois do fim
  do período pago. Depois disso, o usuário volta para o Free mesmo se o
  cancelamento nunca chegar.
- **Volta do Checkout:** `/planos?checkout=success&session_id=cs_…` chama
  `POST /billing/checkout/{id}/confirm`, que lê a sessão no Stripe e libera o
  plano **na hora**, sem esperar o webhook. Uma sessão de outra conta responde
  403.
- **Assinatura dupla:** quem já tem plano pago recebe **409** no checkout, e o
  app abre o portal. Trocar de plano é sempre pelo portal, para não gerar
  duas cobranças mensais.
- **Idempotência:** o checkout manda `Idempotency-Key` por usuário + plano numa
  janela de 10 minutos. Clique duplo não cria duas sessões.

## 4. Teste de ponta a ponta (modo teste)

Use os [cartões de teste](https://docs.stripe.com/testing):

| Cenário | Como | Esperado |
|:---|:---|:---|
| Assinar Pro | Cartão `4242 4242 4242 4242` | Volta para `/planos` com "seu plano Pro já está ativo"; `user_subscriptions.plan = pro` |
| Trocar para Total | Botão "Trocar para Total" | Abre o portal; após a troca, o webhook `customer.subscription.updated` grava `total` |
| Cartão recusado | `4000 0000 0000 0341` (recusa na renovação) | `past_due`; o plano continua por 7 dias depois do fim do período |
| Cancelar | Portal → Cancelar | `cancel_at_period_end = true`; no fim do período, volta para o Free |
| Reentrega | Dashboard → Webhooks → Reenviar evento | 200, sem efeito duplicado |
| Segundo checkout | `POST /billing/checkout/{id}` já assinando | 409 `already_subscribed` |

Para testar localmente: `stripe listen --forward-to localhost:8000/api/v1/billing/webhook`.
O `whsec_` que o CLI imprime vale só para essa sessão local.

## 5. Ligar o enforcement

```bash
BILLING_ENFORCEMENT_ENABLED=true
```

O que passa a ser bloqueado (402 com o plano necessário e uma mensagem de
upgrade):

| Recurso | Plano mínimo |
|:---|:---|
| Radar de Oportunidades, Raio-X de custos, Negociador | Pro |
| Defesa do Consumidor, portabilidade, otimizador de IR | Total |
| Free: 5 mensagens de IA/dia, 3 Compra Inteligente/mês, **1 banco conectado** | — |
| Pro: 1 roteiro do Negociador/mês | — |

- As janelas "dia" e "mês" seguem o calendário de **São Paulo**, não o UTC.
- O limite de bancos conta as conexões reais (`pluggy_items`).
- O **agente de IA** respeita os mesmos gates: uma ferramenta de um plano acima
  responde "RECURSO DO PLANO X", e o agente explica o upgrade em vez de
  entregar o recurso pelo chat.

Antes de ligar, rode `grep would_block` nos logs do dark launch: é a prévia
exata de quem seria bloqueado e em quê.

## 6. Produção (`sk_live_`)

1. Ative a conta Stripe (dados da empresa, conta bancária, **Pix/boleto** se
   for oferecer).
2. Rode `python3 -m scripts.stripe_setup --live --webhook-url https://…` com
   a chave live.
3. Troque as variáveis do passo 2 pelos valores live.
4. Faça uma assinatura real de R$ 19,90 e cancele.
5. Ligue o enforcement.

## 7. App nativo

O app Android/iOS **não vende** assinatura. As lojas exigem a compra delas
para bens digitais. No app, `/planos` mostra o plano e os limites e manda
assinar pelo site. Vender dentro do app exigiria Google Play Billing /
StoreKit, com comissão de 15–30% e outra reconciliação. Essa é uma decisão de
produto e está fora deste roteiro. Ver [APP_NATIVO.md](APP_NATIVO.md).
