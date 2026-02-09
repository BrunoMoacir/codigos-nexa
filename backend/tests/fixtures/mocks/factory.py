#backend/app/simulations/factory.py
from .itau import mock_itau, map_itau
from .nubank import mock_nubank, map_nubank
from .bb import mock_bb, map_bb


def simulate_bank(bank: str):
    bank = bank.lower()

    if bank == "itau":
        return map_itau(mock_itau())

    if bank == "nubank":
        return map_nubank(mock_nubank())

    if bank == "bb":
        return map_bb(mock_bb())

    raise ValueError("Banco não suportado")
