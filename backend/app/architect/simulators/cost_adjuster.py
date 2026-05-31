"""
app/architect/simulators/cost_adjuster.py - Ajustes de custo de propriedade

Extraído de StrategyEngine para separar a lógica de custo de posse
do orquestrador de simulação.
"""

from app.architect.models import AssetType


def compute_maintenance_cost(
    asset_type: AssetType, target_amount: float, months: int
) -> float:
    """
    Custo total de manutenção ao longo do período de posse (R$).

    IMOVEL  → 1% do valor do imóvel por ano (reparos, pequenos consertos).
    VEICULO → R$ 1.000/ano (revisões, pneus, imprevistos).
    Outros  → 0.
    """
    if asset_type == AssetType.IMOVEL:
        annual = target_amount * 0.01
    elif asset_type == AssetType.VEICULO:
        annual = 1000.0
    else:
        return 0.0
    return round(annual * (months / 12), 2)
