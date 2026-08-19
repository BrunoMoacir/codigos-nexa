"""
Regressões dos quatro defeitos de DADO do Architect (auditoria 2026-08).

A matemática determinística estava correta — conferi CET com resíduo zero,
IOF pela Resolução 3.516 e PRICE contra a fórmula fechada. O que estava
errado era o que alimentava essa matemática:

  1. IPCA: get_ipca() lia a série 433 (variação MENSAL) e devolvia como
     `ipca_annual`. Em 01/07/2026 a 433 dava 0,07 e a 13522 (acumulado 12m)
     dava 4,44 — inflação entrando ~60x menor. No consórcio de imóvel isso
     virava reajuste de carta de 0,105% a.a. em vez de ~7%, e R$ 261 mil de
     custo a menos numa decisão de 15 anos.

  2. Consórcio: ritmo fixo de 2 contemplações/mês ignorava a invariante de
     que toda cota é contemplada uma vez ao longo do prazo. 150 cotas em 180
     meses esvaziavam o grupo no mês 75; a mediana caía de 90 para 37.

  3. Macro: o clamp era aplicado DENTRO da recursão e realimentava o passo
     seguinte, então o viés compunha — a Selic "com reversão a 12%" derivava
     para 15% e o IPCA de 5% para 8,2%.

  4. Sensibilidade: calculava o financiamento sem asset_type (seguro zerado)
     e montava o fluxo sem o seguro, divergindo R$ 8,4 mil do número que o
     gráfico deveria explicar.
"""

import numpy as np
import pytest

from app.architect.calculators import financing as fin_calc
from app.architect.calculators.consortium import calculate_consortium_metrics
from app.architect.connectors.ipca import IPCAConnector
from app.architect.simulators.macro_scenario import generate_macro_paths


class TestIPCASerieCorreta:

    def test_serie_primaria_e_o_acumulado_12_meses(self):
        """433 é variação mensal; 13522 é o acumulado que o campo promete."""
        assert IPCAConnector._IPCA_SERIES == 13522
        assert IPCAConnector._IPCA_MONTHLY_SERIES == 433

    def test_valor_mensal_disfarçado_de_anual_e_rejeitado(self, monkeypatch):
        """
        A guarda que faltava: 0,07% "ao ano" é sinal de série trocada, não de
        economia exótica. Rejeitar faz o fallback multi-camada assumir.
        """
        from app.architect.connectors.base import ConnectorError

        class _Resp:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return [{"data": "01/07/2026", "valor": "0.07"}]

        class _Client:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, *a, **k):
                return _Resp()

        import app.architect.connectors.ipca as mod

        monkeypatch.setattr(mod.httpx, "Client", _Client)

        with pytest.raises(ConnectorError, match="implausível"):
            IPCAConnector().fetch_rates()

    @pytest.mark.parametrize("pct,valido", [(0.07, False), (4.44, True), (12.5, True), (60.0, False)])
    def test_faixa_de_plausibilidade(self, pct, valido):
        dentro = (
            IPCAConnector._IPCA_MIN_PLAUSIVEL <= pct / 100 <= IPCAConnector._IPCA_MAX_PLAUSIVEL
        )
        assert dentro is valido


class TestConsorcioRitmoDeContemplacao:

    def _simular(self, group_size: int, months: int):
        return calculate_consortium_metrics(
            letter_value=300_000.0, months=months, admin_rate=0.19,
            reserve_fund_rate=0.02, bid_strategy="none", asset_type="property",
            group_size=group_size, seed=5,
        ).to_dict()

    def test_grupo_dura_o_prazo_inteiro(self):
        """
        Invariante do consórcio: as contemplações se espalham pelo prazo. Com
        ritmo fixo de 2/mês, 150 cotas acabavam no mês 75 de um plano de 180 —
        e o modelo prometia contemplação na primeira metade para todo mundo.
        """
        d = self._simular(group_size=150, months=180)
        p = d["contemplation_percentiles"]

        assert p["p90"] > 90, "o grupo não pode esvaziar na metade do prazo"
        assert 60 <= p["p50"] <= 120, f"mediana fora do plausível: {p['p50']}"
        assert d["contemplation_probability"]["half_term"] < 0.95

    def test_grupo_grande_em_prazo_curto_contempla_mais_rapido(self):
        """Ritmo derivado: 200 cotas em 72 meses = 2,78/mês."""
        curto = self._simular(group_size=200, months=72)
        longo = self._simular(group_size=150, months=180)

        assert curto["contemplation_percentiles"]["p50"] < longo["contemplation_percentiles"]["p50"]

    def test_todos_contemplados_ate_o_fim(self):
        d = self._simular(group_size=150, months=180)
        assert d["contemplation_percentiles"]["p90"] <= 180


class TestMacroRevertePraMediaDeclarada:

    ALVOS = {"selic": 0.12, "ipca": 0.05, "appreciation": 0.06}

    @pytest.fixture(scope="class")
    def paths(self):
        return generate_macro_paths(
            n_sims=3000, n_months=360, initial_selic_annual=0.12, seed=11
        )

    @pytest.mark.parametrize("variavel", ["selic", "ipca", "appreciation"])
    def test_media_simulada_bate_com_o_alvo(self, paths, variavel):
        """
        Clampando dentro da recursão, o truncamento realimentava o processo e
        a média derivava para longe de μ (Selic 12% → 15%, IPCA 5% → 8,2%).
        """
        serie = getattr(paths, variavel)
        anual = (1 + float(np.mean(serie))) ** 12 - 1

        assert anual == pytest.approx(self.ALVOS[variavel], abs=0.01), (
            f"{variavel}: {anual:.2%} contra alvo {self.ALVOS[variavel]:.0%}"
        )

    def test_nao_ha_deriva_ao_longo_do_horizonte(self, paths):
        """Processo estacionário: ano 1 e ano 30 têm a mesma média."""
        ano1 = (1 + float(paths.selic[:, :12].mean())) ** 12 - 1
        ano30 = (1 + float(paths.selic[:, -12:].mean())) ** 12 - 1

        assert abs(ano30 - ano1) < 0.015, f"deriva de {(ano30-ano1)*100:.2f} p.p."

    def test_dispersao_da_selic_bate_com_a_historica(self, paths):
        """
        Recalibrado com SGS 4390 (127 meses, 2016–2026): desvio estacionário
        observado de 0,3298 p.p./mês. O modelo implicava 0,99 — 3x demais, e
        era por isso que 16% dos sorteios caíam abaixo de zero.
        """
        assert float(np.std(paths.selic)) == pytest.approx(0.0033, abs=0.0012)

    def test_selic_nunca_negativa_mas_ipca_pode_ser(self, paths):
        """Taxa nominal de política não é negativa; deflação e desvalorização
        existem e a simulação precisa cobri-las."""
        assert float(paths.selic.min()) >= 0.0
        assert float(paths.ipca.min()) < 0.0
        assert float(paths.appreciation.min()) < 0.0


class TestSensibilidadeMesmaBaseDoMotor:

    def test_fluxo_inclui_seguro_como_no_strategy_engine(self):
        """
        O gráfico que explica o número precisa sair do mesmo custo do número.
        Sem asset_type o seguro some (a tabela é indexada por "property");
        sem somá-lo ao fluxo, some de novo.
        """
        from app.architect.models import AssetType
        from app.architect.simulators.sensitivity_analyzer import (
            _fluxo_financiamento,
            _simular_financiamento,
        )

        class _Req:
            asset_type = AssetType.IMOVEL

            class amortization_method:
                value = "PRICE"

        sim = _simular_financiamento(_Req(), 300_000.0, 0.13, 240)
        assert sim.total_insurance > 0, "imóvel tem seguro obrigatório"

        fluxo = _fluxo_financiamento(60_000.0, sim)
        primeira = sim.schedule[0]
        assert fluxo[1] == pytest.approx(
            -(primeira["payment"] + primeira["insurance"]), abs=0.01
        )

    def test_divergencia_contra_o_motor_principal_zerada(self):
        from app.architect.models import AssetType
        from app.architect.simulators.sensitivity_analyzer import (
            _fluxo_financiamento,
            _simular_financiamento,
        )

        class _Req:
            asset_type = AssetType.IMOVEL

            class amortization_method:
                value = "PRICE"

        motor = fin_calc.calculate_price(300_000.0, 0.13, 240, asset_type="property")
        fluxo_motor = [-60_000.0] + [
            -(r["payment"] + r.get("insurance", 0.0)) for r in motor.schedule
        ]
        fluxo_sens = _fluxo_financiamento(
            60_000.0, _simular_financiamento(_Req(), 300_000.0, 0.13, 240)
        )

        assert fluxo_sens == pytest.approx(fluxo_motor, abs=0.01)
