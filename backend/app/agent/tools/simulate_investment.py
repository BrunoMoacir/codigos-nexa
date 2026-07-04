# app/agent/tools/simulate_investment.py
"""
Tool do agente ReAct (chat) para simulação ad hoc de investimento (OPP.3).

Responde "se eu investir R$ X por Y meses, o que rende mais?" — comparando
Tesouro SELIC, CDB/LCI/LCA do catálogo e a poupança oficial, tudo em
rendimento LÍQUIDO (IR regressivo + custódia B3 no Tesouro).

Delega a TreasuryComparatorService e BankComparator — os mesmos motores dos
endpoints GET /opportunities/treasury-vs-cdb-vs-savings e POST /compare.
Nenhum cálculo duplicado aqui (mesma regra do Ticket OPP1-A para a tool de
radar).
"""
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Singleton de módulo — o cache do BaseConnector é por instância; recriar o
# serviço a cada chamada da tool anularia o TTL das taxas.
_treasury_service = None


def _get_treasury_service():
    global _treasury_service
    if _treasury_service is None:
        from app.opportunities.services.treasury_comparator import TreasuryComparatorService
        _treasury_service = TreasuryComparatorService()
    return _treasury_service


@tool
def simulate_investment(amount: float, holding_months: int = 12) -> str:
    """
    Simula quanto rende um valor em Tesouro SELIC vs. CDB vs. LCI/LCA vs. poupança.

    Use esta ferramenta SEMPRE que o usuário perguntar coisas como:
    - "Se eu investir R$ 20.000 por 2 anos, o que rende mais?"
    - "Tesouro Selic ou CDB, qual vale mais a pena?"
    - "Quanto rende R$ 10 mil na poupança vs CDB?"
    - "Onde coloco minha reserva de emergência?"
    - Qualquer simulação de valor/prazo específico de renda fixa.

    Para detectar dinheiro parado do usuário, use get_opportunities em vez desta.

    Args:
        amount: Valor a investir em reais (obrigatório, > 0).
        holding_months: Prazo em meses (padrão 12; afeta a alíquota de IR).
    """
    logger.info("[Tool] simulate_investment | amount=%s months=%s", amount, holding_months)

    if amount <= 0:
        return "Informe um valor maior que zero para simular."
    holding_months = max(1, min(int(holding_months), 360))

    try:
        result = _get_treasury_service().compare(amount=amount, holding_months=holding_months)
    except Exception as exc:
        logger.error("[Tool] simulate_investment: %s", exc)
        return "Não consegui simular agora. Tente novamente em instantes."

    lines = [
        f"=== SIMULAÇÃO: R$ {amount:,.2f} por {holding_months} meses ===",
        f"Taxas de hoje — SELIC: {result.selic_annual_pct:.2f}% | CDI: {result.cdi_annual_pct:.2f}% | Poupança: {result.savings_annual_pct:.2f}% a.a.",
        "",
        "── Rendimento líquido no período (após IR e custos) ──",
    ]

    for i, entry in enumerate(result.entries, start=1):
        ir_label = "isento de IR" if entry.is_exempt else f"IR {entry.ir_rate * 100:.1f}%"
        guarantee = "FGC" if entry.fgc_covered else "Tesouro Nacional"
        lines.append(
            f"{i}. {entry.label}: R$ {entry.net_yield_brl:,.2f} "
            f"({entry.annual_rate_net_pct:.2f}% a.a. líquido) — {ir_label}, garantia {guarantee}"
        )

    lines += ["", result.recommendation]

    from app.opportunities.models import DISCLAIMER
    lines += ["", DISCLAIMER]

    return "\n".join(lines)
