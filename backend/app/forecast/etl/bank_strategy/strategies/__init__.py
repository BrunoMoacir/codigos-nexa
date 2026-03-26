# app/etl/bank_strategy/strategies/__init__.py
"""
Strategies concretas por banco.

Uso:
    from app.forecast.etl.bank_strategy.strategies import NubankStrategy
"""

from .default import DefaultStrategy
from .nubank import NubankStrategy
from .inter import InterStrategy
from .itau import ItauStrategy

__all__ = [
    "DefaultStrategy",
    "NubankStrategy",
    "InterStrategy",
    "ItauStrategy",
]