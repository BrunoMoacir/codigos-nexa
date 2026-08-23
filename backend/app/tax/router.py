"""
app/tax/router.py — T1/T2: Otimização de IR em Investimentos

GET  /api/v1/tax/optimize/{user_id}  — análise completa da carteira (T1 + T2)
POST /api/v1/tax/breakeven           — calculadora de breakeven CDB vs LCI (sem autenticação de owner)
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user, require_owner
from app.billing.gating import require_plan
from app.tax.models import (
    BreakevenRequest,
    BreakevenResponse,
    TaxAnalysisResponse,
)
from app.tax.services.investment_profiler import InvestmentProfiler
from app.tax.services.ir_calculator import calc_portfolio_ir, calc_breakeven
from app.tax.services.tax_loss_harvesting import TaxLossHarvester
from app.tax.services.zero_tax_mode import ZeroTaxMode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tax", tags=["Tax (T1/T2 — Otimização de IR)"])

_profiler = InvestmentProfiler()
_harvester = TaxLossHarvester()
_zero_tax = ZeroTaxMode()


@router.get("/optimize/{user_id}", response_model=TaxAnalysisResponse)
def get_tax_optimization(
    user_id: str = require_plan("total"),
) -> TaxAnalysisResponse:
    """
    **Otimização de IR na Carteira de Investimentos (T1 + T2)**

    Analisa os investimentos conectados via Pluggy e identifica:

    | Oportunidade | Tipo | Descrição |
    |-------------|------|-----------|
    | **harvest_loss** | T1 | Posição com perda que abate IR de outras posições |
    | **hold_longer** | T1 | Aguardar próximo bracket IR (ex: 22,5% → 20%) |
    | **switch_to_lci** | T2 | CDB tributado → LCI/LCA isenta com vantagem real |
    | **avoid_come_cotas** | T2 | Fundo RF/MM → CDB para diferir IR semestral |

    **Fonte de dados:** carteira Pluggy (Open Finance) do usuário.
    Requer que o usuário tenha pelo menos uma conexão bancária ativa.
    """
    portfolio = _profiler.get_portfolio(user_id)

    if not portfolio:
        return TaxAnalysisResponse(
            user_id=user_id,
            generated_at=datetime.now(timezone.utc),
            portfolio=[],
            total_invested=0.0,
            total_current_balance=0.0,
            total_unrealized_gain=0.0,
            total_estimated_ir_liability=0.0,
            opportunities=[],
            total_estimated_tax_saving=0.0,
            summary=(
                "Nenhuma carteira de investimentos encontrada via Pluggy. "
                "Conecte suas contas de investimento para receber análise fiscal personalizada."
            ),
            data_source="no_data",
        )

    # Busca CDI atual para análise de come-cotas
    cdi_annual = _get_cdi()

    total_invested = round(sum(p.amount for p in portfolio), 2)
    total_balance = round(sum(p.current_balance for p in portfolio), 2)
    total_gain = round(total_balance - total_invested, 2)
    total_ir = calc_portfolio_ir(portfolio)

    # T1 + T2
    opportunities = []
    try:
        opportunities.extend(_harvester.find_opportunities(portfolio))
    except Exception as exc:
        logger.error("[tax/optimize] harvester user=%s: %s", user_id, exc)
    try:
        opportunities.extend(_zero_tax.find_opportunities(portfolio, cdi_annual))
    except Exception as exc:
        logger.error("[tax/optimize] zero_tax user=%s: %s", user_id, exc)

    # Ordena por saving decrescente
    opportunities.sort(key=lambda o: o.estimated_tax_saving_brl, reverse=True)

    # Imposto que deixa de ser devido e imposto que só sai mais tarde não são
    # a mesma coisa. O come-cotas evitado volta no resgate: somar tudo num
    # "total de economia de imposto" superestima o benefício.
    total_saving = round(
        sum(o.estimated_tax_saving_brl for o in opportunities
            if o.benefit_kind == "tax_saving"), 2
    )
    total_deferral = round(
        sum(o.estimated_tax_saving_brl for o in opportunities
            if o.benefit_kind == "deferral"), 2
    )

    summary = _build_summary(portfolio, total_ir, opportunities, total_saving)

    logger.info(
        "[tax/optimize] user=%s positions=%d ir_liability=%.2f opportunities=%d "
        "saving=%.2f deferral=%.2f",
        user_id, len(portfolio), total_ir, len(opportunities), total_saving, total_deferral,
    )

    return TaxAnalysisResponse(
        user_id=user_id,
        generated_at=datetime.now(timezone.utc),
        portfolio=portfolio,
        total_invested=total_invested,
        total_current_balance=total_balance,
        total_unrealized_gain=total_gain,
        total_estimated_ir_liability=total_ir,
        opportunities=opportunities,
        total_estimated_tax_saving=total_saving,
        total_estimated_deferral_gain=total_deferral,
        summary=summary,
        data_source="pluggy",
    )


@router.post("/breakeven", response_model=BreakevenResponse)
def calc_breakeven_endpoint(
    body: BreakevenRequest,
    _: str = Depends(get_current_user),
) -> BreakevenResponse:
    """
    **Calculadora de Breakeven CDB vs LCI/LCA**

    Responde: "qual a taxa mínima de LCI que supera este CDB após IR?"

    - Alíquota IR regressiva (22,5% → 15%) determinada pelo prazo.
    - Fórmula: `lci_breakeven = cdb_rate × (1 − IR)`
    - Se informar `lci_offered_rate_pct`, calcula a vantagem da LCI sobre o breakeven.

    **Exemplo:** CDB 13,5% a.a., prazo 13 meses (IR 20%) → breakeven LCI = 10,80%.
    Qualquer LCI acima de 10,80% supera o CDB líquido.
    """
    if body.cdb_rate_pct <= 0:
        raise HTTPException(status_code=422, detail="cdb_rate_pct deve ser positivo.")
    if not (1 <= body.holding_months <= 360):
        raise HTTPException(status_code=422, detail="holding_months deve ser entre 1 e 360.")

    result = calc_breakeven(
        cdb_rate_pct=body.cdb_rate_pct,
        holding_months=body.holding_months,
        lci_offered_rate_pct=body.lci_offered_rate_pct,
    )

    if body.lci_offered_rate_pct and result.lci_advantage_pct is not None:
        if result.lci_advantage_pct > 0:
            interpretation = (
                f"LCI de {body.lci_offered_rate_pct:.2f}% é MELHOR que o CDB líquido "
                f"(+{result.lci_advantage_pct:.2f} p.p. acima do breakeven). Prefira a LCI."
            )
        else:
            interpretation = (
                f"LCI de {body.lci_offered_rate_pct:.2f}% é PIOR que o CDB líquido "
                f"({result.lci_advantage_pct:.2f} p.p. abaixo do breakeven). Prefira o CDB."
            )
    else:
        interpretation = (
            f"Para superar o CDB de {body.cdb_rate_pct:.2f}% líquido após IR {result.cdb_ir_rate*100:.0f}%, "
            f"a LCI precisa render pelo menos {result.lci_breakeven_pct:.2f}% a.a."
        )

    return BreakevenResponse(
        cdb_rate_pct=result.cdb_gross_rate_pct,
        holding_months=body.holding_months,
        ir_rate_pct=round(result.cdb_ir_rate * 100, 1),
        cdb_net_rate_pct=result.cdb_net_rate_pct,
        lci_breakeven_pct=result.lci_breakeven_pct,
        lci_advantage_pct=result.lci_advantage_pct,
        interpretation=interpretation,
    )


def _get_cdi() -> float:
    try:
        from app.architect.connectors.anbima import AnbimaConnector
        return AnbimaConnector().get_cdi()
    except Exception:
        return 0.1465


def _build_summary(portfolio, total_ir, opportunities, total_saving) -> str:
    taxable = [p for p in portfolio if not p.is_exempt]
    exempt = [p for p in portfolio if p.is_exempt]
    come_cotas = [p for p in portfolio if p.has_come_cotas]

    parts = [
        f"{len(portfolio)} posição(ões) mapeada(s): "
        f"{len(taxable)} tributável(is), {len(exempt)} isenta(s).",
    ]
    if come_cotas:
        parts.append(f"{len(come_cotas)} fundo(s) com come-cotas.")
    if total_ir > 0:
        parts.append(f"IR estimado se resgatar tudo hoje: R$ {total_ir:,.2f}.")
    if opportunities:
        parts.append(
            f"{len(opportunities)} oportunidade(s) encontrada(s) — "
            f"economia potencial de R$ {total_saving:,.2f} em IR."
        )
    else:
        parts.append("Nenhuma oportunidade de otimização fiscal detectada na carteira atual.")

    return " ".join(parts)
