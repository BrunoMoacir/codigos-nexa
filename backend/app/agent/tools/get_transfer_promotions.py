# app/agent/tools/get_transfer_promotions.py
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def get_transfer_promotions(user_id: str) -> str:
    """Lista promoções ATIVAS de transferência bonificada de pontos/milhas
    (ex.: Livelo → Smiles com 100% de bônus) e estima o valor extra para o
    usuário. Use quando o usuário perguntar sobre milhas, pontos, transferir
    pontos, promoções de cartão ou 'vale a pena transferir agora?'."""
    logger.info("[Tool] get_transfer_promotions | user=%s", user_id)

    try:
        from app.optimizer.promotion_tracker import PromotionTracker

        tracker = PromotionTracker()
        active = tracker.get_active_promotions()
    except Exception as exc:
        logger.warning("[Tool] get_transfer_promotions falhou: %s", exc)
        return "Não consegui consultar as promoções de transferência no momento."

    if not active:
        return (
            "=== PROMOÇÕES DE TRANSFERÊNCIA (R4.b) ===\n"
            "Nenhuma promoção de transferência bonificada ativa e verificada no momento. "
            "Promoções de 80–110% aparecem várias vezes por ano (Livelo, Esfera, Smiles) — "
            "a Nexa avisa no feed assim que uma janela abrir."
        )

    lines = ["=== PROMOÇÕES DE TRANSFERÊNCIA ATIVAS (R4.b) ===", ""]
    for promo in active:
        lines += [
            f"── {promo.loyalty_program} → {promo.partner} ──",
            f"Bônus: +{promo.bonus_pct:.0f}% | válida até {promo.end_date.isoformat()} "
            f"({promo.days_remaining} dias restantes)",
            f"1.000 pontos: R$ {promo.normal_rate_per_1000:.2f} → "
            f"R$ {promo.effective_rate_per_1000:.2f} com o bônus",
            f"Mínimo: {promo.min_points:,} pontos"
            + (f" | máximo: {promo.max_points:,}" if promo.max_points else ""),
            f"{promo.description}",
            "",
        ]

    lines += [
        "⚠️ Confirme as condições no app do programa antes de transferir — promoções "
        "mudam sem aviso. Transferir sem plano de resgate próximo pode não valer a pena: "
        "pontos no programa aéreo expiram mais rápido que no banco.",
    ]
    return "\n".join(lines)
