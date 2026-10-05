# app/agent/tools/get_purchase_recommendation.py
import logging
from typing import Optional

from app.agent.procedencia import com_procedencia, degradada
from langchain_core.tools import tool

from app.purchase.models import PurchaseRequest
from app.purchase.purchase_advisor import PurchaseAdvisor
from app.core.formatacao import brl

logger = logging.getLogger(__name__)


@tool
def get_purchase_recommendation(
    user_id: str,
    amount: float,
    category: str,
    installments: int = 1,
    monthly_income: Optional[float] = None,
    cash_price: Optional[float] = None,
    installments_total: Optional[float] = None,
) -> str:
    """
    Analisa uma compra e recomenda a melhor forma de pagamento comparando:
    PIX à vista, cartão à vista, cartão parcelado sem juros e crédito pessoal (CDC).

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Qual a melhor forma de pagar uma compra de R$ X?"
    - "Vale mais a pena parcelar ou pagar à vista?"
    - "Devo pagar no PIX ou no cartão?"
    - "Consigo pagar essa compra sem comprometer meu orçamento?"
    - Qualquer dúvida sobre método de pagamento antes de uma compra.

    Args:
        user_id: ID do usuário (obrigatório).
        amount: Valor da compra em reais (obrigatório). Ex: 3000.0
        category: Categoria da compra. Ex: "Eletrônicos", "Viagem", "Móveis".
        installments: Número de parcelas desejadas (padrão: 1 = à vista). Ex: 12
        monthly_income: Renda mensal do usuário (opcional, use se o usuário informar).
        cash_price: Preço à vista (Pix/dinheiro) quando a loja dá desconto.
            Use SEMPRE que o usuário mencionar desconto — "10% no Pix",
            "à vista sai por 2.700". Sem isso as duas modalidades são tratadas
            pelo mesmo preço e o Pix perde por construção.
        installments_total: Total do parcelado quando é MAIOR que `amount` —
            o "sem juros" que embute juro no preço. Ex.: "3.000 à vista ou
            12x de 280" → amount=3000, installments_total=3360.

    A resposta pode terminar com PERGUNTAS EM ABERTO. Elas trazem o ponto de
    virada já calculado ("a partir de 7,1% de desconto o Pix passa à frente").
    Faça-as ao usuário e, com a resposta, chame a ferramenta de novo passando
    `cash_price` ou `installments_total` — o veredito muda de verdade.
    """
    logger.info(
        "[Tool] get_purchase_recommendation | user=%s amount=%.2f category=%s installments=%d",
        user_id, amount, category, installments,
    )

    try:
        request = PurchaseRequest(
            user_id=user_id,
            amount=amount,
            category=category,
            installments=installments,
            monthly_income=monthly_income,
            cash_price=cash_price,
            installments_total=installments_total,
        )

        result = PurchaseAdvisor().analyze(request)

        # ── Formatar saída para o LLM ────────────────────────────────
        lines = [
            f"=== ANÁLISE DE COMPRA: {category} — {brl(amount)} ===",
            f"Recomendação: {result.recommended_label}",
            f"Custo líquido: {brl(result.recommended_net_cost)}",
            "",
            result.reasoning,
            "",
            "── Opções comparadas (melhor → pior) ──",
        ]

        for i, opt in enumerate(result.options, start=1):
            reward_str = f" | Reward: {brl(opt.reward_value)}" if opt.reward_value > 0 else ""
            installment_str = (
                f" | {opt.installments}x de {brl(opt.monthly_cost)}"
                if opt.monthly_cost and opt.installments and opt.installments > 1
                else ""
            )
            lines.append(
                f"{i}. {opt.label}"
                f" | Custo total: {brl(opt.total_cost)}"
                f"{reward_str}"
                f" | Custo líquido: {brl(opt.net_cost)}"
                f"{installment_str}"
            )
            if opt.notes:
                lines.append(f"   → {opt.notes}")

        lines += [
            "",
            "── Impacto no orçamento ──",
            f"Margem atual (safe-to-spend): {brl(result.liquidity_impact.safe_to_spend_before)}",
            f"Margem após a compra: {brl(result.liquidity_impact.safe_to_spend_after)}",
            f"Acessível: {'não calculado (sem margem segura)' if result.liquidity_impact.affordable is None else ('Sim' if result.liquidity_impact.affordable else 'Não ⚠️')}",
            f"Risco: {result.liquidity_impact.risk_level}",
        ]

        if result.warnings:
            lines += ["", "── Avisos ──"]
            for w in result.warnings:
                lines.append(f"- {w}")

        if result.follow_up_questions:
            lines += [
                "",
                "── O que eu não sei e mudaria a resposta ──",
                "(pergunte ao usuário; com a resposta, chame a ferramenta de novo)",
            ]
            for q in result.follow_up_questions:
                lines.append(f"[{q.priority}] {q.question}")
                if q.rationale:
                    lines.append(f"   → {q.rationale}")

        lines += [
            "",

        ]

        return com_procedencia(
            "\n".join(lines),
            fontes=result.data_sources or ["input_do_usuario"],
            confianca=result.confidence_score,
        )

    except ValueError as exc:
        return degradada(f"Não foi possível analisar a compra: {exc}", "entrada_invalida")
    except Exception as exc:
        logger.error("[Tool] get_purchase_recommendation erro: %s", exc, exc_info=True)
        return degradada(
            "Desculpe, ocorreu um erro interno ao analisar a compra. Tente novamente.",
            "excecao_no_advisor",
        )
