"""
O número que o usuário PUBLICA — unidade e dupla contagem.

O `SavingsConsolidator` agrega quatro módulos num
`total_annual_savings_brl` que vira card compartilhável (V1 Placar de
Economia). Dois defeitos, em direções opostas, que se mascaravam no total:

1. **Unidade.** `negotiation_history.potential_gain` recebe
   `opp.potential_saving_monthly` — valor MENSAL (ver o INSERT em
   `app/negotiator/router.py`). As outras três fontes anualizam; esta somava o
   mensal direto no campo `annual_savings_brl`. Contribuição do Negociador
   12× subestimada.

2. **Dupla contagem.** O Raio-X (F5) mede tarifas EFETIVAMENTE cobradas,
   entre elas `ANUIDADE_CARTAO` e `JUROS_ROTATIVO`. O Negociador estima o que
   se pouparia negociando exatamente essa anuidade e esses juros
   (`ANUIDADE_ALTA`, `JUROS_ROTATIVO_ALTO`). Mesmo dinheiro, duas fontes.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.viral.services.savings_consolidator import (
    _MESES_NO_ANO,
    _TRIGGERS_JA_CONTADOS_NO_RAIO_X,
    SavingsConsolidator,
)


class TestUnidadeDoNegociador:

    def _consolidar(self, soma_mensal: float):
        class _Row(tuple):
            pass

        with patch("app.core.database.SessionLocal") as sess:
            ctx = sess.return_value.__enter__.return_value
            ctx.execute.return_value.fetchone.return_value = (soma_mensal,)
            return SavingsConsolidator()._negotiator_saving("u")

    def test_o_valor_mensal_e_anualizado(self):
        """R$ 180/mês são R$ 2.160/ano, não R$ 180/ano."""
        s = self._consolidar(180.0)
        assert s.annual_savings_brl == pytest.approx(180.0 * _MESES_NO_ANO)

    def test_a_descricao_separa_mensal_de_anual(self):
        s = self._consolidar(180.0)
        assert "180" in s.description and "2,160" in s.description.replace(".", ",")

    def test_sem_negociacao_pendente_fica_zero(self):
        s = self._consolidar(0.0)
        assert s.annual_savings_brl == 0.0
        assert "Nenhuma negociação" in s.description


class TestDuplaContagem:

    def test_os_gatilhos_sobrepostos_estao_declarados(self):
        """
        Os dois que o Raio-X já mede como tarifa efetivamente cobrada.
        """
        assert set(_TRIGGERS_JA_CONTADOS_NO_RAIO_X) == {
            "ANUIDADE_ALTA", "JUROS_ROTATIVO_ALTO",
        }

    def test_os_gatilhos_existem_de_verdade_no_negociador(self):
        """
        Se alguém renomear um trigger, a exclusão vira letra morta e a dupla
        contagem volta em silêncio.
        """
        from app.negotiator.models import NegotiationTrigger

        validos = {t.value for t in NegotiationTrigger}
        for trigger in _TRIGGERS_JA_CONTADOS_NO_RAIO_X:
            assert trigger in validos, trigger

    def test_o_raio_x_realmente_cobre_esse_dinheiro(self):
        """A exclusão só se justifica se o Raio-X conta essas tarifas."""
        from app.costs.models import FeeType

        tipos = {f.value for f in FeeType}
        assert "ANUIDADE_CARTAO" in tipos
        assert "JUROS_ROTATIVO" in tipos

    def test_a_consulta_exclui_os_sobrepostos(self):
        with patch("app.core.database.SessionLocal") as sess:
            ctx = sess.return_value.__enter__.return_value
            ctx.execute.return_value.fetchone.return_value = (100.0,)
            SavingsConsolidator()._negotiator_saving("u")
            _sql, params = ctx.execute.call_args[0]
        assert set(params["sobrepostos"]) == set(_TRIGGERS_JA_CONTADOS_NO_RAIO_X)

    def test_a_descricao_explica_a_exclusao(self):
        with patch("app.core.database.SessionLocal") as sess:
            ctx = sess.return_value.__enter__.return_value
            ctx.execute.return_value.fetchone.return_value = (200.0,)
            s = SavingsConsolidator()._negotiator_saving("u")
        assert "Raio-X" in s.description


class TestTotalConsolidado:

    def test_fontes_zeradas_ficam_fora_da_lista(self):
        with patch.object(SavingsConsolidator, "_optimizer_saving") as o, \
             patch.object(SavingsConsolidator, "_costs_saving") as c, \
             patch.object(SavingsConsolidator, "_negotiator_saving") as n, \
             patch.object(SavingsConsolidator, "_opportunities_saving") as p:
            from app.viral.models import SavingsSource

            def fonte(valor, mod):
                return SavingsSource(name=mod, module=mod,
                                     annual_savings_brl=valor, description="d")
            o.return_value = fonte(1_200.0, "optimizer")
            c.return_value = fonte(780.0, "costs")
            n.return_value = fonte(2_160.0, "negotiator")
            p.return_value = fonte(0.0, "opportunities")

            fontes, total = SavingsConsolidator().consolidate("u")

        assert {f.module for f in fontes} == {"optimizer", "costs", "negotiator"}
        assert total == pytest.approx(1_200 + 780 + 2_160)
