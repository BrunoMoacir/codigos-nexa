"""
app/defense/router.py — D1–D5: Defesa do Consumidor

GET  /api/v1/defense/{user_id}           — análise completa D1–D4
GET  /api/v1/defense/{user_id}/dossier   — dossiê D5 com correção monetária e templates
"""

import logging
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import require_owner
from app.defense.models import DefenseResponse, EvidenceDossier, CorrectionIndex
from app.defense.services.tied_sale_detector import TiedSaleDetector
from app.defense.services.wrongful_charge_detector import WrongfulChargeDetector
from app.defense.services.abusive_interest_detector import AbusiveInterestDetector
from app.defense.services.unilateral_change_detector import UnilateralChangeDetector
from app.defense.services.evidence_builder import EvidenceBuilder

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/defense", tags=["Defense (D1–D5)"])

_detectors = {
    "d1": TiedSaleDetector(),
    "d2": WrongfulChargeDetector(),
    "d3": AbusiveInterestDetector(),
    "d4": UnilateralChangeDetector(),
}
_builder = EvidenceBuilder()


@router.get("/{user_id}", response_model=DefenseResponse)
def get_defense_analysis(
    user_id: str = Depends(require_owner),
    detectors: str = Query(
        default="d1,d2,d3,d4",
        description="Detectores a executar, separados por vírgula: d1,d2,d3,d4",
    ),
) -> DefenseResponse:
    """
    **Análise de Defesa do Consumidor (D1–D4)**

    Executa os detectores selecionados e retorna todos os achados.

    | Detector | Descrição |
    |----------|-----------|
    | **D1** | Venda casada — seguros embutidos em crédito (Res. BACEN 3.919/2010) |
    | **D2** | Cobranças indevidas — duplicatas, pós-cancelamento, sem contrato |
    | **D3** | Juros abusivos — acima da taxa média BACEN SGS 20714/20706 |
    | **D4** | Aumento unilateral — tarifa subiu >10% sem notificação prévia |

    Para gerar o dossiê completo com carta e petição, use `GET /defense/{user_id}/dossier`.
    """
    from datetime import datetime, timezone

    selected = {d.strip().lower() for d in detectors.split(",")}
    invalid = selected - {"d1", "d2", "d3", "d4"}
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Detectores inválidos: {invalid}. Use d1, d2, d3 ou d4.",
        )

    all_findings = []
    for key in ("d1", "d2", "d3", "d4"):
        if key not in selected:
            continue
        try:
            findings = _detectors[key].detect(user_id)
            all_findings.extend(findings)
        except Exception as exc:
            logger.error("[defense] detector=%s user=%s: %s", key, user_id, exc)

    total_disputed = round(sum(f.amount_disputed for f in all_findings), 2)
    high = sum(1 for f in all_findings if f.severity == "high")
    medium = sum(1 for f in all_findings if f.severity == "medium")
    low = sum(1 for f in all_findings if f.severity == "low")

    if not all_findings:
        summary = (
            "Nenhuma irregularidade detectada nos detectores selecionados. "
            "Continue monitorando mensalmente."
        )
    else:
        banks = ", ".join(dict.fromkeys(f.bank_name for f in all_findings))
        summary = (
            f"{len(all_findings)} irregularidade(s) detectada(s) em: {banks}. "
            f"Total contestável: R$ {total_disputed:.2f}. "
            f"Severidade — alta: {high}, média: {medium}, baixa: {low}."
        )

    logger.info(
        "[defense] user=%s detectors=%s findings=%d total_disputed=%.2f",
        user_id, detectors, len(all_findings), total_disputed,
    )

    return DefenseResponse(
        user_id=user_id,
        generated_at=datetime.now(timezone.utc),
        findings=all_findings,
        total_findings=len(all_findings),
        high_severity=high,
        medium_severity=medium,
        low_severity=low,
        total_disputed_amount=total_disputed,
        summary=summary,
    )


@router.get("/{user_id}/dossier", response_model=EvidenceDossier)
def get_evidence_dossier(
    user_id: str = Depends(require_owner),
    charge_date: Optional[date] = Query(
        default=None,
        description="Data da cobrança mais antiga (YYYY-MM-DD) para cálculo de correção monetária.",
    ),
    correction_index: CorrectionIndex = Query(
        default="IPCA",
        description="Índice de correção monetária: IPCA (padrão), SELIC ou INPC.",
    ),
) -> EvidenceDossier:
    """
    **Dossiê de Evidências (D5)**

    Executa todos os detectores (D1–D4), calcula correção monetária e gera:
    - **Carta de contestação** pronta para enviar ao banco
    - **Relato para PROCON** com evidências detalhadas
    - **Petição inicial simplificada** para Juizado Especial Cível

    Se `charge_date` for informada, aplica correção monetária sobre o total
    contestado desde aquela data até hoje, usando o índice selecionado.

    **Importante:** preencha os campos `[NOME COMPLETO]`, `[CPF]`, `[endereço]`
    antes de protocolar qualquer documento gerado.
    """
    all_findings = []
    for key in ("d1", "d2", "d3", "d4"):
        try:
            findings = _detectors[key].detect(user_id)
            all_findings.extend(findings)
        except Exception as exc:
            logger.error("[defense/dossier] detector=%s user=%s: %s", key, user_id, exc)

    try:
        dossier = _builder.build_dossier(
            user_id=user_id,
            findings=all_findings,
            charge_date=charge_date,
            correction_index=correction_index,
        )
    except Exception as exc:
        logger.error("[defense/dossier] build_dossier user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar dossiê.")

    logger.info(
        "[defense/dossier] user=%s findings=%d total_disputed=%.2f",
        user_id, len(all_findings), dossier.total_disputed_amount,
    )
    return dossier
