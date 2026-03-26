# app/api/v1/routes/fiscal_report.py

from fastapi import APIRouter, HTTPException, Query, Depends, status
from app.core.security import get_current_user
from pydantic import BaseModel
from typing import Optional
import logging
from datetime import date

from app.fiscal.fiscal_report import FiscalReportService, SubcategoryLine
from app.forecast.etl.mixed_use_detector import MixedUseDetector

router = APIRouter(prefix="/fiscal-report", tags=["Fiscal Report"])
logger = logging.getLogger(__name__)

_service = FiscalReportService()
_mixed_use_detector = MixedUseDetector()


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
async def get_fiscal_report(
    user_id: str,
    year: int = Query(default=None, description="Ano do relatorio (padrao: ano atual)"),
    month: Optional[int] = Query(default=None, ge=1, le=12, description="Mes 1-12. Omitir para relatorio anual."),
    current_user: str = Depends(get_current_user),
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
    if current_user != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    if year is None:
        year = date.today().year

    try:
        report = _service.generate(user_id=user_id, year=year, month=month)
    except Exception as e:
        logger.error(f"Erro ao gerar relatorio fiscal user={user_id}: {e}")
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
    user_id: str,
    year: int = Query(default=None, description="Ano (padrao: ano atual)"),
    month: Optional[int] = Query(default=None, ge=1, le=12, description="Mes 1-12. Omitir para relatorio anual."),
    current_user: str = Depends(get_current_user),
):
    """
    Detecta transacoes PF com potencial de uso misto PF/PJ.

    Identifica despesas como plano de celular, internet, combustivel e energia
    que podem ser parcialmente deduzidas como despesa operacional PJ.
    Retorna percentual de rateio sugerido e valor PJ dedutivel estimado.
    """
    if current_user != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    if year is None:
        year = date.today().year

    try:
        report = _mixed_use_detector.detect(user_id=user_id, year=year, month=month)
    except Exception as e:
        logger.error(f"Erro ao detectar uso misto user={user_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro ao detectar uso misto.")

    return MixedUseReportResponse(
        user_id=report.user_id,
        period_label=report.period_label,
        candidates=[MixedUseCandidateOut(**vars(c)) for c in report.candidates],
        total_mixed_spend=report.total_mixed_spend,
        total_pj_deductible=report.total_pj_deductible,
    )
