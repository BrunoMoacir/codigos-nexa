"""
app/api/v1/routes/architect.py - Endpoints da F3 (Nexa Architect)

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Expõe os endpoints REST do simulador de conquistas (F3).

ENDPOINTS:
  POST /architect/simulate                    Simula Financiamento vs Consórcio vs Poupar
  GET  /architect/simulations                 Histórico de simulações do usuário
  GET  /architect/simulations/{simulation_id} Detalhe de uma simulação específica
  GET  /architect/metrics                     Métricas agregadas do usuário
  GET  /architect/health                      Health check do módulo

╔══════════════════════════════════════════════════════════════════════╗
║ FLUXO: POST /architect/simulate                                      ║
╚══════════════════════════════════════════════════════════════════════╝

  1. Recebe SimulationRequest no body
  2. Tenta buscar safe_to_spend da F1 (NexaRunner) para o user_id
     → Se F1 indisponível, degradação graciosa (safe_to_spend=None)
  3. Chama ArchitectService.simulate(request, safe_to_spend)
     → InputValidator, Market Rates, StrategyEngine, LiquidityValidator
  4. Persiste o resultado no DuckDB (assíncrono + gracioso)
  5. Retorna SimulationResponse

╔══════════════════════════════════════════════════════════════════════╗
║ TRATAMENTO DE ERROS                                                  ║
╚══════════════════════════════════════════════════════════════════════╝

  ValueError (validação de negócio) → HTTP 422 Unprocessable Entity
  Exception inesperada              → HTTP 500 Internal Server Error
  Falha de persistência             → Ignorada (não bloqueia a resposta)
  Simulação não encontrada          → HTTP 404 Not Found
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status, Depends
from app.core.security import get_current_user
from pydantic import BaseModel, Field

from app.architect.models import SimulationRequest, SimulationResponse, TimingScenario
from app.architect.services.architect_service import ArchitectService
from app.architect.simulators.sensitivity_analyzer import SensitivityAnalyzer
from app.architect.queries import (
    get_simulation,
    get_user_latest_simulation,
    get_user_metrics,
    get_user_simulations,
    save_simulation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/architect", tags=["Architect — F3"])

# Instância singleton do service (stateless — conectores têm cache interno)
_service = ArchitectService()
_sensitivity_analyzer = SensitivityAnalyzer()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODELOS DE RESPOSTA — Endpoints de Histórico
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SimulationSummary(BaseModel):
    """
    Visão resumida de uma simulação — usada na listagem do histórico.

    Contém apenas os campos mais relevantes (sem os JSONs completos)
    para evitar payloads grandes na listagem.
    """
    id: str                          = Field(..., description="UUID da simulação")
    created_at: str                  = Field(..., description="Timestamp ISO 8601")
    target_amount: float             = Field(..., description="Meta financeira (R$)")
    asset_type: str                  = Field(..., description="Tipo do bem")
    recommended_strategy: str        = Field(..., description="Estratégia recomendada")
    confidence_score: float          = Field(..., description="Confiança [0, 1]")
    liquidity_impact: Optional[float] = Field(None, description="Impacto no caixa")
    months_to_achieve: Optional[int]  = Field(None, description="Prazo (meses)")
    expected_cost: Optional[float]    = Field(None, description="Custo esperado (R$)")


class UserMetricsResponse(BaseModel):
    """
    Métricas agregadas do usuário — para exibição em dashboard.

    Calculadas automaticamente a cada nova simulação (UPSERT).
    """
    user_id: str                          = Field(..., description="ID do usuário")
    total_simulations: int                = Field(..., description="Total de simulações")
    last_simulated_at: Optional[str]      = Field(None, description="Última simulação")
    first_simulated_at: Optional[str]     = Field(None, description="Primeira simulação")
    favorite_strategy: Optional[str]      = Field(None, description="Estratégia mais recomendada")
    avg_confidence_score: Optional[float] = Field(None, description="Confiança média")



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER: Buscar safe_to_spend da F1
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _fetch_safe_to_spend(user_id: str) -> Optional[float]:
    """
    Tenta buscar o safe_to_spend mensal da F1 para o usuário.

    Usa o mesmo padrão do forecast.py: NexaRunner em modo "dev".
    Em produção, será substituído por query direta ao Postgres
    com o último resultado de safe_to_spend calculado pela F1.

    Returns:
        safe_to_spend_total (R$/mês) ou None se F1 indisponível.
    """
    try:
        from app.runner import NexaRunner  # import tardio para evitar custo no startup

        import os
        from app.core.config import settings

        logger.info("architect | user=%s | buscando safe_to_spend da F1", user_id)

        mode = "prod" if os.getenv("APP_MODE", "dev") == "prod" else "dev"
        if mode == "prod" and (not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no backend/.env.",
            )

        runner = NexaRunner(mode=mode)
        result = runner.run(horizon_days=30)

        sts = result.get("safe_to_spend", {})
        value = sts.get("safe_to_spend_total")

        if value is not None and float(value) > 0:
            logger.info(
                "architect | user=%s | safe_to_spend=%.2f (F1 disponível)",
                user_id,
                float(value),
            )
            return float(value)

        logger.warning(
            "architect | user=%s | safe_to_spend da F1 retornou zero ou None",
            user_id,
        )
        return None

    except Exception as exc:
        logger.warning(
            "architect | user=%s | F1 indisponível (%s) — prosseguindo sem safe_to_spend",
            user_id,
            exc,
        )
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: POST /architect/simulate
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "/simulate",
    response_model=SimulationResponse,
    status_code=status.HTTP_200_OK,
    summary="Simular estratégias de aquisição",
    description=(
        "Compara **Financiamento**, **Consórcio** e **Poupar/Investir** "
        "para um bem de alto valor. Retorna a estratégia com menor custo "
        "presente (NPV) compatível com a liquidez do usuário."
    ),
)
async def simulate(request: SimulationRequest, current_user: str = Depends(get_current_user)) -> SimulationResponse:
    """
    Simula as 3 estratégias de aquisição e recomenda a melhor.

    **Inputs obrigatórios:**
    - `user_id`: ID do usuário (para buscar safe_to_spend da F1)
    - `target_amount`: Valor total do bem (R$)

    **Inputs opcionais com defaults razoáveis:**
    - `down_payment`: Entrada disponível (default: R$ 0)
    - `max_monthly_budget`: Orçamento mensal máximo (default: usa F1)
    - `asset_type`: Tipo do bem — IMOVEL, VEICULO, REFORMA, VIAGEM, OUTRO
    - `financing_months`: Prazo do financiamento (default: 48 meses)
    - `risk_profile`: conservador | moderado | agressivo
    - `include_consortium`: Incluir consórcio na comparação (default: true)

    **Retorna:**
    ```json
    {
      "recommended_strategy": "CONSORTIUM",
      "costs": {"min_cost": 98000, "expected_cost": 103400, "max_cost": 111000},
      "npv": {"financing": -105000, "consortium": -103400, "save_invest": -120000,
               "discount_rate_used": 0.00896},
      "liquidity_impact": -0.22,
      "months_to_achieve": 26,
      "action_plan": [...],
      "confidence_score": 0.91,
      "warnings": [],
      "data_sources": ["bacen", "anbima", "market_rates", "f1_safe_to_spend"]
    }
    ```

    **Erros:**
    - `422`: Request com regras de negócio inválidas (principal muito baixo, etc.)
    - `500`: Erro interno inesperado
    """
    if current_user != request.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    logger.info(
        "POST /architect/simulate | user=%s target=%.2f",
        request.user_id,
        request.target_amount,
    )

    # ── 1. Buscar safe_to_spend da F1 (degradação graciosa) ──────────
    safe_to_spend = await _fetch_safe_to_spend(request.user_id)

    # ── 2. Chamar o service ──────────────────────────────────────────
    try:
        response = _service.simulate(request, safe_to_spend=safe_to_spend)
        logger.info(
            "POST /architect/simulate | user=%s | estratégia=%s confidence=%.2f",
            request.user_id,
            response.recommended_strategy.value,
            response.confidence_score,
        )

        # ── 3. Persistir o resultado (falha silenciosa) ───────────────
        # A persistência NÃO bloqueia a resposta ao usuário.
        # Se o banco estiver indisponível ou sem migration, apenas
        # registramos no log e seguimos em frente.
        try:
            sim_id = save_simulation(
                user_id=request.user_id,
                request=request,
                response=response,
            )
            if sim_id:
                logger.info(
                    "POST /architect/simulate | persistida | id=%s", sim_id
                )
        except Exception as persist_exc:
            logger.warning(
                "POST /architect/simulate | falha ao persistir (não-crítico): %s",
                persist_exc,
            )

        return response

    except ValueError as exc:
        # Erro de validação de negócio → 422
        logger.warning(
            "POST /architect/simulate | user=%s | validação: %s",
            request.user_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    except Exception as exc:
        logger.error(
            "POST /architect/simulate | user=%s | erro inesperado: %s",
            request.user_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar simulação. Tente novamente.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /architect/health
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check do módulo Architect",
    tags=["Health"],
)
async def health():
    """
    Verifica se o módulo F3 está operacional.

    Retorna:
    ```json
    {"status": "ok", "module": "architect", "timestamp": "..."}
    ```
    """
    return {
        "status": "ok",
        "module": "architect",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /architect/simulations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/simulations",
    response_model=List[SimulationSummary],
    status_code=status.HTTP_200_OK,
    summary="Histórico de simulações do usuário",
    description=(
        "Retorna as últimas simulações realizadas pelo usuário, "
        "ordenadas da mais recente para a mais antiga. "
        "Suporta filtro por tipo de bem e paginação via `limit`."
    ),
)
async def list_simulations(
    user_id: str = Query(..., description="ID do usuário"),
    limit: int   = Query(
        default=10,
        ge=1,
        le=100,
        description="Número máximo de resultados (1–100)",
    ),
    asset_type: Optional[str] = Query(
        default=None,
        description="Filtrar por tipo de bem: IMOVEL, VEICULO, REFORMA, VIAGEM, OUTRO",
    ),
    current_user: str = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Lista o histórico de simulações de um usuário.

    **Parâmetros de query:**
    - `user_id` (obrigatório): ID do usuário
    - `limit` (opcional, default 10): Quantas simulações retornar
    - `asset_type` (opcional): Filtrar por IMOVEL, VEICULO, REFORMA, VIAGEM, OUTRO

    **Retorna:** lista de SimulationSummary (sem os JSONs completos de request/response)

    **Exemplo:**
    ```
    GET /api/v1/architect/simulations?user_id=user_123&limit=5&asset_type=VEICULO
    ```
    """
    if current_user != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    logger.info(
        "GET /architect/simulations | user=%s limit=%d asset_type=%s",
        user_id,
        limit,
        asset_type,
    )

    try:
        simulations = get_user_simulations(
            user_id=user_id,
            limit=limit,
            asset_type=asset_type,
        )
    except Exception as exc:
        logger.error(
            "GET /architect/simulations | user=%s | erro: %s", user_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar histórico de simulações.",
        )

    # Converter created_at para string ISO 8601 (pode ser datetime do DuckDB)
    result = []
    for sim in simulations:
        result.append({
            "id":                   sim["id"],
            "created_at":           _to_iso(sim["created_at"]),
            "target_amount":        sim["target_amount"],
            "asset_type":           sim["asset_type"],
            "recommended_strategy": sim["recommended_strategy"],
            "confidence_score":     sim["confidence_score"],
            "liquidity_impact":     sim.get("liquidity_impact"),
            "months_to_achieve":    sim.get("months_to_achieve"),
            "expected_cost":        sim.get("expected_cost"),
        })

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /architect/simulations/{simulation_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/simulations/{simulation_id}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Detalhe de uma simulação específica",
    description=(
        "Retorna todos os dados de uma simulação, incluindo o request e "
        "o response completos (JSON desserializado). Útil para replay e auditoria."
    ),
)
async def get_simulation_by_id(
    simulation_id: str,
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Retorna os dados completos de uma simulação pelo seu ID.

    Inclui os campos indexáveis e os JSONs completos de `request` e `response`.

    **Retorna HTTP 404** se o `simulation_id` não existir no banco.

    **Exemplo:**
    ```
    GET /api/v1/architect/simulations/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    logger.info("GET /architect/simulations/%s", simulation_id)

    try:
        sim = get_simulation(simulation_id)
    except Exception as exc:
        logger.error(
            "GET /architect/simulations/%s | erro: %s", simulation_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar simulação.",
        )

    if sim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulação '{simulation_id}' não encontrada.",
        )

    # Normalizar created_at para ISO 8601
    sim["created_at"] = _to_iso(sim["created_at"])
    return sim


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /architect/simulations/{simulation_id}/sensitivity
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/simulations/{simulation_id}/sensitivity",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Análise de sensibilidade de uma simulação",
    description=(
        "Analisa como variações nas variáveis-chave (**taxa de juros**, **prazo**, "
        "**entrada** e **CDI**) afetam o NPV de cada estratégia para uma simulação "
        "já realizada. Usa as taxas de mercado atuais. "
        "Retorna a variável mais sensível e o perfil de risco da recomendação."
    ),
)
async def get_sensitivity(
    simulation_id: str,
    _: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Executa análise de sensibilidade sobre os parâmetros de uma simulação existente.

    Reconstrói o request original a partir do banco, busca as taxas de mercado
    atuais e calcula como cada variável-chave afeta o NPV das 3 estratégias.

    **Variáveis analisadas:**
    - `interest_rate` — CET do financiamento: ±2 p.p. (9 pontos)
    - `months` — Prazo do financiamento: ±6 meses (7 pontos)
    - `down_payment` — Valor da entrada: ±10% (9 pontos)
    - `cdi_rate` — Taxa CDI (rendimento do investimento): ±2 p.p. (9 pontos)

    **Retorna:**
    ```json
    {
      "most_sensitive_variable": "cdi_rate",
      "strategy_stability": 1.0,
      "risk_profile": "baixo",
      "baseline_strategy": "SAVE_INVEST",
      "variables": [
        {
          "variable": "cdi_rate",
          "description": "Taxa CDI (Rendimento do Investimento)",
          "unit": "p.p.",
          "base_value": 0.1315,
          "npv_range": 2364.03,
          "elasticity": 118201.5,
          "strategy_flips": 0,
          "points": [
            {"delta": -0.02, "param_value": 0.1115, "npv_financing": -42000,
             "npv_invest": -40000, "npv_consortium": -45000, "recommended": "SAVE_INVEST"},
            ...
          ]
        }
      ],
      "generated_at": "2026-02-22T10:00:00"
    }
    ```

    **Retorna HTTP 404** se o `simulation_id` não existir no banco.

    **Exemplo:**
    ```
    GET /api/v1/architect/simulations/550e8400-e29b-41d4-a716-446655440000/sensitivity
    ```
    """
    logger.info("GET /architect/simulations/%s/sensitivity", simulation_id)

    # ── 1. Buscar simulação no banco ──────────────────────────────────────
    try:
        sim = get_simulation(simulation_id)
    except Exception as exc:
        logger.error(
            "GET /architect/simulations/%s/sensitivity | erro ao buscar: %s",
            simulation_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar simulação.",
        )

    if sim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulação '{simulation_id}' não encontrada.",
        )

    # ── 2. Reconstruir request e response a partir do JSON armazenado ────
    try:
        request = SimulationRequest.model_validate(sim["request"])
        response = SimulationResponse.model_validate(sim["response"])
    except Exception as exc:
        logger.error(
            "GET /architect/simulations/%s/sensitivity | erro ao reconstruir modelos: %s",
            simulation_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar dados da simulação.",
        )

    # ── 3. Buscar taxas de mercado atuais ─────────────────────────────────
    try:
        market_rates = _service.fetch_market_rates(request)
    except Exception as exc:
        logger.warning(
            "GET /architect/simulations/%s/sensitivity | erro ao buscar taxas: %s — usando fallback",
            simulation_id,
            exc,
        )
        # Fallback com taxas de referência para não bloquear a resposta
        market_rates = {
            "selic_annual":                0.1325,
            "cdi_annual":                  0.1315,
            "best_cet_annual":             0.1950,
            "consortium_admin_rate":        0.17,
            "consortium_months":            72.0,
            "consortium_reserve_fund_rate": 0.02,
        }

    # ── 4. Executar análise de sensibilidade ──────────────────────────────
    try:
        report = _sensitivity_analyzer.analyze(request, market_rates, response)
    except Exception as exc:
        logger.error(
            "GET /architect/simulations/%s/sensitivity | erro na análise: %s",
            simulation_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao calcular análise de sensibilidade.",
        )

    logger.info(
        "GET /architect/simulations/%s/sensitivity | variavel_critica=%s risco=%s estabilidade=%.2f",
        simulation_id,
        report.most_sensitive_variable,
        report.risk_profile,
        report.strategy_stability,
    )

    return report.to_dict()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /architect/metrics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/metrics",
    response_model=UserMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Métricas agregadas do usuário",
    description=(
        "Retorna estatísticas consolidadas de todas as simulações do usuário: "
        "total de simulações, estratégia favorita, confidence médio e timestamps."
    ),
)
async def get_metrics(
    user_id: str = Query(..., description="ID do usuário"),
    current_user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Retorna métricas agregadas de simulações do usuário.

    Calculadas e mantidas atualizadas automaticamente pelo banco
    (sem GROUP BY em tempo de request — O(1)).

    **Retorna HTTP 404** se o usuário não tiver nenhuma simulação.

    **Exemplo:**
    ```
    GET /api/v1/architect/metrics?user_id=user_123
    ```

    **Response:**
    ```json
    {
      "user_id": "user_123",
      "total_simulations": 7,
      "last_simulated_at": "2026-02-20T13:00:00+00:00",
      "favorite_strategy": "FINANCING",
      "avg_confidence_score": 0.84
    }
    ```
    """
    if current_user != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    logger.info("GET /architect/metrics | user=%s", user_id)

    try:
        metrics = get_user_metrics(user_id)
    except Exception as exc:
        logger.error(
            "GET /architect/metrics | user=%s | erro: %s", user_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar métricas do usuário.",
        )

    if metrics is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhuma simulação encontrada para o usuário '{user_id}'.",
        )

    return {
        "user_id":              metrics["user_id"],
        "total_simulations":    metrics["total_simulations"],
        "last_simulated_at":    _to_iso(metrics.get("last_simulated_at")),
        "first_simulated_at":   _to_iso(metrics.get("first_simulated_at")),
        "favorite_strategy":    metrics.get("favorite_strategy"),
        "avg_confidence_score": metrics.get("avg_confidence_score"),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER INTERNO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _to_iso(value: Any) -> Optional[str]:
    """
    Converte um valor de data/timestamp para string ISO 8601.

    O DuckDB pode retornar timestamps como objetos datetime Python
    ou como strings, dependendo da versão e do tipo da coluna.
    Esta função normaliza para string ISO 8601 em qualquer caso.

    Args:
        value: datetime, string ou None.

    Returns:
        String ISO 8601 ou None se value for None.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        # Garantir que está em UTC com timezone info
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    # Já é string (ex: DuckDB retornou como str)
    return str(value)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: POST /architect/timing-scenarios (M3.4)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "/timing-scenarios",
    response_model=List[TimingScenario],
    status_code=status.HTTP_200_OK,
    summary="M3.4 — E se eu esperar X meses?",
    description=(
        "Simula múltiplos cenários de timing: comprar agora vs esperar 3/6/12 meses "
        "acumulando mais entrada. Compara parcela, custo total (VPL) e economia "
        "para cada janela, incluindo nota de inflação."
    ),
)
async def timing_scenarios(
    request: SimulationRequest,
    monthly_savings: float = Query(
        ...,
        gt=0,
        description="Quanto o usuário pode poupar por mês durante a espera (R$)",
    ),
    wait_months: Optional[str] = Query(
        default=None,
        description="Janelas de espera separadas por vírgula. Ex: '0,3,6,12'. Padrão: 0,3,6,12",
    ),
    current_user: str = Depends(get_current_user),
) -> List[TimingScenario]:
    """
    Responde: *"E se eu esperar X meses antes de comprar?"*

    **Como usar:**
    - Envie o mesmo `SimulationRequest` do endpoint `/simulate` no body.
    - Passe `monthly_savings` como query parameter (o que economizará por mês).
    - Opcionalmente, customize `wait_months` (CSV). Padrão: `0,3,6,12`.

    **Retorna:** lista de `TimingScenario` com parcela, custo NPV e economia
    para cada janela de espera, incluindo frase comparativa.

    **Exemplo:**
    ```
    POST /api/v1/architect/timing-scenarios?monthly_savings=2000
    Body: {"user_id": "u1", "target_amount": 80000, "down_payment": 10000, ...}
    ```

    **Resposta:**
    ```json
    [
      {"wait_months": 0, "monthly_payment": 2800, "saving_vs_now": 0, "comparison_text": "Comprar agora..."},
      {"wait_months": 6, "monthly_payment": 2350, "saving_vs_now": 8400, "comparison_text": "Esperar 6 meses..."}
    ]
    ```
    """
    if current_user != request.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    logger.info(
        "POST /architect/timing-scenarios | user=%s target=%.2f savings=%.2f",
        request.user_id,
        request.target_amount,
        monthly_savings,
    )

    # Parsear janelas de espera customizadas
    if wait_months:
        try:
            scenarios = [int(w.strip()) for w in wait_months.split(",") if w.strip()]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="wait_months deve ser lista de inteiros separados por vírgula. Ex: '0,3,6,12'",
            )
    else:
        scenarios = [0, 3, 6, 12]

    # Buscar taxas de mercado
    try:
        market_rates = _service.fetch_market_rates(request)
    except Exception as exc:
        logger.warning("timing-scenarios | taxas indisponíveis: %s — usando fallback", exc)
        market_rates = {
            "selic_annual":    0.1325,
            "cdi_annual":      0.1325,
            "best_cet_annual": 0.20,
            "ipca_annual":     0.045,
        }

    # Executar simulações de timing
    try:
        from app.architect.simulators.strategy_engine import StrategyEngine
        engine = StrategyEngine()
        timing_results = engine.simulate_timing_scenarios(
            request=request,
            market_rates=market_rates,
            monthly_savings=monthly_savings,
            scenarios=scenarios,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("POST /architect/timing-scenarios | erro: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao calcular cenários de timing.",
        )

    logger.info(
        "POST /architect/timing-scenarios | user=%s | %d cenários gerados",
        request.user_id,
        len(timing_results),
    )
    return timing_results
