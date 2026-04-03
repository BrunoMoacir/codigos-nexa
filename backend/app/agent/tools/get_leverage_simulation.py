# app/agent/tools/get_leverage_simulation.py
"""
Tool: get_leverage_simulation
Simula a estratégia de alavancagem patrimonial via consórcio (F3.5 — Nexa Architect).

Use SEMPRE que o usuário perguntar sobre:
- "Consigo comprar um imóvel sem gastar nada por mês?"
- "Vale a pena fazer consórcio maior e investir o surplus?"
- "Como alavanco patrimônio com imóvel e SELIC?"
- "O aluguel paga as parcelas do consórcio?"
- Qualquer estratégia de alavancagem imobiliária via consórcio
"""
from langchain_core.tools import tool
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@tool
def get_leverage_simulation(
    user_id: str,
    city: Optional[str] = None,
    neighborhood: Optional[str] = None,
    sqm: Optional[float] = None,
    asset_value: Optional[float] = None,
    monthly_rent: Optional[float] = None,
    consortium_months: int = 180,
    admin_rate: Optional[float] = None,
    annual_adjustment_rate: float = 0.0,
) -> str:
    """
    F3.5 — Simula a estratégia de alavancagem patrimonial via consórcio:
    entrar num consórcio com carta MAIOR que o imóvel, comprar o imóvel
    quando contemplado, investir o surplus (carta - imóvel) na SELIC e
    usar aluguel + rendimento para pagar as parcelas sem desembolso mensal.

    Testa automaticamente multiplicadores de 1.2x a 3.0x e encontra o ótimo.
    Se nenhum cenário fechar a conta, retorna o melhor parcial e a razão.

    DOIS MODOS DE USO:

    Modo 1 — Localização automática (recomendado):
        Informe city + neighborhood + sqm e a Nexa busca preço/m² e aluguel/m²
        da região (FipeZAP) e calcula tudo automaticamente.
        Ex: city="BH", neighborhood="Buritis", sqm=70

    Modo 2 — Valores explícitos:
        Informe asset_value e monthly_rent diretamente.
        Ex: asset_value=525000, monthly_rent=1750

    Use esta ferramenta quando o usuário perguntar:
    - "Consigo comprar imóvel sem gastar nada por mês?"
    - "Vale fazer consórcio maior, comprar, alugar e investir o troco?"
    - "Como alavanco patrimônio com imóvel + SELIC?"
    - "O aluguel cobre as parcelas do consórcio?"
    - "Quero comprar um apê de 80m² no Leblon — vale alavancar?"

    Args:
        user_id: ID do usuário (obrigatório).
        city: Cidade do imóvel (ex: "BH", "São Paulo", "RJ"). Para Modo 1.
        neighborhood: Bairro (ex: "Buritis", "Itaim Bibi"). Para Modo 1.
        sqm: Área em m² do imóvel (ex: 70). Para Modo 1.
        asset_value: Valor do imóvel em R$ (Modo 2 ou override do Modo 1).
        monthly_rent: Aluguel mensal estimado em R$ (Modo 2 ou override do Modo 1).
        consortium_months: Prazo do grupo de consórcio em meses (padrão: 180 = 15 anos).
        admin_rate: Taxa de administração do consórcio decimal (padrão: taxa real de mercado).
        annual_adjustment_rate: Reajuste anual da carta (ex: 0.04 para INCC, padrão: 0).
    """
    logger.info(
        "[Tool] get_leverage_simulation user=%s city=%s nbhd=%s sqm=%s asset=R$%s",
        user_id, city, neighborhood, sqm, asset_value,
    )
    try:
        from app.architect.calculators.leverage_optimizer import LeverageOptimizer
        from app.architect.connectors.real_estate import RealEstateDataConnector
        from app.architect.models import SimulationRequest, AssetType, RiskProfile
        from app.architect.services.architect_service import ArchitectService

        location_info = ""

        # ── Resolver asset_value e monthly_rent ─────────────────────────────
        if asset_value is None or monthly_rent is None:
            # Modo 1: buscar via localização
            if not city:
                return (
                    "Para simular a alavancagem preciso de pelo menos:\n"
                    "- city + neighborhood + sqm (ex: city='BH', neighborhood='Buritis', sqm=70)\n"
                    "- ou asset_value + monthly_rent diretamente"
                )

            re_connector = RealEstateDataConnector()
            loc = re_connector.get_location_data(city=city, neighborhood=neighborhood)

            if sqm and sqm > 0:
                if asset_value is None:
                    asset_value = loc["price_sqm"] * sqm
                if monthly_rent is None:
                    monthly_rent = loc["rent_sqm"] * sqm
            else:
                # Sem sqm: usa price_sqm e rent_sqm como base e informa o usuário
                return (
                    f"Encontrei dados para {city}"
                    + (f" / {neighborhood}" if neighborhood else "")
                    + f":\n"
                    f"  Preço médio: R$ {loc['price_sqm']:,.0f}/m²\n"
                    f"  Aluguel médio: R$ {loc['rent_sqm']:,.0f}/m²\n"
                    f"  Yield: {loc['rent_yield_annual']*100:.2f}% a.a.\n\n"
                    f"Para simular a alavancagem, informe a área do imóvel em m² (ex: sqm=70)."
                )

            nbhd_str = neighborhood or ""
            city_str = loc["city_normalized"].replace("_", " ").title()
            nbhd_display = nbhd_str.replace("_", " ").title() if nbhd_str else ""
            location_display = f"{nbhd_display + ', ' if nbhd_display else ''}{city_str}"
            fallback_note = "" if loc["fallback_level"] == "neighborhood" else (
                f" (dado para bairro não encontrado — usando média de {city_str})"
                if loc["fallback_level"] == "city"
                else " (dado nacional — cidade não encontrada)"
            )
            location_info = (
                f"Localização: {location_display}{fallback_note}\n"
                f"Fonte: FipeZAP fev/2026 | "
                f"R$ {loc['price_sqm']:,.0f}/m² venda | "
                f"R$ {loc['rent_sqm']:,.0f}/m² aluguel | "
                f"Yield {loc['rent_yield_annual']*100:.2f}% a.a.\n"
            )
        else:
            if city and neighborhood:
                location_info = f"Localização: {neighborhood}, {city}\n"

        # ── Buscar taxas de mercado ──────────────────────────────────────────
        request = SimulationRequest(
            user_id=user_id,
            target_amount=asset_value,
            asset_type=AssetType.IMOVEL,
            financing_months=consortium_months,
        )
        service = ArchitectService()
        market_rates = service.fetch_market_rates(request)

        selic_annual = market_rates.get("selic_annual", 0.1475)
        effective_admin = admin_rate if admin_rate is not None else market_rates.get("consortium_admin_rate", 0.18)
        effective_months = int(market_rates.get("consortium_months", consortium_months))

        # ── Executar otimizador ──────────────────────────────────────────────
        optimizer = LeverageOptimizer()
        result = optimizer.find_optimal(
            asset_value=asset_value,
            monthly_rent=monthly_rent,
            selic_annual=selic_annual,
            admin_rate=effective_admin,
            consortium_months=effective_months,
            annual_adjustment_rate=annual_adjustment_rate,
        )

        # ── Formatar saída ───────────────────────────────────────────────────
        sqm_str = f" ({sqm:.0f}m²)" if sqm else ""
        lines = [
            f"Simulação de Alavancagem Patrimonial — Imóvel R$ {asset_value:,.0f}{sqm_str}",
        ]
        if location_info:
            lines.append(location_info.strip())
        lines += [
            f"Aluguel estimado: R$ {monthly_rent:,.0f}/mês "
            f"(yield {result.rent_yield_monthly*100:.2f}%/mês = {result.rent_yield_annual*100:.1f}%/ano)",
            f"SELIC: {selic_annual*100:.1f}% a.a. | Admin consórcio: {effective_admin*100:.0f}% | Prazo: {effective_months} meses",
            "-" * 44,
        ]

        if result.is_viable:
            o = result.optimal
            lines += [
                "VIÁVEL — A operação se paga sozinha ✓",
                "",
                f"Carta de consórcio ideal: R$ {o.letter_value:,.0f}  ({o.multiplier}x o imóvel)",
                f"Surplus investido na SELIC: R$ {o.surplus_invested:,.0f}",
                "",
                "Fluxo mensal (mês 1):",
                f"  + Aluguel recebido:     R$ {o.monthly_rent_income:,.0f}",
                f"  + Rendimento SELIC:     R$ {o.monthly_selic_income_initial:,.0f}",
                f"  - Parcela consórcio:    R$ {o.monthly_payment:,.0f}",
                f"  = Saldo líquido:        R$ {o.monthly_net_initial:,.0f}",
                f"  Cobertura total:        {o.total_coverage_pct:.0f}% da parcela",
                "",
                f"Resultado ao final de {effective_months} meses:",
                f"  Imóvel quitado:          R$ {asset_value:,.0f}",
                f"  Saldo investido restante: R$ {max(o.final_invested_balance, 0):,.0f}",
                f"  Patrimônio total:         R$ {o.final_patrimony:,.0f}",
                f"  Desembolso do bolso:      R$ 0 (100% auto-sustentável)",
                "",
                result.recommendation,
            ]

            # Outros multiplicadores viáveis (top 2)
            others = [s for s in result.all_scenarios if s.is_self_sustaining and s.multiplier != o.multiplier]
            if others:
                top = sorted(others, key=lambda s: s.final_patrimony, reverse=True)[:2]
                lines += ["", "Outros multiplicadores viáveis:"]
                for s in top:
                    lines.append(
                        f"  {s.multiplier}x — carta R$ {s.letter_value:,.0f} | "
                        f"parcela R$ {s.monthly_payment:,.0f}/mês | "
                        f"patrimônio final R$ {s.final_patrimony:,.0f}"
                    )
        else:
            lines += [
                "NÃO VIÁVEL — Alavancagem não se sustenta neste cenário",
                "",
                f"Motivo: {result.rejection_reason}",
                "",
            ]
            if result.best_partial:
                p = result.best_partial
                lines += [
                    f"Melhor cenário parcial ({p.multiplier}x):",
                    f"  Carta: R$ {p.letter_value:,.0f} | Parcela: R$ {p.monthly_payment:,.0f}/mês",
                    f"  Cobertura: {p.total_coverage_pct:.0f}% da parcela (faltam {100-p.total_coverage_pct:.0f}%)",
                    f"  Déficit máximo: R$ {p.max_monthly_deficit:,.0f}/mês do seu bolso",
                    "",
                ]
            lines.append(result.recommendation)

        return "\n".join(lines)

    except ValueError as ve:
        return f"Dados insuficientes para simular alavancagem: {ve}"
    except Exception as e:
        logger.error("[Tool] get_leverage_simulation erro: %s", e, exc_info=True)
        return (
            "Não foi possível executar a simulação de alavancagem agora. "
            "Verifique os dados informados e tente novamente."
        )
