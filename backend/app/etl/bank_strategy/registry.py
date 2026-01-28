# app/etl/bank_strategy/registry.py

from app.etl.bank_strategy.strategies.default import DefaultStrategy
from app.etl.bank_strategy.strategies.nubank import NubankStrategy
from app.etl.bank_strategy.strategies.itau import ItauStrategy
from app.etl.bank_strategy.strategies.inter import InterStrategy
from app.etl.bank_strategy.base import BankStrategy


def get_bank_strategy(bank_id: str) -> BankStrategy:
    bank_id = bank_id.lower()

    registry = {
        "nubank": NubankStrategy,
        "itau": ItauStrategy,
        "inter": InterStrategy,
    }

    strategy_cls = registry.get(bank_id, DefaultStrategy)
    return strategy_cls(bank_id)
