"""
app/api/v1/routes/negotiator.py — F13: Negotiator Bot

Endpoints:
  POST  /negotiator/generate-script          — detecta oportunidades e gera roteiro
  GET   /negotiator/history/{user_id}        — lista histórico de negociações
  PATCH /negotiator/history/{record_id}      — registra resultado da negociação
"""

import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_current_user, require_owner
from app.core.database import get_db
from sqlalchemy.orm import Session
from app.negotiator.health_score import score_nexa
from app.negotiator.models import NegotiationReport, NegotiationRequest
from app.negotiator.opportunity_detector import NegotiationOpportunityDetector
from app.negotiator.script_generator import NegotiationScriptGenerator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/negotiator", tags=["Negotiator Bot (F13)"])

ResultStatus = Literal["sucesso", "parcial", "recusado", "nao_tentou"]


# ── Schemas de histórico ──────────────────────────────────────────────

class NegotiationHistoryItem(BaseModel):
    id: str
    bank_name: str
    trigger_type: str
    potential_gain: Optional[float] = None
    generated_at: datetime
    result_status: Optional[str] = None
    result_gain: Optional[float] = None
    resolved_at: Optional[datetime] = None


class NegotiationHistoryResponse(BaseModel):
    user_id: str
    total: int
    items: list[NegotiationHistoryItem]
    total_potential_gain: float
    total_realized_gain: float


class NegotiationResultUpdate(BaseModel):
    result_status: ResultStatus
    result_gain: Optional[float] = None  # ganho real obtido (R$/mês), se houver


@router.post("/generate-script", response_model=NegotiationReport)
async def generate_negotiation_script(
    request: NegotiationRequest,
    current_user: str = Depends(get_current_user),
) -> NegotiationReport:
    """
    **F13 — Negotiator Bot**

    Detecta oportunidades de negociação bancária e gera roteiros personalizados via IA.

    Cruza 3 fontes de dados:
    - **FeeDetector (F5)** → juros rotativos e anuidades pagas pelo usuário
    - **BACEN** → taxa SELIC como referência de mercado (CDC = SELIC/12 + 2,5%)
    - **Health Score** → poder de barganha do usuário (proxy: meses sem juros rotativos)

    **Triggers detectados:**
    - `JUROS_ROTATIVO_ALTO` — pagou juros nos últimos 3 meses
    - `ANUIDADE_ALTA` — anuidade > R$ 30/mês nos últimos 12 meses
    - `HEALTH_SCORE_ALTO` — score ≥ 70 sem outros triggers (renegociação proativa)
    """
    # Gating: Free = 0 roteiros; Pro = 1/mês; Total = ilimitado
    from app.billing.gating import consume_usage
    consume_usage(current_user, "negotiator_scripts")
    if current_user != request.user_id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    logger.info("[API] F13 negotiator/generate-script | user=%s bank=%s", request.user_id, request.bank_name)

    # ── 1. Buscar transações ──────────────────────────────────────
    try:
        from app.core.db.queries import get_transactions_for_user
        transactions_df = get_transactions_for_user(request.user_id)
    except Exception as exc:
        logger.error("[API] F13 erro ao buscar transações: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao acessar dados do usuário.")

    if transactions_df.is_empty():
        raise HTTPException(
            status_code=404,
            detail=f"Sem histórico de transações para user_id={request.user_id}. "
                   "Conecte sua conta bancária via Open Finance primeiro.",
        )

    # ── 2. Buscar health score ────────────────────────────────────
    # Fonte única — ver negotiator/health_score.py. Havia aqui uma cópia de
    # `_get_health_score` que importava `app.profile`, módulo inexistente:
    # o except devolvia 50 para todo usuário, sempre.
    health_score = score_nexa(transactions_df)

    # ── 3. Detectar oportunidades ────────────────────────────────
    detector = NegotiationOpportunityDetector()
    opportunities = detector.detect(transactions_df, health_score=health_score)

    # Filtra por banco específico se informado
    if request.bank_name:
        bank_lower = request.bank_name.lower()
        opportunities = [
            o for o in opportunities
            if o.bank_name.lower() == bank_lower
        ]

    if not opportunities:
        return NegotiationReport(
            user_id=request.user_id,
            opportunities_found=0,
            scripts=[],
            summary=(
                "Não foram encontradas oportunidades de negociação no momento. "
                "Continue mantendo um bom histórico financeiro para aumentar seu poder de barganha."
            ),
            confidence_score=0.5,
            # Mesmo marcador do relatório completo: sem ele, o dia em que o
            # perfil parar de ser calculado passa despercebido de novo.
            data_sources=(
                ["transactions_clean", "fee_detector"]
                + (["user_profile_analyzer"] if health_score is not None else [])
            ),
            warnings=(
                ["Sem oportunidades detectadas com os dados disponíveis."]
                + ([] if health_score is not None else [
                    "Score Nexa indisponível — negociação proativa por bom "
                    "histórico não pôde ser avaliada."
                ])
            ),
        )

    # ── 4. Gerar scripts para cada oportunidade ──────────────────
    generator = NegotiationScriptGenerator()
    scripts = []
    warnings: list[str] = []

    for opp in opportunities:
        script = generator.generate(opp)
        scripts.append(script)
        warnings.extend(script.warnings)
        _persist_negotiation(request.user_id, opp)

    # ── 5. Montar relatório final ────────────────────────────────
    # Loop fechado (F13): quando há desfechos reais suficientes, o ganho
    # apresentado é calibrado pelo fator de realização observado — e a
    # origem é declarada ao usuário (nunca calibração silenciosa).
    from app.negotiator.calibration import get_calibration_factor

    total_saving = 0.0
    calibrated_notes: list[str] = []
    for opp in opportunities:
        trigger_name = getattr(opp.trigger, "value", str(opp.trigger))
        calibration = get_calibration_factor(trigger_name)
        if calibration is not None:
            factor, samples = calibration
            total_saving += opp.potential_saving_monthly * factor
            calibrated_notes.append(
                f"{trigger_name}: estimativa ajustada por resultados reais "
                f"(fator {factor:.2f}, {samples} negociações reportadas)"
            )
        else:
            total_saving += opp.potential_saving_monthly

    confidence = _compute_confidence(health_score, len(opportunities), transactions_df.height)

    summary = _build_summary(opportunities, total_saving, health_score)
    warnings.extend(calibrated_notes)
    if health_score is None:
        warnings.append(
            "Score Nexa indisponível — os roteiros não usam score como argumento."
        )

    return NegotiationReport(
        user_id=request.user_id,
        opportunities_found=len(opportunities),
        scripts=scripts,
        summary=summary,
        confidence_score=confidence,
        # `user_profile_analyzer` só entra quando o score foi REALMENTE
        # calculado — é o marcador que teria denunciado o import quebrado.
        data_sources=[
            "transactions_clean", "fee_detector", "bacen_sgs_credito",
            "claude-haiku-4-5-20251001",
        ] + (["user_profile_analyzer"] if health_score is not None else []),
        warnings=list(dict.fromkeys(warnings)),  # deduplica mantendo ordem
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2.7 — Follow-up do histórico de negociações
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/history/{user_id}", response_model=NegotiationHistoryResponse)
def get_negotiation_history(
    user_id: str = Depends(require_owner),
    db: Session = Depends(get_db),
) -> NegotiationHistoryResponse:
    """
    Lista o histórico de negociações do usuário, do mais recente ao mais antigo.

    Inclui status do resultado quando o usuário já reportou (via PATCH /history/{id}).
    Usado pelo agent (V2/Wrapped) e pelo daily digest para detectar negociações recentes.
    """
    from sqlalchemy import text

    try:
        rows = db.execute(
            text(
                "SELECT id, bank_name, trigger_type, potential_gain, generated_at,"
                "       result_status, result_gain, resolved_at"
                " FROM negotiation_history"
                " WHERE user_id = :uid"
                " ORDER BY generated_at DESC"
                " LIMIT 200"
            ),
            {"uid": user_id},
        ).fetchall()
    except Exception as exc:
        logger.error("[negotiator] get_history user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao buscar histórico de negociações.")

    items = [
        NegotiationHistoryItem(
            id=r[0],
            bank_name=r[1],
            trigger_type=r[2],
            potential_gain=float(r[3]) if r[3] is not None else None,
            generated_at=r[4],
            result_status=r[5],
            result_gain=float(r[6]) if r[6] is not None else None,
            resolved_at=r[7],
        )
        for r in rows
    ]

    total_potential = sum(i.potential_gain or 0.0 for i in items)
    total_realized = sum(
        i.result_gain or 0.0
        for i in items
        if i.result_status in ("sucesso", "parcial")
    )

    return NegotiationHistoryResponse(
        user_id=user_id,
        total=len(items),
        items=items,
        total_potential_gain=round(total_potential, 2),
        total_realized_gain=round(total_realized, 2),
    )


@router.patch("/history/{record_id}", response_model=NegotiationHistoryItem)
def update_negotiation_result(
    record_id: str,
    body: NegotiationResultUpdate,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NegotiationHistoryItem:
    """
    Registra o resultado de uma negociação já gerada.

    O usuário informa o que aconteceu depois de usar o roteiro:
    - **sucesso** — banco aceitou, ganho real informado via `result_gain`
    - **parcial** — aceitou parcialmente (ex: reduziu mas não zerou anuidade)
    - **recusado** — banco recusou a negociação
    - **nao_tentou** — usuário não chegou a usar o roteiro

    Esses dados alimentam:
    - Badge NEGOCIADOR (health_score/badge_service.py)
    - Wrapped anual (agent/tools/get_annual_wrapped.py)
    - Relatório de sucesso no daily digest
    """
    from sqlalchemy import text

    try:
        row = db.execute(
            text("SELECT user_id FROM negotiation_history WHERE id = :rid"),
            {"rid": record_id},
        ).fetchone()
    except Exception as exc:
        logger.error("[negotiator] patch history read record=%s: %s", record_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao buscar registro.")

    if row is None:
        raise HTTPException(status_code=404, detail="Registro de negociação não encontrado.")

    if row[0] != current_user:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    now = datetime.now(timezone.utc)

    try:
        db.execute(
            text(
                "UPDATE negotiation_history"
                " SET result_status = :st,"
                "     result_gain   = :gain,"
                "     resolved_at   = :res"
                " WHERE id = :rid"
            ),
            {
                "st":   body.result_status,
                "gain": body.result_gain,
                "res":  now,
                "rid":  record_id,
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("[negotiator] patch history write record=%s: %s", record_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao salvar resultado.")

    try:
        updated = db.execute(
            text(
                "SELECT id, bank_name, trigger_type, potential_gain, generated_at,"
                "       result_status, result_gain, resolved_at"
                " FROM negotiation_history WHERE id = :rid"
            ),
            {"rid": record_id},
        ).fetchone()
    except Exception as exc:
        logger.error("[negotiator] patch history re-read record=%s: %s", record_id, exc)
        raise HTTPException(status_code=500, detail="Resultado salvo mas falhou ao reler.")

    logger.info(
        "[negotiator] resultado registrado: record=%s status=%s gain=%s",
        record_id, body.result_status, body.result_gain,
    )

    return NegotiationHistoryItem(
        id=updated[0],
        bank_name=updated[1],
        trigger_type=updated[2],
        potential_gain=float(updated[3]) if updated[3] is not None else None,
        generated_at=updated[4],
        result_status=updated[5],
        result_gain=float(updated[6]) if updated[6] is not None else None,
        resolved_at=updated[7],
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _compute_confidence(
    health_score: Optional[int], n_opportunities: int, n_transactions: int
) -> float:
    """
    Confiança do relatório:
    - n_transactions >= 90 (3 meses de dados) → base alta
    - health_score bem calculado → bom sinal
    - pelo menos 1 oportunidade detectada → plena confiança

    Sem score, o termo vale ZERO — não 0,15. Enquanto o score voltava 50 fixo,
    todo relatório carregava esse 0,15 como se fosse informação.
    """
    base = min(n_transactions / 90, 1.0) * 0.5   # até 0.5 por volume de dados
    score_factor = (health_score / 100) * 0.3 if health_score is not None else 0.0
    opp_factor = 0.2 if n_opportunities > 0 else 0.0
    return round(min(base + score_factor + opp_factor, 1.0), 2)


def _persist_negotiation(user_id: str, opp) -> None:
    """Persiste oportunidade gerada em negotiation_history. Falha silenciosamente."""
    import uuid
    from datetime import datetime, timezone

    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            db.execute(
                text(
                    "INSERT INTO negotiation_history"
                    " (id, user_id, bank_name, trigger_type, potential_gain, generated_at)"
                    " VALUES (:id, :uid, :bank, :trigger, :gain, :gen_at)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "uid": user_id,
                    "bank": opp.bank_name,
                    "trigger": opp.trigger.value,
                    "gain": float(opp.potential_saving_monthly),
                    "gen_at": datetime.now(timezone.utc),
                },
            )
            db.commit()
    except Exception as exc:
        logger.warning("[API] F13 persist_negotiation falhou: %s", exc)


def _build_summary(
    opportunities, total_saving: float, health_score: Optional[int]
) -> str:
    n = len(opportunities)
    banks = ", ".join(dict.fromkeys(o.bank_name for o in opportunities))
    saving_str = f"R$ {total_saving:.2f}/mês" if total_saving > 0 else "condições melhores"

    if health_score is None:
        trecho_score = "Não consegui calcular seu Score Nexa desta vez."
    else:
        trecho_score = (
            f"Seu Score Nexa é {health_score}/100 — "
            + ("ótimo poder de barganha." if health_score >= 70 else "bom perfil para negociar.")
        )

    return (
        f"Encontrei {n} oportunidade(s) de negociação com {banks}. "
        f"Economia potencial estimada: {saving_str}. "
        + trecho_score
    )
