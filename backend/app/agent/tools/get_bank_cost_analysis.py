# app/agent/tools/get_bank_cost_analysis.py
import logging

from app.agent.procedencia import com_procedencia, degradada
from langchain_core.tools import tool

from app.costs.bank_fee_analyzer import BankFeeAnalyzer
from app.core.db.queries import get_transactions_for_user

logger = logging.getLogger(__name__)


@tool
def get_bank_cost_analysis(user_id: str) -> str:
    """
    Analisa quanto o usuário paga em tarifas bancárias e compara com o mercado.

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Quanto pago de tarifa / anuidade / taxa bancária?"
    - "Meu banco está me cobrando muito?"
    - "Quanto economizo trocando de banco?"
    - "Quais são meus custos bancários?"
    - "Vale a pena migrar para um banco digital?"
    - Qualquer pergunta sobre tarifas, taxas ou custos de conta bancária.

    Args:
        user_id: ID do usuário (obrigatório).
    """
    logger.info("[Tool] get_bank_cost_analysis | user=%s", user_id)

    transactions_df = get_transactions_for_user(user_id)

    if transactions_df.is_empty():
        return (
            "Não encontrei histórico de transações para analisar tarifas. "
            "Conecte sua conta bancária via Open Finance para obter essa análise."
        )

    try:
        report = BankFeeAnalyzer().analyze(transactions_df, user_id=user_id)
    except Exception as exc:
        logger.error("[Tool] get_bank_cost_analysis | erro: %s", exc, exc_info=True)
        return degradada(
            "Desculpe, ocorreu um erro interno ao analisar seus custos bancários.",
            "analise_falhou",
        )

    # ── Formatar saída para o LLM ────────────────────────────────
    lines = [
        f"=== RAIO-X DE CUSTOS BANCÁRIOS ===",
        f"Período analisado: {report.analysis_months} mês(es)",
        f"Total pago em tarifas: R$ {report.total_paid:,.2f}",
        f"Média mensal: R$ {report.monthly_avg:,.2f}",
        f"Projeção anual (CBT): R$ {report.annual_projection:,.2f}",
    ]

    if report.savings_opportunity > 0:
        lines.append(
            f"💡 Economia potencial: R$ {report.savings_opportunity:,.2f}/mês "
            f"(R$ {report.savings_opportunity * 12:,.2f}/ano)"
        )

    # Por banco
    if report.by_bank:
        lines += ["", "── Por banco ──"]
        for bank in report.by_bank:
            lines.append(
                f"• {bank.bank_name}: R$ {bank.monthly_avg:,.2f}/mês "
                f"({bank.transaction_count} cobrança(s) detectada(s))"
            )
            for fee_type, value in bank.fees_by_type.items():
                lines.append(f"  - {fee_type}: R$ {value:,.2f}")

    # Por tipo de tarifa
    if report.by_fee_type:
        lines += ["", "── Por tipo de tarifa ──"]
        for fee_type, value in report.by_fee_type.items():
            lines.append(f"• {fee_type}: R$ {value:,.2f}")

    # Benchmarks
    if report.market_benchmarks:
        lines += ["", "── Comparação com o mercado ──"]
        for bm in report.market_benchmarks:
            lines.append(
                f"• {bm.bank_name}: R$ {bm.monthly_avg_market:,.2f}/mês (média mercado)"
            )

    if report.warnings:
        lines += ["", "── Avisos ──"]
        for w in report.warnings:
            lines.append(f"- {w}")

    # A confiança e as fontes saíam como prosa, no meio de outras linhas de
    # prosa: o modelo não tinha como distinguir "R$ 0,00 medido" de "R$ 0,00
    # porque o detector não rodou". Agora vão na linha [NEXA], que o system
    # prompt sabe ler.
    return com_procedencia(
        "\n".join(lines),
        fontes=report.data_sources,
        confianca=report.confidence_score,
        cobertura_meses=report.analysis_months,
    )
