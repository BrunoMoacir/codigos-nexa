"""
app/api/v1/routes/negotiator.py — F13: Negotiator Bot

Endpoint: POST /negotiator/generate-script
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.negotiator.models import NegotiationReport, NegotiationRequest
from app.negotiator.opportunity_detector import NegotiationOpportunityDetector
from app.negotiator.script_generator import NegotiationScriptGenerator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/negotiator", tags=["Negotiator Bot (F13)"])


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
    health_score = _get_health_score(request.user_id, transactions_df)

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
            data_sources=["transactions_clean", "fee_detector"],
            warnings=["Sem oportunidades detectadas com os dados disponíveis."],
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
    total_saving = sum(o.potential_saving_monthly for o in opportunities)
    confidence = _compute_confidence(health_score, len(opportunities), transactions_df.height)

    summary = _build_summary(opportunities, total_saving, health_score)

    return NegotiationReport(
        user_id=request.user_id,
        opportunities_found=len(opportunities),
        scripts=scripts,
        summary=summary,
        confidence_score=confidence,
        data_sources=["transactions_clean", "fee_detector", "bacen_sgs_credito", "claude-haiku-4-5-20251001"],
        warnings=list(dict.fromkeys(warnings)),  # deduplica mantendo ordem
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_health_score(user_id: str, transactions_df) -> int:
    """Calcula health score via UserProfileAnalyzer. Fallback: 50."""
    try:
        from app.profile.user_profile_analyzer import UserProfileAnalyzer
        profile = UserProfileAnalyzer().analyze(transactions_df, user_id=user_id)
        return profile.health_score
    except Exception as exc:
        logger.warning("[API] F13 health score indisponível: %s", exc)
        return 50


def _compute_confidence(health_score: int, n_opportunities: int, n_transactions: int) -> float:
    """
    Confiança do relatório:
    - n_transactions >= 90 (3 meses de dados) → base alta
    - health_score bem calculado → bom sinal
    - pelo menos 1 oportunidade detectada → plena confiança
    """
    base = min(n_transactions / 90, 1.0) * 0.5   # até 0.5 por volume de dados
    score_factor = (health_score / 100) * 0.3     # até 0.3 pelo health score
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


def _build_summary(opportunities, total_saving: float, health_score: int) -> str:
    n = len(opportunities)
    banks = ", ".join(dict.fromkeys(o.bank_name for o in opportunities))
    saving_str = f"R$ {total_saving:.2f}/mês" if total_saving > 0 else "condições melhores"

    return (
        f"Encontrei {n} oportunidade(s) de negociação com {banks}. "
        f"Economia potencial estimada: {saving_str}. "
        f"Seu Score Nexa é {health_score}/100 — "
        + ("ótimo poder de barganha." if health_score >= 70 else "bom perfil para negociar.")
    )
