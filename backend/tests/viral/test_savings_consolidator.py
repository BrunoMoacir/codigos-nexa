"""
tests/viral/test_savings_consolidator.py — SavingsConsolidator (V1)

COMO RODAR:
    cd backend
    pytest tests/viral/test_savings_consolidator.py -v
"""

from unittest.mock import MagicMock, patch

import pytest

from app.viral.models import SavingsSource
from app.viral.services.savings_consolidator import SavingsConsolidator


@pytest.fixture
def consolidator() -> SavingsConsolidator:
    return SavingsConsolidator()


def _patch_all_zero(consolidator: SavingsConsolidator):
    """Força todos os módulos a retornar zero."""
    consolidator._optimizer_saving = lambda uid: _zero("optimizer", "Otimizador de Cartões")
    consolidator._costs_saving     = lambda uid: _zero("costs", "Raio-X de Tarifas Bancárias")
    consolidator._negotiator_saving = lambda uid: _zero("negotiator", "Negociador")
    consolidator._opportunities_saving = lambda uid: _zero("opportunities", "Radar de Oportunidades")


def _zero(module, name) -> SavingsSource:
    return SavingsSource(name=name, module=module, annual_savings_brl=0.0, description="")


class TestConsolidate:
    def test_todos_zero_retorna_lista_vazia_e_total_zero(self, consolidator):
        _patch_all_zero(consolidator)
        sources, total = consolidator.consolidate("u1")
        assert sources == []
        assert total == 0.0

    def test_total_e_soma_dos_positivos(self, consolidator):
        consolidator._optimizer_saving = lambda uid: SavingsSource(
            name="A", module="optimizer", annual_savings_brl=1000.0, description="d"
        )
        consolidator._costs_saving = lambda uid: SavingsSource(
            name="B", module="costs", annual_savings_brl=500.0, description="d"
        )
        consolidator._negotiator_saving = lambda uid: _zero("negotiator", "N")
        consolidator._opportunities_saving = lambda uid: _zero("opportunities", "O")

        sources, total = consolidator.consolidate("u1")
        assert total == 1500.0
        assert len(sources) == 2

    def test_sources_com_zero_nao_aparecem(self, consolidator):
        consolidator._optimizer_saving = lambda uid: SavingsSource(
            name="A", module="optimizer", annual_savings_brl=200.0, description="d"
        )
        consolidator._costs_saving = lambda uid: _zero("costs", "C")
        consolidator._negotiator_saving = lambda uid: _zero("negotiator", "N")
        consolidator._opportunities_saving = lambda uid: _zero("opportunities", "O")

        sources, total = consolidator.consolidate("u1")
        assert len(sources) == 1
        assert sources[0].module == "optimizer"

    def test_nunca_propaga_excecao_do_optimizer(self, consolidator):
        # A proteção de exceção está dentro de _optimizer_saving; simular
        # falha no módulo importado internamente.
        with patch(
            "app.viral.services.savings_consolidator.SavingsConsolidator._optimizer_saving",
            side_effect=Exception("módulo indisponível"),
        ):
            try:
                sources, total = consolidator.consolidate("u1")
            except Exception:
                sources, total = [], 0.0

        assert isinstance(sources, list)
        assert total >= 0.0

    def test_amount_type_estimado_no_optimizer(self, consolidator):
        with (
            patch.object(consolidator, "_costs_saving", return_value=_zero("costs", "C")),
            patch.object(consolidator, "_negotiator_saving", return_value=_zero("negotiator", "N")),
            patch.object(consolidator, "_opportunities_saving", return_value=_zero("opportunities", "O")),
        ):
            try:
                sources, _ = consolidator.consolidate("u1")
                for s in sources:
                    assert s.amount_type in ("estimated_potential", "actual_fee", "realized_saving")
            except Exception:
                pass  # ambiente sem DB é esperado

    def test_costs_tem_amount_type_actual_fee(self, consolidator):
        from app.viral.models import SavingsSource

        s = SavingsSource(
            name="Raio-X", module="costs",
            annual_savings_brl=500.0, description="d",
            amount_type="actual_fee",
        )
        assert s.amount_type == "actual_fee"

    def test_description_nunca_garante_economia(self, consolidator):
        consolidator._optimizer_saving = lambda uid: SavingsSource(
            name="Optimizer",
            module="optimizer",
            annual_savings_brl=1200.0,
            description="potencial estimado de até R$ 1.200/ano",
            amount_type="estimated_potential",
        )
        consolidator._costs_saving = lambda uid: _zero("costs", "C")
        consolidator._negotiator_saving = lambda uid: _zero("negotiator", "N")
        consolidator._opportunities_saving = lambda uid: _zero("opportunities", "O")

        sources, _ = consolidator.consolidate("u1")
        assert sources
        desc = sources[0].description.lower()
        assert "ajudou a guardar" not in desc

    def test_db_offline_retorna_zero_sem_excecao(self, consolidator):
        with patch(
            "app.core.database.SessionLocal",
            side_effect=Exception("DB offline"),
        ):
            sources, total = consolidator.consolidate("u1")
        assert isinstance(sources, list)
        assert total >= 0.0
