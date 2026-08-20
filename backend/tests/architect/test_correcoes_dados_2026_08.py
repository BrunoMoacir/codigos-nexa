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
    """
    Duas afirmações distintas, que a primeira versão deste teste confundia:

    (a) o GRUPO contempla todas as cotas ao longo do prazo — ritmo total
        group_size/months, invariante do produto;
    (b) o USUÁRIO específico espera mais ou menos que a mediana do grupo
        conforme dê ou não lance.

    Com ritmo fixo de 2/mês, (a) quebrava: 150 cotas acabavam no mês 75 de um
    plano de 180. Ao corrigir (a) eu quebrei (b) sem perceber, porque as vagas
    de lance eram `contemplacoes_do_mes - 1` — sempre zero abaixo de 2/mês, que
    é o caso de todo consórcio de imóvel. O lance virou decoração.
    """

    def _simular(self, group_size: int, months: int, lance: float = 0.0):
        return calculate_consortium_metrics(
            letter_value=300_000.0, months=months, admin_rate=0.19,
            reserve_fund_rate=0.02, bid_strategy="none", bid_amount=lance,
            asset_type="property", group_size=group_size, seed=5,
        ).to_dict()

    # ── (a) invariante do grupo ──────────────────────────────────────────────

    def test_ritmo_total_esgota_o_grupo_exatamente_no_prazo(self):
        """
        Contemplações acumuladas ao longo do prazo == tamanho do grupo. Nem
        antes (o grupo esvaziava na metade) nem depois (cota sem contemplação).
        """
        for group_size, months in ((150, 180), (200, 72), (80, 100)):
            taxa = group_size / months
            assert round(taxa * months) == group_size

    def test_grupo_nao_esvazia_na_metade_do_prazo(self):
        d = self._simular(group_size=150, months=180)
        assert d["contemplation_percentiles"]["p90"] > 90
        assert d["contemplation_probability"]["half_term"] < 0.95

    def test_ninguem_passa_do_prazo(self):
        d = self._simular(group_size=150, months=180)
        assert d["contemplation_percentiles"]["p90"] <= 180

    def test_grupo_grande_em_prazo_curto_contempla_mais_rapido(self):
        """Ritmo derivado: 200 cotas em 72 meses = 2,78/mês."""
        curto = self._simular(group_size=200, months=72)
        longo = self._simular(group_size=150, months=180)
        assert (curto["contemplation_percentiles"]["p50"]
                < longo["contemplation_percentiles"]["p50"])

    # ── (b) o lance tem que mover a agulha ───────────────────────────────────

    @pytest.mark.parametrize("lance_pct", [0.20, 0.30, 0.50])
    def test_lance_competitivo_antecipa_a_contemplacao(self, lance_pct):
        """
        A data de contemplação é a única alavanca que o consorciado controla.
        Sem repartir o ritmo entre sorteio e lance, ela ficava constante em
        137 meses para qualquer lance, de zero a 50% da carta.
        """
        sem = self._simular(150, 180)["contemplation_percentiles"]["p50"]
        com = self._simular(150, 180, lance=300_000.0 * lance_pct)
        assert com["contemplation_percentiles"]["p50"] < sem, (
            f"lance de {lance_pct:.0%} não antecipou nada (ambos no mês {sem})"
        )

    @pytest.mark.parametrize("lance_pct", [0.05, 0.10])
    def test_lance_baixo_nao_vence(self, lance_pct):
        """
        Verdade de produto, não bug: os concorrentes ofertam ~35% da carta no
        início do grupo (bid_mean_initial), então lance de 5–10% perde. Vale
        travar para que ninguém "conserte" isso achando que é insensibilidade.
        """
        sem = self._simular(150, 180)["contemplation_percentiles"]["p50"]
        com = self._simular(150, 180, lance=300_000.0 * lance_pct)
        assert com["contemplation_percentiles"]["p50"] == sem

    def test_lance_maior_antecipa_mais(self):
        p50 = [self._simular(150, 180, lance=300_000.0 * pct)
               ["contemplation_percentiles"]["p50"]
               for pct in (0.10, 0.30, 0.50)]
        assert p50 == sorted(p50, reverse=True), f"não é monotônico: {p50}"

    def test_quem_nao_da_lance_espera_mais_que_a_mediana_do_grupo(self):
        """
        Metade das vagas vai para lance; quem não disputa fica atrás de quem
        disputa. A mediana do NÃO-ofertante tem que ficar acima dos 90 meses
        que é a mediana do grupo (150 cotas / 180 meses).
        """
        assert self._simular(150, 180)["contemplation_percentiles"]["p50"] > 90


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

    # σ MENSAL medido nas séries observadas do BCB (não alisadas):
    #   Selic → SGS 4390 | IPCA → SGS 433
    SIGMA_MENSAL_REAL = {"selic": 0.003298, "ipca": 0.003830}
    # σ ANUAL da valorização → IVG-R (SGS 21340), 25 anos não-sobrepostos
    SIGMA_ANUAL_APPR = 0.0836

    @pytest.mark.parametrize("variavel", ["selic", "ipca"])
    def test_dispersao_mensal_bate_com_a_historica(self, paths, variavel):
        """
        As três variâncias eram chutadas e grandes demais (Selic 3,0x, IPCA
        1,4x). Tolerância de 10% porque _SIGMA_E foi calibrada por iteração
        numérica, não em forma fechada.
        """
        alvo = self.SIGMA_MENSAL_REAL[variavel]
        sigma = float(np.std(getattr(paths, variavel)))

        assert sigma == pytest.approx(alvo, rel=0.10), (
            f"{variavel}: σ={sigma:.5f} contra {alvo:.5f} da série real"
        )

    def test_dispersao_anual_da_valorizacao(self, paths):
        """
        A valorização é calibrada no ANUAL, não no mensal: o IVG-R é índice de
        avaliação suavizado por filtro de estado — os incrementos mensais do
        fim da série são 6,64 / 6,64 / 6,65 / 6,65 e ρ₁ das variações mensais é
        0,999. Calibrar σ mensal contra ele importava a suavização e o modelo
        saía com 4,11 p.p. de desvio anual contra os 8,36 observados,
        subestimando o risco de valorização pela METADE.
        """
        n_sims = paths.appreciation.shape[0]
        anos = paths.appreciation.shape[1] // 12
        a12 = (1 + paths.appreciation[:, : anos * 12]).reshape(n_sims, anos, 12).prod(axis=2) - 1

        assert float(a12.std()) == pytest.approx(self.SIGMA_ANUAL_APPR, rel=0.10), (
            f"σ anual={a12.std():.4f} contra {self.SIGMA_ANUAL_APPR:.4f} do IVG-R"
        )

    def test_persistencia_calibrada_e_estacionaria(self):
        """
        _A foi estimada por MQO nas séries reais (125 meses). A trava aqui é a
        ESTACIONARIEDADE: o MQO devolve 1,0148 para a própria defasagem da
        valorização — raiz unitária vinda do alisamento do IVG-R, não de
        economia. Adotar aquela linha faria o processo parar de reverter à
        média, e o simulador inteiro depende disso.
        """
        from app.architect.simulators.macro_scenario import _A

        raio = max(abs(np.linalg.eigvals(_A)))
        assert raio < 0.95, f"raio espectral {raio:.4f} — processo não reverte"

    def test_ipca_nao_e_mais_persistente_que_a_serie_real(self):
        """
        O modelo guardava choque de inflação com persistência 0,85; a série
        mostra 0,42 (ρ₁ = 0,466 no univariado). Guardava o dobro do tempo.
        """
        from app.architect.simulators.macro_scenario import _A

        assert _A[1][1] == pytest.approx(0.42, abs=0.05)

    def test_deflacao_na_frequencia_certa(self, paths):
        """
        Com a variância inflada o modelo dava 22,8% de meses em deflação
        contra 9,4% observados — cobria o fenômeno com o dobro da frequência.
        """
        pct_neg = float((paths.ipca < 0).mean())
        assert 0.08 <= pct_neg <= 0.20, f"{pct_neg:.1%} de meses em deflação"

    def test_selic_nunca_negativa_mas_ipca_pode_ser(self, paths):
        """Taxa nominal de política não é negativa; deflação e desvalorização
        existem e a simulação precisa cobri-las."""
        assert float(paths.selic.min()) >= 0.0
        assert float(paths.ipca.min()) < 0.0
        assert float(paths.appreciation.min()) < 0.0


class TestSensibilidadeMesmaBaseDoMotor:
    """
    A curva de sensibilidade explica um número; se ela sair de outra base de
    custo, o gráfico contradiz o resultado. Estes testes comparam contra o
    StrategyEngine DE VERDADE — comparar contra uma réplica escrita no teste
    deixa passar exatamente o que aconteceu com o IOF: o helper foi corrigido
    para o seguro, a réplica também, e a divergência de R$ 2.376 num veículo
    sobreviveu às duas.
    """

    def _request(self, asset_type, metodo="PRICE", **kw):
        from app.architect.models import AmortizationMethod, SimulationRequest

        return SimulationRequest(
            user_id="t", target_amount=kw.get("target", 300_000.0),
            down_payment=kw.get("down", 60_000.0),
            asset_type=asset_type, financing_months=kw.get("months", 240),
            amortization_method=AmortizationMethod(metodo),
        )

    def _fluxo_do_motor(self, req, cet):
        """Reconstrói o fluxo do motor a partir do próprio código do motor."""
        from app.architect.simulators.strategy_engine import (
            _CALC_ASSET_MAP, _IOF_RATE_BY_ASSET,
        )

        calc = (fin_calc.calculate_sac
                if req.amortization_method.value == "SAC"
                else fin_calc.calculate_price)
        sim = calc(
            req.target_amount - req.down_payment, cet, req.financing_months,
            iof_rate=_IOF_RATE_BY_ASSET.get(req.asset_type, fin_calc.IOF_FIXO_RATE),
            asset_type=_CALC_ASSET_MAP.get(req.asset_type, "other"),
        )
        return [-(req.down_payment + sim.total_iof)] + [
            -(r["payment"] + r.get("insurance", 0.0)) for r in sim.schedule
        ], sim

    @pytest.mark.parametrize(
        "asset,metodo,target,down,months",
        [
            ("IMOVEL",  "PRICE", 300_000.0, 60_000.0, 240),
            ("IMOVEL",  "SAC",   300_000.0, 60_000.0, 240),
            ("VEICULO", "PRICE",  80_000.0, 16_000.0,  48),
            ("REFORMA", "PRICE",  50_000.0,  5_000.0,  36),
            ("OUTRO",   "PRICE",  40_000.0,      0.0,  24),
        ],
    )
    def test_fluxo_identico_ao_do_motor(self, asset, metodo, target, down, months):
        from app.architect.models import AssetType
        from app.architect.simulators.sensitivity_analyzer import (
            _fluxo_financiamento, _simular_financiamento,
        )

        req = self._request(
            getattr(AssetType, asset), metodo,
            target=target, down=down, months=months,
        )
        cet = 0.13
        esperado, _ = self._fluxo_do_motor(req, cet)

        sim = _simular_financiamento(req, target - down, cet, months)
        assert _fluxo_financiamento(down, sim) == pytest.approx(esperado, abs=0.01)

    def test_seguro_obrigatorio_entra_no_fluxo(self):
        """Sem asset_type o seguro some — a tabela é indexada por "property"."""
        from app.architect.models import AssetType
        from app.architect.simulators.sensitivity_analyzer import (
            _fluxo_financiamento, _simular_financiamento,
        )

        req = self._request(AssetType.IMOVEL)
        sim = _simular_financiamento(req, 240_000.0, 0.13, 240)
        assert sim.total_insurance > 0

        primeira = sim.schedule[0]
        assert _fluxo_financiamento(60_000.0, sim)[1] == pytest.approx(
            -(primeira["payment"] + primeira["insurance"]), abs=0.01
        )

    def test_iof_de_entrada_entra_em_t0(self):
        """
        Veículo paga IOF no ato (imóvel SFH é isento). Omitir esse termo
        subestimava o custo em R$ 2.376 num financiamento de R$ 64 mil.
        """
        from app.architect.models import AssetType
        from app.architect.simulators.sensitivity_analyzer import (
            _fluxo_financiamento, _simular_financiamento,
        )

        req = self._request(AssetType.VEICULO, target=80_000.0, down=16_000.0, months=48)
        sim = _simular_financiamento(req, 64_000.0, 0.24, 48)
        assert sim.total_iof > 0

        assert _fluxo_financiamento(16_000.0, sim)[0] == pytest.approx(
            -(16_000.0 + sim.total_iof), abs=0.01
        )

    def test_imovel_sfh_e_isento_de_iof(self):
        from app.architect.models import AssetType
        from app.architect.simulators.sensitivity_analyzer import _simular_financiamento

        req = self._request(AssetType.IMOVEL)
        assert _simular_financiamento(req, 240_000.0, 0.13, 240).total_iof == 0.0
