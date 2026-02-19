"""
app/api/v1/routes/architect.py - Endpoints da F3 (Nexa Architect)

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Expõe os endpoints REST do simulador de conquistas (F3).

ENDPOINTS:
  POST /architect/simulate          Simula Financiamento vs Consórcio vs Poupar
  GET  /architect/health            Health check do módulo

╔══════════════════════════════════════════════════════════════════════╗
║ FLUXO: POST /architect/simulate                                      ║
╚══════════════════════════════════════════════════════════════════════╝

  1. Recebe SimulationRequest no body
  2. Tenta buscar safe_to_spend da F1 (NexaRunner) para o user_id
     → Se F1 indisponível, degradação graciosa (safe_to_spend=None)
  3. Chama ArchitectService.simulate(request, safe_to_spend)
     → InputValidator, Market Rates, StrategyEngine, LiquidityValidator
  4. Retorna SimulationResponse

╔══════════════════════════════════════════════════════════════════════╗
║ TRATAMENTO DE ERROS                                                  ║
╚══════════════════════════════════════════════════════════════════════╝

  ValueError (validação de negócio) → HTTP 422 Unprocessable Entity
  Exception inesperada              → HTTP 500 Internal Server Error
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status

from app.architect.models import SimulationRequest, SimulationResponse
from app.architect.services.architect_service import ArchitectService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/architect", tags=["Architect — F3"])

# Instância singleton do service (stateless — conectores têm cache interno)
_service = ArchitectService()


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

        logger.info("architect | user=%s | buscando safe_to_spend da F1", user_id)
        runner = NexaRunner(mode="dev")
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
async def simulate(request: SimulationRequest) -> SimulationResponse:
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
