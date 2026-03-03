# app/api/v1/routes/optimizer.py
# Rotas REST da Funcionalidade 2: Nexa Optimizer

import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from app.optimizer.models import OptimizationRequest, OptimizationReport
from app.optimizer.services.optimizer_service import OptimizerService
import polars as pl

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/optimizer", tags=["Optimizer (F2)"])


@router.post("/analyze", response_model=OptimizationReport)
async def analyze_cards(
    request: OptimizationRequest,
    # db_conn is mocked or retrieved from dependencies ideally, but keeping it simple for now
) -> OptimizationReport:
    """
    Analisa os gastos do usuário e recomenda o melhor cartão de crédito.
    
    1. Requer `user_id` e opcionalmente `safe_to_spend` ou `monthly_income`.
    2. Puxa as transações limpas da F1 (Nexa Core Engine).
    3. Simula o retorno matemático e aplica regras de risco e elegibilidade.
    4. Retorna um relatório completo detalhando por que cada cartão é (ou não) recomendado.
    """
    logger.info(f"[API] Solicitando otimização de cartões para user_id={request.user_id}")
    
    try:
        from app.db.queries import get_connection
        import duckdb
        
        con = get_connection()
        try:
            transactions_df = con.execute(
                "SELECT * FROM transactions_clean WHERE user_id = ?", 
                [request.user_id]
            ).pl()
        except duckdb.CatalogException:
            # Fallback se a tabela da F1 ainda não existir
            logger.warning("[API] Tabela transactions_clean não encontrada. Usando DataFrame vazio.")
            transactions_df = pl.DataFrame(schema={
                "date": pl.Date, "amount": pl.Float64, "description": pl.Utf8,
                "category": pl.Utf8, "pf_pj_label": pl.Utf8, "type": pl.Utf8
            })
        finally:
            con.close()

        # O shadow_invoices_df real depende do runner completo da F1. 
        # Por enquanto, mantemos None; o profiler lida com isso perfeitamente.
        shadow_invoices_df = None

        service = OptimizerService()
        
        report = service.analyze(
            request=request,
            transactions_df=transactions_df,
            shadow_invoices_df=shadow_invoices_df
        )
        
        return report

    except ValueError as ve:
        # Erros de validação (regras de negócio)
        logger.error(f"[API] Erro de validação: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    
    except Exception as e:
        logger.error(f"[API] Erro interno durante otimização: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao processar a otimização de cartões.")

from app.db.queries.optimizer_queries import get_optimization_reports, get_optimization_report_by_id
from app.optimizer.card_loader import CardKnowledgeBase
from app.optimizer.opportunity_cost import OpportunityCostCalculator
from app.optimizer.profiler import ConsumptionProfiler

@router.get("/reports/{user_id}")
async def list_user_reports(user_id: str):
    """Retorna o histórico resumido de otimizações de um usuário."""
    reports = get_optimization_reports(user_id)
    return {"reports": reports}

@router.get("/reports/{report_id}/detail")
async def get_report_detail(report_id: str):
    """Retorna os detalhes completos de um relatório gerado."""
    report = get_optimization_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    return report

@router.get("/cards")
async def list_available_cards():
    """Lista todos os cartões disponíveis na base de conhecimento do Nexa."""
    loader = CardKnowledgeBase()
    try:
        cards = loader.load()
        return {"total": len(cards), "cards": [c.model_dump() for c in cards]}
    except Exception as e:
        logger.error(f"[API] Erro ao carregar cartões: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao carregar base de cartões.")

@router.get("/opportunity-cost")
async def get_opportunity_cost(
    user_id: str,
    current_card_id: str,
    months: int = 3,
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
        from app.db.queries import get_connection
        import duckdb

        con = get_connection()
        try:
            transactions_df = con.execute(
                "SELECT * FROM transactions_clean WHERE user_id = ?",
                [user_id]
            ).pl()
        except duckdb.CatalogException:
            logger.warning("[API] Tabela transactions_clean não encontrada.")
            raise HTTPException(status_code=404, detail="Dados do usuário não encontrados.")
        finally:
            con.close()

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

        # Candidatos = todos exceto o atual
        candidates = [c for c in all_cards if c.card_id != current_card_id]

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
        logger.error(f"[API] Erro ao calcular custo de oportunidade: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao calcular custo de oportunidade.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# M2.2 — Estratégia Multi-Cartão ("Carteira ideal")
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from pydantic import BaseModel as _BaseModel
from typing import Optional as _Optional
from datetime import datetime as _datetime


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
    request_link: _Optional[str] = None


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
async def get_card_portfolio(
    user_id: str,
    max_cards: int = Query(default=3, ge=1, le=5, description="Máximo de cartões na carteira"),
    monthly_income: _Optional[float] = Query(default=None, description="Renda mensal (R$) para cálculo de elegibilidade"),
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
    from app.optimizer.multi_card_strategy import MultiCardStrategist
    from app.db.queries import get_connection
    import duckdb

    logger.info(f"[API] Portfolio multi-cartão para user={user_id} max_cards={max_cards}")

    # ── 1. Buscar transações ────────────────────────────────────────
    try:
        con = get_connection()
        try:
            transactions_df = con.execute(
                "SELECT * FROM transactions_clean WHERE user_id = ?",
                [user_id]
            ).pl()
        except duckdb.CatalogException:
            raise HTTPException(status_code=404, detail="Dados do usuário não encontrados.")
        finally:
            con.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Erro ao buscar transações para portfolio: {e}", exc_info=True)
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
        logger.error(f"[API] Erro ao construir perfil de consumo: {e}", exc_info=True)
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
        logger.error(f"[API] Erro ao filtrar cartões: {e}", exc_info=True)
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
        logger.error(f"[API] Erro ao calcular portfólio: {e}", exc_info=True)
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


@router.get("/health")
async def optimizer_health_check():
    """Health check do módulo Optimizer."""
    return {"status": "ok", "module": "optimizer"}
