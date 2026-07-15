# app/agent/tools/review_recent_purchases.py
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def review_recent_purchases(user_id: str) -> str:
    """
    Revisa as compras grandes dos últimos 14 dias e mostra quanto o usuário
    teria economizado pagando de outra forma (PIX vs. cartão com cashback
    vs. parcelado), usando o mesmo motor do Modo Compra (F7).

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Paguei certo nas minhas últimas compras?"
    - "Perdi dinheiro pagando com PIX/débito/cartão errado?"
    - "Revise minhas compras recentes"
    - "Quanto deixei de ganhar em cashback?"
    - Qualquer pedido de revisão retroativa de compras já feitas.

    Para analisar uma compra FUTURA, use get_purchase_recommendation.

    Args:
        user_id: ID do usuário (obrigatório).
    """
    logger.info("[Tool] review_recent_purchases | user=%s", user_id)

    try:
        from app.purchase.post_purchase import get_post_purchase_analyzer

        # sob demanda: ignora o marcador de "já analisada" do scheduler
        followups = get_post_purchase_analyzer().detect(user_id, use_seen_marker=False)
    except Exception as exc:
        logger.error("[Tool] review_recent_purchases erro: %s", exc)
        return f"Erro ao revisar compras recentes: {exc}"

    lines = ["=== REVISÃO DE COMPRAS RECENTES (F7 retroativo) ===", ""]

    if not followups:
        lines.append(
            "Nenhuma compra grande recente com forma de pagamento subótima "
            "detectada nos últimos 14 dias. Ou você pagou bem, ou não houve "
            "compras à vista acima de R$300 no período. 👏"
        )
        lines.append("")
        lines.append(
            "Dica: antes da próxima compra grande, pergunte aqui 'qual a melhor "
            "forma de pagar X reais em Y?' — o Modo Compra compara PIX, cartão "
            "e parcelado pelo custo líquido real."
        )
        return "\n".join(lines)

    total = 0.0
    for i, f in enumerate(followups, 1):
        total += f.potential_savings_brl
        lines += [
            f"── {i}. R$ {f.amount:,.2f} em {f.merchant.title()} ({f.purchase_date}) ──",
            f"Como pagou: {f.paid_method_label}",
            f"Melhor opção: {f.best_method_label}",
            f"Diferença: R$ {f.potential_savings_brl:,.2f} de custo líquido",
            "",
        ]

    lines += [
        f"Total deixado na mesa nessas compras: R$ {total:,.2f}.",
        "Não é bronca — a compra já foi. O valor está em criar o hábito: "
        "antes da próxima compra grande, consulte o Modo Compra.",
    ]
    return "\n".join(lines)
