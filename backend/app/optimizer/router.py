# app/api/v1/routes/optimizer.py
# Rotas REST da Funcionalidade 2: Nexa Optimizer

import json
import logging
from datetime import datetime as _datetime
from typing import Optional

import polars as pl
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel as _BaseModel

from app.core.db.queries import get_transactions_for_user
from app.core.security import get_current_user, require_owner
from app.optimizer.card_loader import CardKnowledgeBase
from app.optimizer.models import (
    CurrentCardROI,
    FeedbackStats,
    OptimizationReport,
    OptimizationRequest,
    RecommendationFeedbackRequest,
    RecommendationFeedbackResponse,
)
from app.optimizer.opportunity_cost import OpportunityCostCalculator
from app.optimizer.profiler import ConsumptionProfiler
from app.optimizer.promotion_tracker import PromotionTracker
from app.optimizer.queries import (
    INSIGHT_DETECTOR,
    find_insight_in_report,
    get_feedback_stats,
    get_feedback_weights,
    get_global_feedback_weights,
    get_user_feedback_weights,
    get_optimization_report_by_id,
    get_optimization_reports,
    save_recommendation_feedback,
)
from app.optimizer.services.optimizer_service import OptimizerService
from app.optimizer.simulator import CardSimulator
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/optimizer", tags=["Optimizer (F2)"])


@router.post("/analyze", response_model=OptimizationReport)
def analyze_cards(
    request: OptimizationRequest,
    current_user: str = Depends(get_current_user),
) -> OptimizationReport:
    """
    Analisa os gastos do usuário e recomenda o melhor cartão de crédito.
    
    1. Requer `user_id` e opcionalmente `safe_to_spend` ou `monthly_income`.
    2. Puxa as transações limpas da F1 (Nexa Core Engine).
    3. Simula o retorno matemático e aplica regras de risco e elegibilidade.
    4. Retorna um relatório completo detalhando por que cada cartão é (ou não) recomendado.
    """
    if current_user != request.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    logger.info("[API] Solicitando otimização de cartões para user_id=%s", request.user_id)
    
    try:
        transactions_df = get_transactions_for_user(request.user_id)
        if transactions_df.is_empty():
            logger.warning("[API] Sem transações para user=%s. Usando DataFrame vazio.", request.user_id)
            transactions_df = pl.DataFrame(schema={
                "date": pl.Date, "amount": pl.Float64, "description": pl.Utf8,
                "category": pl.Utf8, "pf_pj_label": pl.Utf8, "type": pl.Utf8
            })

        # Shadow invoices — obrigações futuras projetadas (assinaturas + parcelamentos).
        # Alimentam committed_percentage no profiler, melhorando o cálculo de liquidity risk.
        shadow_invoices_df: pl.DataFrame | None = None
        try:
            from app.subscriptions.shadow_invoices.runner import run_shadow_invoice_detection
            txns_for_shadow = transactions_df
            if "date" in transactions_df.columns and "transaction_date" not in transactions_df.columns:
                txns_for_shadow = transactions_df.rename({"date": "transaction_date"})
            shadow_invoices_df = run_shadow_invoice_detection(txns_for_shadow)
            logger.info("[API] shadow_invoices=%d eventos para user=%s", len(shadow_invoices_df), request.user_id)
        except Exception as shadow_exc:
            logger.debug("[API] shadow_invoice indisponível para user=%s: %s", request.user_id, shadow_exc)

        # GoalContext — aportes mensais nas metas ativas comprometem margem como obrigação futura.
        if request.monthly_goals_commitment == 0.0 and request.user_id:
            try:
                from app.goals.tracker import GoalTracker
                from app.core.db.session import get_db_session
                with get_db_session() as db:
                    active_goals = GoalTracker(db).list_goals(request.user_id, status="ACTIVE")
                commitment = sum(
                    (g.monthly_contribution_needed or 0.0) for g in active_goals
                )
                if commitment > 0:
                    request = request.model_copy(update={"monthly_goals_commitment": commitment})
                    logger.info("[API] monthly_goals_commitment=R$%.0f para user=%s", commitment, request.user_id)
            except Exception as goal_exc:
                logger.debug("[API] GoalTracker indisponível para optimizer user=%s: %s", request.user_id, goal_exc)

        # Contexto da F1 quando o cliente não manda: o modelo prometia
        # "safe_to_spend injetado pela rota via F1" e a rota nunca injetava —
        # o botão "Rodar análise completa" voltava 400 "informe safe_to_spend
        # ou monthly_income" para quem não tinha aberto outra aba antes.
        if request.safe_to_spend is None and request.monthly_income is None:
            request = request.model_copy(update=_contexto_da_f1(request.user_id, transactions_df))

        service = OptimizerService()

        report = service.analyze(
            request=request,
            transactions_df=transactions_df,
            shadow_invoices_df=shadow_invoices_df,
        )

        # Construir dicionário serializável e adicionar campos legados
        try:
            resp = report.model_dump()
        except Exception:
            # Caso report já seja dict
            resp = dict(report)
        try:
            resp["recommended_cards"] = [c.card_id for c in (report.all_cards or [])][:3]
        except Exception:
            resp["recommended_cards"] = []
        # Estimate a lightweight confidence_score for backward compatibility
        try:
            conf = 0.5
            if resp.get("all_cards") and len(resp.get("all_cards", [])) >= 3:
                conf += 0.2
            if "pluggy" in resp.get("data_sources", []):
                conf += 0.1
            if resp.get("user_profile_summary", {}).get("monthly_avg_spend", 0) > 0:
                conf += 0.1
            resp["confidence_score"] = round(min(1.0, conf), 2)
        except Exception:
            resp["confidence_score"] = 0.5

        return JSONResponse(content=jsonable_encoder(resp))

    except ValueError as ve:
        logger.error("[API] Erro de validação na otimização: %s", ve)
        raise HTTPException(status_code=400, detail=str(ve))
    
    except Exception as e:
        logger.error("[API] Erro interno durante otimização: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao processar a otimização de cartões.")

def _contexto_da_f1(user_id: str, transactions_df: pl.DataFrame) -> dict:
    """safe_to_spend (o do /forecast) e renda estimada, quando disponíveis."""
    contexto: dict = {}
    try:
        from app.runner import get_runner, safe_to_spend_total

        sts = safe_to_spend_total(get_runner().run_from_db(user_id=user_id, horizon_days=30))
        if sts is not None and sts >= 0:
            contexto["safe_to_spend"] = sts
    except Exception as exc:
        logger.debug("[API] safe_to_spend da F1 indisponível para %s: %s", user_id, exc)
    renda = _renda_estimada(transactions_df)
    if renda:
        contexto["monthly_income"] = renda
    return contexto


def _renda_estimada(transactions_df: pl.DataFrame) -> float | None:
    """Renda mensal líquida pelo extrato (confiança ≥ 0,5), ou None."""
    try:
        from app.forecast.etl.income_profiler import IncomeProfiler

        if not transactions_df.is_empty():
            perfil = IncomeProfiler().build(transactions_df)
            if perfil.confidence >= 0.5 and perfil.monthly_net_income > 0:
                return float(perfil.monthly_net_income)
    except Exception as exc:
        logger.debug("[API] renda estimada indisponível: %s", exc)
    return None


def _json_ou_lista(valor):
    """warnings/data_sources são gravados como texto JSON; a lista os devolvia crus."""
    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except ValueError:
            return [valor] if valor else []
    return valor if valor is not None else []


@router.get("/reports/{user_id}")
def list_user_reports(user_id: str = Depends(require_owner)):
    """Retorna o histórico resumido de otimizações de um usuário."""
    reports = get_optimization_reports(user_id)
    for r in reports:
        for campo in ("warnings", "data_sources"):
            if campo in r:
                r[campo] = _json_ou_lista(r[campo])
    return {"reports": reports}

@router.get("/reports/{report_id}/detail")
def get_report_detail(
    report_id: str,
    current_user: str = Depends(get_current_user),
):
    """Retorna os detalhes completos de um relatório gerado."""
    report = get_optimization_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    if report.get("user_id") != current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    return report

@router.get("/cards")
def list_available_cards():
    """Lista todos os cartões disponíveis na base de conhecimento do Nexa."""
    loader = CardKnowledgeBase()
    try:
        cards = loader.load()
        return {"total": len(cards), "cards": [c.model_dump() for c in cards]}
    except Exception as e:
        logger.error("[API] Erro ao carregar cartões: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao carregar base de cartões.")

@router.get("/opportunity-cost")
def get_opportunity_cost(
    current_card_id: str,
    months: int = 3,
    user_id: str = Depends(require_owner),
):
    """
    Calcula quanto o usuário deixou de ganhar por usar o cartão atual
    em vez dos melhores disponíveis na base.

    **Parâmetros:**
    - `user_id`: ID do usuário
    - `current_card_id`: ID do cartão que o usuário usa hoje
    - `months`: Janela de análise em meses (padrão: 3)

    **Retorna:**
    ```json
    {
      "current_card_name": "Nubank Roxinho",
      "period_months": 3,
      "total_spent": 9600.0,
      "current_card_reward_value": 48.0,
      "best_opportunity": {
        "card_name": "C6 Carbon",
        "difference": 144.0,
        "difference_annualized": 576.0,
        "explanation": "Nos últimos 3 meses você gastou R$ 9.600..."
      },
      "opportunities": [...]
    }
    ```
    """
    try:
        transactions_df = get_transactions_for_user(user_id)

        if transactions_df.is_empty():
            raise HTTPException(status_code=404, detail=f"Sem histórico para user_id={user_id}")

        # Montar perfil de consumo
        profile = ConsumptionProfiler().build(transactions_df=transactions_df)

        # Carregar todos os cartões
        all_cards = CardKnowledgeBase().load()

        # Localizar cartão atual
        current_card = next((c for c in all_cards if c.card_id == current_card_id), None)
        if current_card is None:
            raise HTTPException(
                status_code=404,
                detail=f"Cartão '{current_card_id}' não encontrado na base de conhecimento."
            )

        # Candidatos = todos exceto o atual — e só os que o usuário pode
        # contratar: sem o filtro, o "melhor" podia ser um cartão de renda
        # mínima R$ 20 mil para quem ganha R$ 4 mil.
        candidates = [c for c in all_cards if c.card_id != current_card_id]
        renda_mensal = _renda_estimada(transactions_df)
        if renda_mensal:
            elegiveis = {c.card_id for c in CardKnowledgeBase().filter_eligible(annual_income=renda_mensal * 12)}
            candidates = [c for c in candidates if c.card_id in elegiveis]

        report = OpportunityCostCalculator().calculate(
            profile=profile,
            current_card=current_card,
            candidate_cards=candidates,
            months=months,
        )

        return report.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[API] Erro ao calcular custo de oportunidade: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao calcular custo de oportunidade.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# M2.2 — Estratégia Multi-Cartão ("Carteira ideal")
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class _CardAssignmentResponse(_BaseModel):
    card_id: str
    card_name: str
    issuer: str
    card_type: str
    assigned_categories: list[str]
    monthly_spend_directed: float
    annual_return_from_this_card: float
    effective_annuity: float
    net_annual: float                    # annual_return - effective_annuity
    reason: str
    request_link: Optional[str] = None


class _CardPortfolioResponse(_BaseModel):
    user_id: str
    total_cards: int
    total_annual_return: float
    total_annuity_cost: float
    net_annual_gain: float
    vs_single_best: float                # ganho adicional vs melhor cartão único
    single_best_net_gain: float          # referência: retorno do melhor cartão único
    cards: list[_CardAssignmentResponse]
    explanation: str
    data_quality: str                    # "OK" | "INSUFFICIENT_DATA" | "NO_TRANSACTIONS"
    generated_at: str


@router.get("/portfolio/{user_id}", response_model=_CardPortfolioResponse)
def get_card_portfolio(
    user_id: str = Depends(require_owner),
    max_cards: int = Query(default=3, ge=1, le=5, description="Máximo de cartões na carteira"),
    monthly_income: Optional[float] = Query(default=None, description="Renda mensal (R$) para cálculo de elegibilidade"),
):
    """
    Calcula a carteira ideal de cartões para o perfil de gastos do usuário.

    Usa um algoritmo greedy por categoria: para cada categoria de gasto
    (Alimentação, Transporte, etc.) elege o cartão com maior retorno,
    depois consolida até `max_cards` cartões e compara com o melhor cartão único.

    **Parâmetros:**
    - `user_id`: ID do usuário
    - `max_cards`: Máximo de cartões na carteira (1–5, padrão: 3)
    - `monthly_income`: Renda mensal para elegibilidade (R$). Se omitido, estimado a partir das transações.

    **Exemplo de resposta:**
    ```json
    {
      "user_id": "user_123",
      "net_annual_gain": 1240.0,
      "vs_single_best": 480.0,
      "cards": [
        {
          "card_name": "Inter Black",
          "assigned_categories": ["Alimentação", "Mercado"],
          "annual_return_from_this_card": 720.0,
          "reason": "Melhor cashback em Alimentação (1.5%)"
        }
      ]
    }
    ```
    """
    from app.optimizer.multi_card_strategy import MultiCardStrategist  # lazy — evita circular import no startup

    logger.info("[API] Portfolio multi-cartão para user=%s max_cards=%d", user_id, max_cards)
    # ── 1. Buscar transações ────────────────────────────────────────
    try:
        transactions_df = get_transactions_for_user(user_id)
    except Exception as e:
        logger.error("[API] Erro ao buscar transações para portfolio: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao acessar dados do usuário.")

    data_quality = "OK"

    if transactions_df.is_empty():
        raise HTTPException(
            status_code=404,
            detail=f"Sem histórico de transações para user_id={user_id}. Envie dados via webhook primeiro."
        )

    if transactions_df.height < 10:
        data_quality = "INSUFFICIENT_DATA"

    # ── 2. Construir perfil de consumo ──────────────────────────────
    try:
        profile = ConsumptionProfiler().build(transactions_df=transactions_df)
    except Exception as e:
        logger.error("[API] Erro ao construir perfil de consumo: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao calcular perfil de consumo.")

    # ── 3. Determinar renda anual para elegibilidade ────────────────
    if monthly_income and monthly_income > 0:
        annual_income = monthly_income * 12
    elif profile.income_profile and profile.income_profile.confidence >= 0.5:
        annual_income = (profile.income_profile.monthly_net_income or 0) * 12
    else:
        annual_income = profile.estimated_monthly_income * 12

    # ── 4. Filtrar cartões elegíveis ────────────────────────────────
    try:
        kb = CardKnowledgeBase()
        eligible_cards = kb.filter_eligible(annual_income=annual_income)
    except Exception as e:
        logger.error("[API] Erro ao filtrar cartões: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao carregar base de cartões.")

    if not eligible_cards:
        raise HTTPException(
            status_code=422,
            detail="Nenhum cartão elegível para o perfil de renda informado."
        )

    # ── 5. Calcular carteira ideal ──────────────────────────────────
    try:
        portfolio = MultiCardStrategist().optimize_portfolio(
            profile=profile,
            eligible_cards=eligible_cards,
            max_cards=max_cards,
        )
    except Exception as e:
        logger.error("[API] Erro ao calcular portfólio: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao calcular carteira ideal.")

    # ── 6. Serializar resposta ──────────────────────────────────────
    card_responses = [
        _CardAssignmentResponse(
            card_id=a.card.card_id,
            card_name=a.card.name,
            issuer=a.card.issuer,
            card_type=a.card.card_type.value if hasattr(a.card.card_type, "value") else str(a.card.card_type),
            assigned_categories=a.assigned_categories,
            monthly_spend_directed=round(a.monthly_spend_directed, 2),
            annual_return_from_this_card=round(a.annual_return_from_this_card, 2),
            effective_annuity=round(a.effective_annuity, 2),
            net_annual=round(a.annual_return_from_this_card - a.effective_annuity, 2),
            reason=a.reason,
            request_link=a.card.request_link,
        )
        for a in portfolio.cards
    ]

    return _CardPortfolioResponse(
        user_id=user_id,
        total_cards=len(portfolio.cards),
        total_annual_return=portfolio.total_annual_return,
        total_annuity_cost=portfolio.total_annuity_cost,
        net_annual_gain=portfolio.net_annual_gain,
        vs_single_best=portfolio.vs_single_best,
        single_best_net_gain=portfolio.single_best_net_gain,
        cards=card_responses,
        explanation=portfolio.explanation,
        data_quality=data_quality,
        generated_at=_datetime.now().isoformat(),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# M2.4 — ROI do Cartão Atual ("Sua anuidade está se pagando?")
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/roi/{card_id}", response_model=CurrentCardROI)
def get_card_roi(
    card_id: str,
    user_id: str = Depends(require_owner),
    monthly_spend: Optional[float] = Query(
        default=None,
        description="Gasto mensal médio (R$). Se omitido, calculado a partir do histórico de transações."
    ),
):
    """
    M2.4 — Calcula se a anuidade do seu cartão atual está se pagando.

    Compara o valor gerado em pontos/cashback com a anuidade paga.
    Retorna diagnóstico, veredicto e explicação em linguagem natural.

    **Parâmetros:**
    - `card_id`: ID do cartão (ex: `nubank_roxinho`)
    - `user_id`: ID do usuário
    - `monthly_spend`: Opcional — gasto mensal. Se omitido, usa histórico real.
    """
    from dataclasses import replace as _replace

    # 1. Carregar o cartão
    all_cards = CardKnowledgeBase().load()
    card = next((c for c in all_cards if c.card_id == card_id), None)
    if card is None:
        raise HTTPException(
            status_code=404,
            detail=f"Cartão '{card_id}' não encontrado na base de conhecimento."
        )

    # 2. Montar perfil
    if monthly_spend is not None and monthly_spend > 0:
        profile = ConsumptionProfiler().build(pl.DataFrame())
        profile = _replace(profile, monthly_avg_spend=monthly_spend)
    else:
        try:
            transactions_df = get_transactions_for_user(user_id)
        except Exception as e:
            logger.error("[API] Erro ao buscar transações para ROI: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Erro ao acessar dados do usuário.")

        if transactions_df.is_empty():
            raise HTTPException(
                status_code=422,
                detail="Sem histórico. Informe 'monthly_spend' como parâmetro para calcular sem histórico.",
            )
        profile = ConsumptionProfiler().build(transactions_df=transactions_df)

    # 3. Calcular ROI
    try:
        roi = CardSimulator().calculate_current_card_roi(card=card, profile=profile)
    except Exception as e:
        logger.error("[API] Erro ao calcular ROI: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao calcular ROI do cartão.")

    return roi


# ─────────────────────────────────────────────────────────────────────────────
# Aprendizado com feedback — M2.8
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/recommendations/{recommendation_id}/feedback",
    response_model=RecommendationFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_recommendation_feedback(
    recommendation_id: str,
    body: RecommendationFeedbackRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Registra a resposta do usuário a um insight do relatório de otimização.

    **Outcomes:**
    - `ACCEPTED` — usuário vai executar a recomendação
    - `IGNORED`  — fechou sem interagir
    - `REJECTED` — marcou como irrelevante

    O feedback é associado ao `recommendation_id` (report_id retornado por
    `POST /optimizer/analyze`) e ao `insight_type` escolhido pelo cliente.
    Os sinais do perfil são extraídos automaticamente do relatório salvo.
    """
    report = get_optimization_report_by_id(recommendation_id)
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    if report.get("user_id") != current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    insight = find_insight_in_report(report, body.insight_id)
    if not insight:
        raise HTTPException(
            status_code=404,
            detail=f"Insight '{body.insight_id}' não encontrado neste relatório",
        )

    insight_type = insight.get("type", "")
    try:
        feedback_id = save_recommendation_feedback(
            recommendation_id=recommendation_id,
            user_id=current_user,
            insight_id=body.insight_id,
            insight_type=insight_type,
            outcome=body.outcome.value,
            reason=body.reason,
            insight_data=insight,
        )
    except Exception as e:
        logger.error("[API] Erro ao salvar feedback: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao registrar feedback")

    from datetime import datetime as _dt
    return RecommendationFeedbackResponse(
        feedback_id=feedback_id,
        recommendation_id=recommendation_id,
        insight_type=insight_type,
        detector=INSIGHT_DETECTOR.get(insight_type, "Unknown"),
        outcome=body.outcome.value,
        created_at=_dt.utcnow().isoformat(),
    )


@router.get("/feedback/stats", response_model=list[FeedbackStats])
def feedback_stats(
    insight_type: Optional[str] = None,
    detector: Optional[str] = None,
    current_user: str = Depends(get_current_user),
):
    """
    Retorna estatísticas de aceitação de insights agrupadas por (detector, insight_type).

    Útil para calibrar manualmente o ranking ou auditar quais recomendações
    os usuários mais aceitam ou rejeitam.
    """
    return get_feedback_stats(insight_type=insight_type, detector=detector)


@router.get("/feedback/weights")
def feedback_weights(current_user: str = Depends(get_current_user)):
    """
    Retorna os pesos finais por insight_type para o usuário autenticado.

    **Dois níveis combinados (multiplicados):**
    - `global_weights`: aprendido com todos os usuários — range [0.5, 1.5], floor ≥ 10 amostras.
    - `user_weights`: ajuste individual — range [0.75, 1.25], floor ≥ 5 amostras do usuário.
    - `final_weights`: `global × user` — aplicado ao priority_score no ranking.

    Se o usuário não tem dados suficientes, `user_weights` fica vazio e `final = global`.
    """
    global_w = get_global_feedback_weights()
    user_w   = get_user_feedback_weights(current_user)
    final_w  = get_feedback_weights(user_id=current_user)
    return {
        "user_id":       current_user,
        "global_weights": global_w,
        "user_weights":   user_w,
        "final_weights":  final_w,
    }



@router.get("/health")
def optimizer_health_check():
    """Health check do módulo Optimizer."""
    return {"status": "ok", "module": "optimizer"}


# ─────────────────────────────────────────────────────────────────────────────
# M2.6 — Alertas de Promoções de Transferência Bonificada
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/promotions")
def list_active_promotions(
    include_expired: bool = Query(default=False, description="Incluir promoções encerradas"),
):
    """
    M2.6 — Lista promoções de transferência de pontos em vigor.

    Retorna todas as promoções ativas (ou todas incluindo encerradas).
    Cada promoção inclui:
    - Programa de fidelidade fonte e parceiro destino
    - % de bônus e taxa efetiva por 1.000 pontos
    - Janela de vigência e dias restantes
    - Cartões elegíveis para participar

    **Exemplo de uso:**
    ```
    GET /optimizer/promotions
    GET /optimizer/promotions?include_expired=true
    ```
    """
    tracker = PromotionTracker()
    promotions = tracker.get_all_promotions(include_expired=include_expired)
    return {
        "total": len(promotions),
        "include_expired": include_expired,
        "promotions": [p.to_dict() for p in promotions],
    }


@router.get("/promotions/opportunities")
def check_promotion_opportunities(
    user_id: str = Query(..., description="ID do usuário"),
    cards: str = Query(
        default="",
        description="Cartões do usuário separados por vírgula (ex: 'Inter Black,Amex Gold')",
    ),
    points_balance: str = Query(
        default="",
        description="Saldo de pontos por programa no formato 'programa:quantidade' separados por vírgula "
                    "(ex: 'smiles:15000,livelo:8000')",
    ),
):
    """
    M2.6 — Identifica oportunidades de promoção vantajosas para o usuário.

    Recebe os cartões do usuário e seu saldo de pontos, e retorna alertas
    classificados pelo valor financeiro extra obtido ao aproveitar cada promoção.

    **Exemplo:**
    ```
    GET /optimizer/promotions/opportunities
        ?user_id=u1
        &cards=Inter Black,Amex Gold
        &points_balance=smiles:15000,livelo:8000
    ```

    **Resposta:**
    ```json
    {
      "alerted_count": 1,
      "opportunities": [
        {
          "user_card": "Inter Black",
          "extra_value": 272.0,
          "alert_text": "🔥 Promoção ativa: Smiles → GOL Smiles com 80% de bônus..."
        }
      ]
    }
    ```
    """
    # Parse dos query params
    user_cards: list[str] = [c.strip() for c in cards.split(",") if c.strip()]
    user_points: dict[str, int] = {}
    for item in points_balance.split(","):
        item = item.strip()
        if ":" in item:
            prog, qty = item.split(":", 1)
            try:
                user_points[prog.strip()] = int(qty.strip())
            except ValueError:
                pass

    if not user_cards:
        raise HTTPException(
            status_code=422,
            detail="Informe ao menos um cartão via parâmetro 'cards' (ex: 'Inter Black,Amex Gold').",
        )

    tracker = PromotionTracker()
    alerts = tracker.check_user_opportunities(
        user_cards=user_cards,
        user_points_balance=user_points,
    )

    return {
        "user_id": user_id,
        "user_cards": user_cards,
        "user_points_balance": user_points,
        "alerted_count": len(alerts),
        "opportunities": [a.to_dict() for a in alerts],
    }
