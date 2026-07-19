# app/agent/tools/get_plan_info.py
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def get_plan_info(user_id: str) -> str:
    """Retorna o plano atual do usuário (Free/Pro/Total), o uso dos limites
    (mensagens de IA, consultas de compra, negociador) e o catálogo de planos
    com preços e benefícios. Use quando o usuário perguntar sobre plano,
    assinatura, preço, limites de uso, upgrade ou o que ganha assinando."""
    logger.info("[Tool] get_plan_info | user=%s", user_id)

    try:
        from app.billing.plans import PLANS
        from app.billing.service import BillingService
        from app.billing.gating import usage_snapshot

        record = BillingService().get_record_dict(user_id)
        usage = usage_snapshot(user_id)
    except Exception as exc:
        logger.warning("[Tool] get_plan_info falhou: %s", exc)
        return "Não consegui consultar as informações de plano no momento."

    plan_id = record["plan"]
    plan = PLANS.get(plan_id)
    lines = [
        "=== SEU PLANO NEXA ===",
        f"Plano atual: {plan.name if plan else plan_id}"
        + (f" — R$ {plan.price_brl_monthly:.2f}/mês".replace(".", ",") if plan and plan.price_brl_monthly else " (gratuito)"),
    ]
    if record.get("cancel_at_period_end"):
        lines.append("⚠️ Assinatura marcada para cancelar no fim do período atual.")
    if record.get("current_period_end"):
        lines.append(f"Período atual até: {record['current_period_end']:%d/%m/%Y}")

    if usage:
        lines += ["", "── Uso dos limites ──"]
        for u in usage:
            window = "hoje" if u["window"] == "daily" else "este mês"
            lines.append(f"{u['description']}: {u['used']}/{u['limit']} ({window})")

    lines += ["", "── Planos disponíveis ──"]
    for p in PLANS.values():
        price = f"R$ {p.price_brl_monthly:.2f}/mês".replace(".", ",") if p.price_brl_monthly else "grátis"
        marker = " ← seu plano" if p.plan_id == plan_id else ""
        lines.append(f"• {p.name} ({price}){marker} — {p.tagline}")
        for feat in p.features[:4]:
            lines.append(f"    - {feat}")

    lines += [
        "",
        "Para assinar ou trocar de plano, use a tela Planos do app "
        "(o checkout é seguro, via Stripe — a Nexa não vê os dados do cartão).",
    ]
    return "\n".join(lines)
