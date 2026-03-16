# app/agent/tools/get_timing_scenarios.py
"""
Tool: get_timing_scenarios
Simula o impacto de esperar X meses antes de comprar um bem (M3.4 — Nexa Architect).

Use SEMPRE que o usuário perguntar sobre:
- "Vale a pena esperar para comprar?"
- "E se eu juntar mais entrada antes de financiar?"
- "Quanto economizo esperando 6 meses?"
- Comparações de timing: comprar agora vs. esperar 3/6/12 meses
"""
from langchain_core.tools import tool
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@tool
def get_timing_scenarios(
    user_id: str,
    target_amount: float,
    monthly_savings: float,
    down_payment: float = 0.0,
    asset_type: str = "OUTRO",
    financing_months: int = 48,
    risk_profile: str = "moderado",
    wait_months: Optional[str] = None,
) -> str:
    """
    M3.4 — Simula e compara o impacto financeiro de esperar X meses antes de comprar
    um bem, acumulando mais entrada ao longo do tempo.

    Para cada janela de espera, calcula:
    - Entrada acumulada (original + poupança mensal × meses)
    - Novo principal financiado (reduzido pela entrada maior)
    - Parcela mensal resultante
    - Custo total e NPV do cenário
    - Economia (ou custo extra) vs. comprar agora

    Use esta ferramenta quando o usuário perguntar:
    - "Vale a pena esperar 6 meses para juntar mais entrada?"
    - "Se eu poupar R$ 1.000/mês, quando compensa financiar?"
    - "Compro agora ou espero para ter entrada maior?"
    - "Quanto economizo esperando 3, 6 ou 12 meses?"

    Args:
        user_id: ID do usuário (obrigatório).
        target_amount: Valor total do bem em R$ (obrigatório).
        monthly_savings: Quanto o usuário pode poupar por mês durante a espera em R$ (obrigatório).
        down_payment: Entrada já disponível em R$ (padrão: 0).
        asset_type: Tipo de bem — IMOVEL, VEICULO, REFORMA, VIAGEM ou OUTRO (padrão: OUTRO).
        financing_months: Prazo do financiamento em meses (padrão: 48).
        risk_profile: Perfil de risco — conservador, moderado ou agressivo (padrão: moderado).
        wait_months: Janelas de espera separadas por vírgula. Ex: "0,3,6,12" (padrão: 0,3,6,12).
    """
    logger.info(
        "[Tool] get_timing_scenarios user=%s target=R$%.0f savings=R$%.0f/mês",
        user_id, target_amount, monthly_savings,
    )
    try:
        from app.architect.models import SimulationRequest, AssetType, RiskProfile
        from app.architect.services.architect_service import ArchitectService
        from app.architect.simulators.strategy_engine import StrategyEngine

        # Mapear enums
        asset_map = {
            "IMOVEL": AssetType.IMOVEL,
            "VEICULO": AssetType.VEICULO,
            "REFORMA": AssetType.REFORMA,
            "VIAGEM": AssetType.VIAGEM,
        }
        asset_enum = asset_map.get(asset_type.upper(), AssetType.OUTRO)

        risk_map = {
            "conservador": RiskProfile.CONSERVADOR,
            "agressivo": RiskProfile.AGRESSIVO,
        }
        risk_enum = risk_map.get(risk_profile.lower(), RiskProfile.MODERADO)

        # Parsear janelas de espera
        if wait_months:
            try:
                scenarios = [int(w.strip()) for w in wait_months.split(",") if w.strip()]
            except ValueError:
                scenarios = [0, 3, 6, 12]
        else:
            scenarios = [0, 3, 6, 12]

        request = SimulationRequest(
            user_id=user_id,
            target_amount=target_amount,
            down_payment=down_payment,
            asset_type=asset_enum,
            financing_months=financing_months,
            risk_profile=risk_enum,
        )

        # Buscar taxas de mercado via ArchitectService
        service = ArchitectService()
        market_rates = service.fetch_market_rates(request)

        # Executar simulação de timing
        engine = StrategyEngine()
        results = engine.simulate_timing_scenarios(
            request=request,
            market_rates=market_rates,
            monthly_savings=monthly_savings,
            scenarios=scenarios,
        )

        if not results:
            return "Não foi possível calcular os cenários de timing com os dados informados."

        asset_label = asset_type.upper() if asset_type.upper() in asset_map else "Bem"
        lines = [
            f"Análise de Timing — {asset_label} R$ {target_amount:,.0f}",
            f"Poupança mensal durante espera: R$ {monthly_savings:,.0f}/mês",
            "-" * 40,
        ]

        for s in results:
            if s.wait_months == 0:
                lines.append(f"Comprar AGORA:")
            else:
                lines.append(f"Esperar {s.wait_months} meses:")

            lines.append(f"  Entrada acumulada: R$ {s.accumulated_down_payment:,.0f}")
            lines.append(f"  Principal financiado: R$ {s.new_principal:,.0f}")
            lines.append(f"  Parcela mensal: R$ {s.monthly_payment:,.2f}")
            lines.append(f"  Custo total esperado: R$ {s.total_cost_expected:,.0f}")

            if s.wait_months > 0:
                if s.saving_vs_now > 0:
                    lines.append(f"  Economia vs agora: R$ {s.saving_vs_now:,.0f} (VPL)")
                elif s.saving_vs_now < 0:
                    lines.append(f"  Custo extra vs agora: R$ {abs(s.saving_vs_now):,.0f} (VPL)")
                else:
                    lines.append(f"  Sem diferença significativa vs agora")

            lines.append(f"  {s.comparison_text}")
            lines.append("")

        # Recomendar o melhor cenário (maior economia)
        best = max(results, key=lambda s: s.saving_vs_now)
        if best.wait_months == 0:
            lines.append("Recomendação: Comprar agora é a opção com melhor custo-benefício.")
        else:
            lines.append(
                f"Recomendação: Esperar {best.wait_months} meses oferece a melhor relação "
                f"custo-benefício — economia de R$ {best.saving_vs_now:,.0f} em valor presente."
            )

        return "\n".join(lines)

    except ValueError as ve:
        return f"Dados insuficientes para calcular os cenários: {ve}"
    except Exception as e:
        logger.error("[Tool] get_timing_scenarios erro: %s", e, exc_info=True)
        return (
            "Não foi possível calcular os cenários de timing agora. "
            "Verifique os dados informados e tente novamente."
        )
