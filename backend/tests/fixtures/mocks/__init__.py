"""
Mocks de bancos para testes.
"""

from .factory import simulate_bank
from .itau import mock_itau, map_itau
from .nubank import mock_nubank, map_nubank
from .bb import mock_bb, map_bb

__all__ = [
    "simulate_bank",
    "mock_itau",
    "map_itau",
    "mock_nubank",
    "map_nubank",
    "mock_bb",
    "map_bb",
]