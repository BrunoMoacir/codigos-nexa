"""
scripts/stripe_setup.py — prepara a conta Stripe para cobrar Pro e Total.

Idempotente: pode rodar quantas vezes quiser, em teste ou produção. Cria (ou
reaproveita) exatamente o que o backend espera:

  1. Produtos `hive_pro` e `hive_total` (IDs fixos);
  2. Prices mensais em BRL com lookup_key `hive_pro_mensal` / `hive_total_mensal`
     (valores de app/billing/plans.py). Mudou o preço no plans.py? O script
     cria um price novo e transfere o lookup_key — quem já assina continua no
     preço antigo até migrar pelo portal;
  3. Configuração do portal do cliente (troca Pro↔Total, cancelamento no fim do
     período, troca de cartão, histórico de faturas);
  4. Endpoint de webhook (com --webhook-url), com a versão de API fixada e só
     os eventos que o backend trata.

Uso (a chave vem do AMBIENTE — nunca de argumento, que fica no histórico do shell):

    cd backend
    export STRIPE_SECRET_KEY=sk_test_...        # ou já no .env
    python3 -m scripts.stripe_setup --dry-run
    python3 -m scripts.stripe_setup --webhook-url https://api.seu-dominio/api/v1/billing/webhook

Chave de produção (sk_live_/rk_live_) exige --live.

No fim, imprime as variáveis para o ambiente de deploy. O segredo do webhook
só existe na criação do endpoint: é mostrado UMA vez — guarde direto no
gerenciador de segredos do deploy.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Callable
from urllib.parse import urlparse

from app.billing.plans import PLAN_PRO, PLAN_TOTAL, PLANS, PRICE_LOOKUP_KEYS, price_cents
from app.billing.service import EVENTOS_TRATADOS
from app.billing.stripe_client import StripeClient, StripeNaoEncontrado
from app.core.config import settings

PRODUTOS = {PLAN_PRO: "hive_pro", PLAN_TOTAL: "hive_total"}
MARCA_PORTAL = "hive_setup_v1"


class ErroDeConfiguracao(Exception):
    pass


def _modo_da_chave(chave: str) -> str:
    if chave.startswith(("sk_live_", "rk_live_")):
        return "live"
    if chave.startswith(("sk_test_", "rk_test_")):
        return "test"
    raise ErroDeConfiguracao("STRIPE_SECRET_KEY não parece uma chave do Stripe (sk_test_/sk_live_).")


def _validar_url_webhook(url: str) -> str:
    partes = urlparse(url)
    if partes.scheme != "https" or not partes.netloc:
        raise ErroDeConfiguracao("--webhook-url precisa ser https:// (o Stripe não entrega em http).")
    if not partes.path.rstrip("/").endswith("/billing/webhook"):
        raise ErroDeConfiguracao("--webhook-url deve apontar para …/api/v1/billing/webhook.")
    return url


def _garantir_produto(stripe: StripeClient, plano: str, dry_run: bool, log: Callable[[str], None]) -> str:
    produto_id = PRODUTOS[plano]
    try:
        stripe._request("GET", f"/products/{produto_id}")
        log(f"  produto {produto_id}: já existe")
        return produto_id
    except StripeNaoEncontrado:
        pass
    if dry_run:
        log(f"  produto {produto_id}: SERIA criado")
        return produto_id
    stripe._request("POST", "/products", {
        "id": produto_id,
        "name": f"HIVE {PLANS[plano].name}",
        "description": PLANS[plano].tagline,
        "metadata[hive_plan]": plano,
    }, idempotency_key=f"hive-produto-{produto_id}")
    log(f"  produto {produto_id}: criado")
    return produto_id


def _garantir_price(stripe: StripeClient, plano: str, produto_id: str, dry_run: bool,
                    log: Callable[[str], None]) -> str:
    lookup_key = PRICE_LOOKUP_KEYS[plano]
    esperado = price_cents(plano)
    atual = (stripe._request("GET", "/prices", params={
        "lookup_keys[]": lookup_key, "active": "true", "limit": 1,
    }).get("data") or [None])[0]

    if atual:
        recorrencia = (atual.get("recurring") or {}).get("interval")
        if atual.get("unit_amount") == esperado and atual.get("currency") == "brl" and recorrencia == "month":
            log(f"  price {lookup_key}: já existe ({atual['id']})")
            return str(atual["id"])
        log(f"  price {lookup_key}: valor diferente do plans.py ({atual.get('unit_amount')} ≠ {esperado})")

    if dry_run:
        log(f"  price {lookup_key}: SERIA criado (R$ {esperado / 100:.2f}/mês)")
        return atual["id"] if atual else f"(novo {lookup_key})"

    novo = stripe._request("POST", "/prices", {
        "product": produto_id,
        "currency": "brl",
        "unit_amount": esperado,
        "recurring[interval]": "month",
        "lookup_key": lookup_key,
        # move o lookup_key do price antigo para este; assinantes existentes
        # continuam no price deles
        "transfer_lookup_key": "true",
        "metadata[hive_plan]": plano,
    }, idempotency_key=f"hive-price-{lookup_key}-{esperado}")
    log(f"  price {lookup_key}: criado ({novo['id']})")
    return str(novo["id"])


def _garantir_portal(stripe: StripeClient, precos: dict[str, str], dry_run: bool,
                     log: Callable[[str], None]) -> str:
    dados: dict[str, Any] = {
        "business_profile[headline]": "HIVE — gerencie sua assinatura",
        "features[customer_update][enabled]": "true",
        "features[customer_update][allowed_updates][0]": "email",
        "features[invoice_history][enabled]": "true",
        "features[payment_method_update][enabled]": "true",
        "features[subscription_cancel][enabled]": "true",
        "features[subscription_cancel][mode]": "at_period_end",
        "features[subscription_cancel][cancellation_reason][enabled]": "true",
        "features[subscription_cancel][cancellation_reason][options][0]": "too_expensive",
        "features[subscription_cancel][cancellation_reason][options][1]": "missing_features",
        "features[subscription_cancel][cancellation_reason][options][2]": "unused",
        "features[subscription_cancel][cancellation_reason][options][3]": "other",
        "features[subscription_update][enabled]": "true",
        "features[subscription_update][default_allowed_updates][0]": "price",
        "features[subscription_update][proration_behavior]": "create_prorations",
        "metadata[hive]": MARCA_PORTAL,
    }
    for i, plano in enumerate((PLAN_PRO, PLAN_TOTAL)):
        dados[f"features[subscription_update][products][{i}][product]"] = PRODUTOS[plano]
        dados[f"features[subscription_update][products][{i}][prices][0]"] = precos[plano]

    existentes = stripe._request("GET", "/billing_portal/configurations", params={"limit": 100}).get("data") or []
    nossa = next((c for c in existentes if (c.get("metadata") or {}).get("hive") == MARCA_PORTAL), None)
    if dry_run:
        log("  portal: SERIA " + ("atualizado" if nossa else "criado"))
        return nossa["id"] if nossa else "(nova configuração)"
    if nossa:
        stripe._request("POST", f"/billing_portal/configurations/{nossa['id']}", dados)
        log(f"  portal: configuração atualizada ({nossa['id']})")
        return str(nossa["id"])
    nova = stripe._request("POST", "/billing_portal/configurations", dados,
                           idempotency_key=f"hive-portal-{MARCA_PORTAL}")
    log(f"  portal: configuração criada ({nova['id']})")
    return str(nova["id"])


def _garantir_webhook(stripe: StripeClient, url: str, dry_run: bool,
                      log: Callable[[str], None]) -> tuple[str, str | None]:
    eventos = sorted(EVENTOS_TRATADOS)
    existentes = stripe._request("GET", "/webhook_endpoints", params={"limit": 100}).get("data") or []
    atual = next((w for w in existentes if w.get("url") == url), None)
    dados: dict[str, Any] = {f"enabled_events[{i}]": e for i, e in enumerate(eventos)}
    if dry_run:
        log("  webhook: SERIA " + ("atualizado" if atual else "criado") + f" ({len(eventos)} eventos)")
        return (atual or {}).get("id", "(novo)"), None
    if atual:
        stripe._request("POST", f"/webhook_endpoints/{atual['id']}", dados)
        log(f"  webhook: já existia ({atual['id']}) — eventos atualizados. O segredo não é "
            "mostrado de novo: use o que você guardou (ou apague o endpoint no dashboard e rode outra vez).")
        return str(atual["id"]), None
    dados["url"] = url
    dados["api_version"] = getattr(settings, "STRIPE_API_VERSION", "") or "2024-06-20"
    dados["description"] = "HIVE — assinaturas (stripe_setup.py)"
    novo = stripe._request("POST", "/webhook_endpoints", dados, idempotency_key=f"hive-webhook-{url}")
    log(f"  webhook: criado ({novo['id']})")
    return str(novo["id"]), novo.get("secret")


def configurar(stripe: StripeClient, *, webhook_url: str | None, live: bool, dry_run: bool,
               log: Callable[[str], None] = print) -> dict[str, str]:
    """Executa a preparação e devolve as variáveis de ambiente resultantes."""
    chave = getattr(settings, "STRIPE_SECRET_KEY", "") or ""
    if not chave:
        raise ErroDeConfiguracao("Defina STRIPE_SECRET_KEY no ambiente (export ou backend/.env).")
    modo = _modo_da_chave(chave)
    if modo == "live" and not live:
        raise ErroDeConfiguracao("Chave de PRODUÇÃO detectada: rode de novo com --live se é isso mesmo.")
    if webhook_url:
        _validar_url_webhook(webhook_url)

    log(f"Stripe em modo {modo.upper()}{' (simulação — nada será criado)' if dry_run else ''}")
    precos: dict[str, str] = {}
    for plano in (PLAN_PRO, PLAN_TOTAL):
        produto = _garantir_produto(stripe, plano, dry_run, log)
        precos[plano] = _garantir_price(stripe, plano, produto, dry_run, log)
    portal = _garantir_portal(stripe, precos, dry_run, log)

    ambiente = {
        "STRIPE_PRICE_PRO_MONTHLY": precos[PLAN_PRO],
        "STRIPE_PRICE_TOTAL_MONTHLY": precos[PLAN_TOTAL],
        "STRIPE_PORTAL_CONFIGURATION": portal,
        "STRIPE_API_VERSION": getattr(settings, "STRIPE_API_VERSION", "") or "2024-06-20",
    }
    if webhook_url:
        _, segredo = _garantir_webhook(stripe, webhook_url, dry_run, log)
        if segredo:
            ambiente["STRIPE_WEBHOOK_SECRET"] = segredo
    return ambiente


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepara a conta Stripe para os planos Pro e Total.")
    parser.add_argument("--webhook-url", help="https://…/api/v1/billing/webhook (opcional)")
    parser.add_argument("--live", action="store_true", help="permite chave de produção (sk_live_)")
    parser.add_argument("--dry-run", action="store_true", help="só mostra o que faria")
    args = parser.parse_args(argv)
    try:
        ambiente = configurar(StripeClient(), webhook_url=args.webhook_url, live=args.live, dry_run=args.dry_run)
    except ErroDeConfiguracao as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print("\nVariáveis para o ambiente de deploy (Railway → Variables):")
    for nome, valor in ambiente.items():
        print(f"  {nome}={valor}")
    if "STRIPE_WEBHOOK_SECRET" in ambiente:
        print("\nATENÇÃO: o STRIPE_WEBHOOK_SECRET acima só aparece agora. Guarde-o no gerenciador de "
              "segredos e não cole em chat, ticket ou commit.")
    print("\nDepois de configurar e testar uma assinatura de ponta a ponta: BILLING_ENFORCEMENT_ENABLED=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
