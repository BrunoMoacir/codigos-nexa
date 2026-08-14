# app/etl/bank_strategy/registry.py

from app.core.schemas.enums import BankTier
from app.forecast.etl.bank_strategy.base import BankStrategy
from app.forecast.etl.bank_strategy.strategies.default import DefaultStrategy
from app.forecast.etl.bank_strategy.strategies.inter import InterStrategy
from app.forecast.etl.bank_strategy.strategies.itau import ItauStrategy
from app.forecast.etl.bank_strategy.strategies.nubank import NubankStrategy
from app.forecast.etl.bank_strategy.strategies.tiered import TieredStrategy

# Bancos com peculiaridade própria mapeada (quirks que exigem código).
_DEDICADAS = {
    "nubank": NubankStrategy,
    "itau": ItauStrategy,
    "inter": InterStrategy,
}

# Bancos reconhecidos pelo resolvedor de instituição, sem quirk próprio:
# recebem a TieredStrategy com o tier calibrado do enum BankTier.
# Fonte dos tiers: observação de produção documentada em enums.py.
_TIER_POR_BANCO = {
    # TIER_1 — excelentes
    "c6": BankTier.TIER_1,
    "btg": BankTier.TIER_1,
    # TIER_2 — bons
    "original": BankTier.TIER_2,
    "xp": BankTier.TIER_2,
    "safra": BankTier.TIER_2,
    "nomad": BankTier.TIER_2,
    "pluggy_sandbox": BankTier.TIER_2,
    # TIER_3 — legados problemáticos
    "bradesco": BankTier.TIER_3,
    "santander": BankTier.TIER_3,
    "caixa": BankTier.TIER_3,
    "banco_do_brasil": BankTier.TIER_3,
    "sicredi": BankTier.TIER_3,
    "sicoob": BankTier.TIER_3,
    "banrisul": BankTier.TIER_3,
    "brb": BankTier.TIER_3,
    "pan": BankTier.TIER_3,
    # TIER_4 — muito instáveis
    "picpay": BankTier.TIER_4,
    "mercadopago": BankTier.TIER_4,
    "pagbank": BankTier.TIER_4,
    "neon": BankTier.TIER_4,
    "will": BankTier.TIER_4,
}


def get_bank_strategy(bank_id: str) -> BankStrategy:
    bank_id = bank_id.lower()

    strategy_cls = _DEDICADAS.get(bank_id)
    if strategy_cls is not None:
        return strategy_cls(bank_id)

    tier = _TIER_POR_BANCO.get(bank_id)
    if tier is not None:
        return TieredStrategy(bank_id, tier)

    # Banco fora do radar: fallback conservador (DEGRADED, sem normalização).
    return DefaultStrategy(bank_id)
