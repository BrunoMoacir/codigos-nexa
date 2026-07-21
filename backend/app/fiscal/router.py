# app/api/v1/routes/fiscal_report.py

from fastapi import APIRouter, HTTPException, Query, Depends, status
from app.core.security import require_owner
from app.core.cache import cache_response
from pydantic import BaseModel
from typing import Literal, Optional
import logging
from datetime import date

from app.fiscal.fiscal_report import FiscalReportService, SubcategoryLine
from app.fiscal.ir_pf_calculator import IRPFCalculator, InvestmentType
from app.forecast.etl.mixed_use_detector import MixedUseDetector

from app.fiscal.rights_monitor.models import ForgottenRightsReport
from app.fiscal.rights_monitor.services.monitor import RightsMonitorAggregator

router = APIRouter(prefix="/fiscal-report", tags=["Fiscal Report"])
logger = logging.getLogger(__name__)

_service = FiscalReportService()
_mixed_use_detector = MixedUseDetector()
_ir_calc = IRPFCalculator()
_rights_monitor = RightsMonitorAggregator()


class SubcategoryLineOut(BaseModel):
    subcategory: str
    label: str
    total: float
    count: int


class FiscalReportResponse(BaseModel):
    user_id: str
    period_label: str
    year: int
    month: Optional[int]

    receitas: list[SubcategoryLineOut]
    despesas: list[SubcategoryLineOut]

    total_receita: float
    total_despesa: float
    lucro_estimado: float

    rbt12_anualizado: float
    das_aliquota_efetiva: float   # em %
    das_estimado: float
    das_faixa: str

    total_transactions: int


@router.get("/{user_id}", response_model=FiscalReportResponse)
@cache_response(prefix="fiscal", ttl=1800)  # 30 min
async def get_fiscal_report(
    user_id: str = Depends(require_owner),
    year: int = Query(default=None, description="Ano do relatorio (padrao: ano atual)"),
    month: Optional[int] = Query(default=None, ge=1, le=12, description="Mes 1-12. Omitir para relatorio anual."),
):
    """
    Relatorio fiscal automatizado das transacoes PJ do usuario.

    - Receitas e despesas por subcategoria PJ
    - Lucro estimado
    - DAS estimado (Simples Nacional Anexo III — Servicos)

    Parametros:
    - **year**: Ano (padrao: ano atual)
    - **month**: Mes 1-12. Omitir para relatorio anual completo.
    """

    if year is None:
        year = date.today().year

    try:
        report = _service.generate(user_id=user_id, year=year, month=month)
    except Exception as e:
        logger.error("Erro ao gerar relatorio fiscal user=%s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Erro ao gerar relatorio fiscal.")

    return FiscalReportResponse(
        user_id=report.user_id,
        period_label=report.period_label,
        year=report.year,
        month=report.month,
        receitas=[SubcategoryLineOut(**vars(r)) for r in report.receitas],
        despesas=[SubcategoryLineOut(**vars(d)) for d in report.despesas],
        total_receita=report.total_receita,
        total_despesa=report.total_despesa,
        lucro_estimado=report.lucro_estimado,
        rbt12_anualizado=report.rbt12_anualizado,
        das_aliquota_efetiva=report.das_aliquota_efetiva,
        das_estimado=report.das_estimado,
        das_faixa=report.das_faixa,
        total_transactions=report.total_transactions,
    )


# ---------------------------------------------------------------------------
# M4.3 — Deteccao de Uso Misto
# ---------------------------------------------------------------------------

class MixedUseCandidateOut(BaseModel):
    transaction_id: str
    description: str
    amount: float
    date: str
    matched_rule: str
    suggested_pj_pct: float
    pj_amount: float
    pf_amount: float
    explanation: str


class MixedUseReportResponse(BaseModel):
    user_id: str
    period_label: str
    candidates: list[MixedUseCandidateOut]
    total_mixed_spend: float
    total_pj_deductible: float


@router.get("/{user_id}/mixed-use", response_model=MixedUseReportResponse)
async def get_mixed_use_report(
    user_id: str = Depends(require_owner),
    year: int = Query(default=None, description="Ano (padrao: ano atual)"),
    month: Optional[int] = Query(default=None, ge=1, le=12, description="Mes 1-12. Omitir para relatorio anual."),
):
    """
    Detecta transacoes PF com potencial de uso misto PF/PJ.

    Identifica despesas como plano de celular, internet, combustivel e energia
    que podem ser parcialmente deduzidas como despesa operacional PJ.
    Retorna percentual de rateio sugerido e valor PJ dedutivel estimado.
    """

    if year is None:
        year = date.today().year

    try:
        report = _mixed_use_detector.detect(user_id=user_id, year=year, month=month)
    except Exception as e:
        logger.error("Erro ao detectar uso misto user=%s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Erro ao detectar uso misto.")

    return MixedUseReportResponse(
        user_id=report.user_id,
        period_label=report.period_label,
        candidates=[MixedUseCandidateOut(**vars(c)) for c in report.candidates],
        total_mixed_spend=report.total_mixed_spend,
        total_pj_deductible=report.total_pj_deductible,
    )


# ---------------------------------------------------------------------------
# T1/T2 — IR PF sobre Investimentos
# ---------------------------------------------------------------------------

class IRResultOut(BaseModel):
    investment_type: str
    gross_yield_brl: float
    ir_rate: float
    ir_brl: float
    net_yield_brl: float
    net_annual_rate_pct: float
    is_exempt: bool


class BreakevenOut(BaseModel):
    cdb_gross_rate_pct: float
    cdb_ir_rate: float
    cdb_net_rate_pct: float
    lci_breakeven_pct: float
    lci_advantage_pct: Optional[float] = None


class IRCompareResponse(BaseModel):
    amount: float
    holding_months: int
    cdb: IRResultOut
    lci: IRResultOut
    recommended: str            # "CDB" | "LCI"
    net_difference_brl: float   # rendimento líquido LCI − CDB (positivo = LCI ganha)
    breakeven: BreakevenOut


@router.get("/ir-pf/compare", response_model=IRCompareResponse)
def get_ir_pf_compare(
    user_id: str = Depends(require_owner),
    amount: float = Query(..., gt=0, description="Valor a investir (R$)"),
    cdb_rate_pct: float = Query(..., gt=0, description="Taxa bruta anual do CDB (%). Ex: 13.5"),
    lci_rate_pct: float = Query(..., gt=0, description="Taxa anual da LCI (%). Ex: 10.8"),
    holding_months: int = Query(default=12, ge=1, le=360, description="Prazo em meses"),
):
    """
    Compara rendimento líquido de CDB vs LCI/LCA para o mesmo capital e prazo.

    Considera a tabela regressiva de IR (22,5% → 15%) sobre o CDB e
    isenção total para LCI/LCA. Retorna qual investimento rende mais no
    prazo informado e a taxa mínima de LCI equivalente (breakeven).

    **Exemplo:**
    - CDB 13,5% a.a., LCI 10,8% a.a., 12 meses, R$ 50.000
    - CDB líquido ≈ 10,8% a.a. (após 20% IR no prazo de 12 meses)
    - LCI 10,8% = breakeven exato — qualquer LCI acima já supera o CDB

    **Alíquotas IR (tabela regressiva):**
    - Até 180 dias → 22,5%
    - 181–360 dias → 20,0%
    - 361–720 dias → 17,5%
    - Acima de 720 dias → 15,0%
    """
    try:
        comp = _ir_calc.compare(
            principal=amount,
            cdb_rate_pct=cdb_rate_pct,
            lci_rate_pct=lci_rate_pct,
            holding_months=holding_months,
        )
        bk = _ir_calc.calc_breakeven_lci(
            cdb_gross_rate_pct=cdb_rate_pct,
            holding_months=holding_months,
            lci_offered_rate_pct=lci_rate_pct,
        )
    except Exception as exc:
        logger.error("Erro em ir-pf/compare user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao calcular IR.")

    return IRCompareResponse(
        amount=comp.amount,
        holding_months=comp.holding_months,
        cdb=IRResultOut(**vars(comp.cdb)),
        lci=IRResultOut(**vars(comp.lci)),
        recommended=comp.recommended,
        net_difference_brl=comp.net_difference_brl,
        breakeven=BreakevenOut(**vars(bk)),
    )


@router.get("/ir-pf/breakeven", response_model=BreakevenOut)
def get_ir_pf_breakeven(
    user_id: str = Depends(require_owner),
    cdb_rate_pct: float = Query(..., gt=0, description="Taxa bruta anual do CDB (%)"),
    holding_months: int = Query(default=12, ge=1, le=360, description="Prazo em meses"),
    lci_offered_pct: Optional[float] = Query(
        default=None, gt=0,
        description="Taxa da LCI disponível no mercado (%). Calcula a vantagem da LCI.",
    ),
):
    """
    Calcula a taxa mínima de LCI/LCA equivalente a um CDB tributado.

    Responde: "Se o CDB paga X% a.a. com IR de Y%, qual a taxa mínima de LCI
    que iguala o rendimento líquido?"

    Fórmula: lci_breakeven = cdb_rate × (1 − alíquota_IR)
    """
    try:
        bk = _ir_calc.calc_breakeven_lci(
            cdb_gross_rate_pct=cdb_rate_pct,
            holding_months=holding_months,
            lci_offered_rate_pct=lci_offered_pct,
        )
    except Exception as exc:
        logger.error("Erro em ir-pf/breakeven user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao calcular breakeven.")

    return BreakevenOut(**vars(bk))

# ---------------------------------------------------------------------------
# T3 — Monitor de Direitos Esquecidos
# ---------------------------------------------------------------------------

@router.get("/forgotten-rights", response_model=ForgottenRightsReport)
async def get_forgotten_rights(
    user_id: str = Depends(require_owner),
    cpf: str = Query(..., description="CPF do usuário para consulta (somente números)"),
):
    """
    T3 - Monitor de Direitos Esquecidos (visão fiscal).

    Retorna o status de verificação por fonte, sem fabricar valores:
    - SVR BACEN → consulta REAL assistida em `POST /rights/{user_id}/svr/check`
    - Restituição IRPF → consulta REAL autorizada em `POST /rights/{user_id}/ir/check`
    - FGTS → orientação (sem API pública para terceiros)
    """
    try:
        report = await _rights_monitor.run_scan(user_id=user_id, cpf=cpf)
        return report
    except Exception as exc:
        logger.error("Erro ao buscar direitos esquecidos user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao buscar direitos esquecidos.")
