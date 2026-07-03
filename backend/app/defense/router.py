"""
app/defense/router.py — D1–D6: Defesa do Consumidor

GET  /api/v1/defense/{user_id}                  — análise completa D1–D4
GET  /api/v1/defense/{user_id}/dossier          — dossiê D5 com correção monetária e templates
GET  /api/v1/defense/{user_id}/portability      — D6: análise de portabilidade
"""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.core.security import require_owner
from app.defense.models import DefenseResponse, EvidenceDossier, CorrectionIndex
from app.defense.services.tied_sale_detector import TiedSaleDetector
from app.defense.services.wrongful_charge_detector import WrongfulChargeDetector
from app.defense.services.abusive_interest_detector import AbusiveInterestDetector
from app.defense.services.unilateral_change_detector import UnilateralChangeDetector
from app.defense.services.portability_detector import PortabilityDetector
from app.defense.services.evidence_builder import EvidenceBuilder

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/defense", tags=["Defense (D1–D6)"])

_detectors = {
    "d1": TiedSaleDetector(),
    "d2": WrongfulChargeDetector(),
    "d3": AbusiveInterestDetector(),
    "d4": UnilateralChangeDetector(),
    "d6": PortabilityDetector(),
}
_builder = EvidenceBuilder()

_VALID_DETECTORS = {"d1", "d2", "d3", "d4", "d6"}


@router.get("/{user_id}", response_model=DefenseResponse)
def get_defense_analysis(
    user_id: str = Depends(require_owner),
    detectors: str = Query(
        default="d1,d2,d3,d4",
        description="Detectores a executar (vírgula): d1,d2,d3,d4,d6",
    ),
) -> DefenseResponse:
    """
    **Análise de Defesa do Consumidor (D1–D4)**

    | Detector | Descrição | Base Legal |
    |----------|-----------|-----------|
    | **D1** | Venda casada + correlação temporal crédito→seguro | CDC art. 39, I + Tema 972/STJ |
    | **D2** | Cobranças indevidas + serviços essenciais + regra do dobro | CDC art. 42 + EAREsp 676.608 |
    | **D3** | Juros abusivos — thresholds graduados vs BACEN/Olinda | REsp 1.061.530/RS (Tema 27) |
    | **D4** | Aumento unilateral — qualquer aumento sem aviso prévio | Res. CMN 3.919/2010, art. 3º |
    | **D6** | Portabilidade assistida | Res. CMN 5.057/2022 |

    ⚠️ Valores são ESTIMATIVAS educacionais. Consulte advogado antes de acionar o JEC.
    """
    from datetime import datetime, timezone

    selected = {d.strip().lower() for d in detectors.split(",")}
    invalid = selected - _VALID_DETECTORS
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Detectores inválidos: {invalid}. Use: {', '.join(sorted(_VALID_DETECTORS))}.",
        )

    all_findings = []
    for key in ("d1", "d2", "d3", "d4", "d6"):
        if key not in selected:
            continue
        try:
            findings = _detectors[key].detect(user_id)
            all_findings.extend(findings)
        except Exception as exc:
            logger.error("[defense] detector=%s user=%s: %s", key, user_id, exc)

    total_disputed = round(sum(f.amount_disputed for f in all_findings), 2)
    high   = sum(1 for f in all_findings if f.severity == "high")
    medium = sum(1 for f in all_findings if f.severity == "medium")
    low    = sum(1 for f in all_findings if f.severity == "low")

    if not all_findings:
        summary = (
            "Nenhuma irregularidade detectada. Continue monitorando mensalmente. "
            "Forneça mais histórico de transações para análise mais precisa."
        )
    else:
        banks = ", ".join(dict.fromkeys(f.bank_name for f in all_findings))
        summary = (
            f"{len(all_findings)} indício(s) detectado(s) em: {banks}. "
            f"Estimativa contestável: R$ {total_disputed:.2f}. "
            f"Severidade — alta: {high}, média: {medium}, baixa: {low}. "
            f"Valores são estimativas educacionais — consulte advogado."
        )

    logger.info(
        "[defense] user=%s detectors=%s findings=%d total=%.2f",
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
        description="Data da cobrança mais antiga (YYYY-MM-DD) para correção monetária.",
    ),
    correction_index: CorrectionIndex = Query(
        default="IPCA",
        description="Índice de correção: IPCA (padrão), SELIC ou INPC.",
    ),
) -> EvidenceDossier:
    """
    **Dossiê de Evidências (D5)**

    Executa D1–D4, calcula correção monetária acumulada mensalmente e gera:
    - **Carta de contestação** ao banco
    - **Relato para PROCON/Consumidor.gov.br**
    - **Petição inicial modelo** para Juizado Especial Cível (com valor da causa)

    ⚠️ Preencha [NOME COMPLETO], [CPF], [endereço] antes de protocolar.
    Recomenda-se revisão por advogado antes do JEC.
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
        "[defense/dossier] user=%s findings=%d total=%.2f",
        user_id, len(all_findings), dossier.total_disputed_amount,
    )
    return dossier


@router.get("/{user_id}/zip")
def get_evidence_zip(
    user_id: str = Depends(require_owner),
    charge_date: Optional[date] = Query(
        default=None,
        description="Data da cobrança mais antiga (YYYY-MM-DD) para correção monetária.",
    ),
    correction_index: CorrectionIndex = Query(
        default="IPCA",
        description="Índice de correção: IPCA (padrão), SELIC ou INPC.",
    ),
) -> Response:
    """
    **Pacote ZIP de Evidências (D5)**

    Baixa pacote ZIP com todos os documentos do dossiê:
    - Carta de contestação ao banco
    - Relato para PROCON / Consumidor.gov.br
    - Modelo de petição JEC
    - Resumo dos achados

    ⚠️ Preencha seus dados pessoais antes de protocolar.
    """
    all_findings = []
    for key in ("d1", "d2", "d3", "d4"):
        try:
            findings = _detectors[key].detect(user_id)
            all_findings.extend(findings)
        except Exception as exc:
            logger.error("[defense/zip] detector=%s user=%s: %s", key, user_id, exc)

    try:
        zip_bytes = _builder.build_zip_package(
            user_id=user_id,
            findings=all_findings,
            charge_date=charge_date,
            correction_index=correction_index,
        )
    except Exception as exc:
        logger.error("[defense/zip] build_zip_package user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar pacote ZIP.")

    logger.info("[defense/zip] user=%s findings=%d", user_id, len(all_findings))

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="dossie_nexa_{user_id}.zip"'
        },
    )


@router.get("/{user_id}/portability", response_model=DefenseResponse)
def get_portability_analysis(
    user_id: str = Depends(require_owner),
) -> DefenseResponse:
    """
    **D6 — Portabilidade Assistida (Res. CMN 5.057/2022)**

    Detecta contratos com taxa acima do benchmark de mercado e gera roteiro
    completo para solicitar portabilidade gratuitamente.

    Regras da Res. CMN 5.057/2022:
    - Portabilidade **gratuita** para o consumidor.
    - Banco cedente tem **5 dias úteis** para contraproposta.
    - Novo contrato não pode exceder saldo devedor e prazo remanescente.

    ⚠️ Valores são estimativas. A portabilidade pode não ser aprovada pelo banco destino.
    """
    from datetime import datetime, timezone

    try:
        findings = _detectors["d6"].detect(user_id)
    except Exception as exc:
        logger.error("[defense/portability] user=%s: %s", user_id, exc)
        findings = []

    total = round(sum(f.amount_disputed for f in findings), 2)
    high   = sum(1 for f in findings if f.severity == "high")
    medium = sum(1 for f in findings if f.severity == "medium")
    low    = sum(1 for f in findings if f.severity == "low")

    if not findings:
        summary = (
            "Nenhum contrato com taxa acima do benchmark detectado. "
            "Forneça taxa contratada ou conecte conta via Open Finance para análise precisa."
        )
    else:
        banks = ", ".join(dict.fromkeys(f.bank_name for f in findings))
        summary = (
            f"{len(findings)} oportunidade(s) de portabilidade em: {banks}. "
            f"Economia estimada total: R$ {total:.2f}. "
            f"Portabilidade é gratuita (Res. CMN 5.057/2022)."
        )

    logger.info("[defense/portability] user=%s findings=%d economy=%.2f", user_id, len(findings), total)

    return DefenseResponse(
        user_id=user_id,
        generated_at=datetime.now(timezone.utc),
        findings=findings,
        total_findings=len(findings),
        high_severity=high,
        medium_severity=medium,
        low_severity=low,
        total_disputed_amount=total,
        summary=summary,
    )
