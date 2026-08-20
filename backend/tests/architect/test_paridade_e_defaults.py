"""
Paridade entre o motor e a curva de sensibilidade, e fonte única dos defaults.

O SensitivityAnalyzer produz o GRÁFICO que explica o número do StrategyEngine.
Quando os dois montam o fluxo de caixa por conta própria, divergem — e o gráfico
passa a contradizer o número que ele deveria explicar. Já aconteceu duas vezes:

  • financiamento: faltava asset_type (zera o seguro obrigatório) e o IOF de
    entrada → R$ 2.376 num veículo de R$ 64 mil;
  • consórcio: faltavam seis parâmetros de grupo, entre eles o reajuste da carta
    → R$ 8.568 (4,6% do VPL) e contemplação 31 meses diferente.

Aqui a paridade é verificada contra o MOTOR, não contra uma réplica escrita no
teste — foi exatamente uma réplica que deixou o IOF passar na primeira correção.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.architect.calculators import consortium as cons_calc
from app.architect.calculators import financing as fin_calc
from app.architect.models import AmortizationMethod, AssetType, SimulationRequest
from app.architect.rate_defaults import (
    MissingRateError,
    _DEFAULTS,
    fallback_market_rates,
    missing_keys,
    rate,
    rate_int,
)
from app.architect.simulators import cost_basis

_APP = Path(__file__).resolve().parents[2] / "app" / "architect"


def _request(asset=AssetType.IMOVEL, metodo="PRICE", alvo=300_000.0, entrada=60_000.0, meses=240):
    return SimulationRequest(
        user_id="t", target_amount=alvo, down_payment=entrada, asset_type=asset,
        financing_months=meses, amortization_method=AmortizationMethod(metodo),
    )


class TestFonteUnicaDeDefaults:

    def test_nenhum_get_com_default_literal_sobrou(self):
        """
        A regressão que este teste impede: voltar a escrever
        `rates.get("selic_annual", 0.1475)` em vez de `rate(rates, ...)`.

        Era assim que o MESMO conector fora do ar produzia números diferentes
        conforme o caminho do código — best_cet_annual tinha 0,15, 0,1950 e
        0,20 espalhados, consortium_admin_rate tinha 0,17 e 0,18.
        """
        # Só dicionários de taxa de MERCADO: `rates`, `market_rates`, `_rates`.
        # Outros dicts (estado de calibração, tabela da ABAC) legitimamente têm
        # chaves de mesmo nome e default próprio.
        padrao = re.compile(
            r'\b\w*rates\.get\(\s*"(' + "|".join(_DEFAULTS) + r')"\s*,\s*[0-9]'
        )
        infratores = []
        for arquivo in _APP.rglob("*.py"):
            if arquivo.name == "rate_defaults.py":
                continue
            for n, linha in enumerate(arquivo.read_text().splitlines(), 1):
                if padrao.search(linha):
                    infratores.append(f"{arquivo.relative_to(_APP)}:{n}: {linha.strip()}")
        assert not infratores, "default literal fora do rate_defaults:\n" + "\n".join(infratores)

    def test_fallback_traz_o_conjunto_completo(self):
        """
        Os fallbacks do router omitiam as chaves de consórcio e o IPCA, que os
        consumidores então preenchiam com outro conjunto de defaults.
        """
        for asset in ("IMOVEL", "VEICULO", "REFORMA"):
            rates = fallback_market_rates(asset)
            assert missing_keys(rates) == [], f"{asset}: faltando {missing_keys(rates)}"

    def test_fallback_de_imovel_usa_o_grupo_de_imovel(self):
        """Consórcio de imóvel não é grupo de 100 cotas em 72 meses."""
        imovel = fallback_market_rates("IMOVEL")
        assert imovel["consortium_months"] >= 120
        assert imovel["consortium_group_size"] >= 120

    def test_chave_ausente_cai_no_default_canonico(self):
        assert rate({}, "best_cet_annual") == _DEFAULTS["best_cet_annual"]
        assert rate_int({}, "consortium_months") == int(_DEFAULTS["consortium_months"])

    def test_chave_presente_vence_o_default(self):
        assert rate({"selic_annual": 0.09}, "selic_annual") == pytest.approx(0.09)

    def test_chave_desconhecida_estoura(self):
        """Erro de digitação não pode virar número silencioso."""
        with pytest.raises(MissingRateError):
            rate({}, "selic_anual")           # sem o segundo 'n'

    def test_uso_de_default_fica_no_log(self, caplog):
        with caplog.at_level("WARNING"):
            rate({}, "selic_annual")
        assert any("selic_annual" in r.getMessage() for r in caplog.records)


class TestParidadeFinanciamento:

    def _fluxo_do_motor(self, req, cet):
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
        ]

    @pytest.mark.parametrize(
        "asset,metodo,alvo,entrada,meses",
        [
            (AssetType.IMOVEL,  "PRICE", 300_000.0, 60_000.0, 240),
            (AssetType.IMOVEL,  "SAC",   300_000.0, 60_000.0, 240),
            (AssetType.VEICULO, "PRICE",  80_000.0, 16_000.0,  48),
            (AssetType.VEICULO, "SAC",    80_000.0, 16_000.0,  48),
            (AssetType.REFORMA, "PRICE",  50_000.0,  5_000.0,  36),
            (AssetType.OUTRO,   "PRICE",  40_000.0,      0.0,  24),
        ],
    )
    def test_fluxo_identico(self, asset, metodo, alvo, entrada, meses):
        req = _request(asset, metodo, alvo, entrada, meses)
        sim = cost_basis.simular_financiamento(req, alvo - entrada, 0.13, meses)
        assert cost_basis.fluxo_financiamento(entrada, sim) == pytest.approx(
            self._fluxo_do_motor(req, 0.13), abs=0.01
        )

    def test_seguro_obrigatorio_no_fluxo(self):
        req = _request(AssetType.IMOVEL)
        sim = cost_basis.simular_financiamento(req, 240_000.0, 0.13, 240)
        assert sim.total_insurance > 0
        primeira = sim.schedule[0]
        assert cost_basis.fluxo_financiamento(60_000.0, sim)[1] == pytest.approx(
            -(primeira["payment"] + primeira["insurance"]), abs=0.01
        )

    def test_iof_de_entrada_em_t0(self):
        """Veículo paga IOF no ato; imóvel no SFH é isento."""
        veiculo = cost_basis.simular_financiamento(
            _request(AssetType.VEICULO, meses=48), 64_000.0, 0.24, 48
        )
        assert veiculo.total_iof > 0
        assert cost_basis.fluxo_consorcio is not None      # módulo carregado
        assert cost_basis.fluxo_financiamento(16_000.0, veiculo)[0] == pytest.approx(
            -(16_000.0 + veiculo.total_iof), abs=0.01
        )

        imovel = cost_basis.simular_financiamento(_request(AssetType.IMOVEL), 240_000.0, 0.13, 240)
        assert imovel.total_iof == 0.0


class TestParidadeConsorcio:

    RATES = {
        "consortium_admin_rate":             0.19,
        "consortium_months":                 180.0,
        "consortium_reserve_fund_rate":      0.02,
        "consortium_group_size":             150.0,
        "consortium_contemplated_per_month": 2.0,
        "consortium_annual_adjustment_rate": 0.0666,
        "bid_mean_initial":                  0.35,
        "bid_std":                           0.12,
    }

    def test_fluxo_identico_ao_do_motor(self):
        from app.architect.connectors.consortium_rate_provider import ConsortiumRateProvider

        req = _request(AssetType.IMOVEL, meses=180)
        motor = cons_calc.calculate_consortium_metrics(
            letter_value=300_000.0, months=180, admin_rate=0.19, reserve_fund_rate=0.02,
            bid_amount=60_000.0,
            asset_type=ConsortiumRateProvider.map_asset_type("IMOVEL"),
            annual_adjustment_rate=0.0666, group_size=150, contemplated_per_month=2,
            bid_mean_initial=0.35, bid_std=0.12,
            num_simulations=cost_basis.SIMS_SENSIBILIDADE,
            seed=cost_basis.SEED_SENSIBILIDADE,
        )
        cf_motor = cost_basis.fluxo_consorcio(motor, 60_000.0, 180)

        sim = cost_basis.simular_consorcio(
            req, self.RATES, 60_000.0,
            num_simulations=cost_basis.SIMS_SENSIBILIDADE,
            seed=cost_basis.SEED_SENSIBILIDADE,
        )
        assert cost_basis.fluxo_consorcio(sim, 60_000.0, 180) == pytest.approx(cf_motor, abs=0.01)

    def test_reajuste_da_carta_chega_na_simulacao(self):
        """
        O parâmetro omitido mais caro: a sensibilidade rodava com o default de
        4,5% enquanto o motor usava o IPCA real corrigido (série 13522).
        """
        req = _request(AssetType.IMOVEL, meses=180)
        baixo = cost_basis.simular_consorcio(
            req, {**self.RATES, "consortium_annual_adjustment_rate": 0.02},
            60_000.0, num_simulations=200, seed=1,
        )
        alto = cost_basis.simular_consorcio(
            req, {**self.RATES, "consortium_annual_adjustment_rate": 0.10},
            60_000.0, num_simulations=200, seed=1,
        )
        assert alto.total_cost > baixo.total_cost

    def test_tamanho_do_grupo_chega_na_simulacao(self):
        """
        Estava omitido: a sensibilidade rodava sempre com o default de 100
        cotas. Aqui só se afirma que o parâmetro CHEGA — a direção do efeito
        não é óbvia (grupo maior tem mais vagas por assembleia, mas também
        mais concorrentes) e o teste não é o lugar de arbitrar isso.
        """
        req = _request(AssetType.IMOVEL, meses=180)
        resultados = {
            g: cost_basis.simular_consorcio(
                req, {**self.RATES, "consortium_group_size": float(g)},
                0.0, num_simulations=400, seed=3,
            ).contemplation_month_expected
            for g in (100, 300)
        }
        assert resultados[100] != resultados[300], (
            f"group_size não chegou na simulação: {resultados}"
        )

        direto = cons_calc.calculate_consortium_metrics(
            letter_value=300_000.0, months=180, admin_rate=0.19,
            reserve_fund_rate=0.02, bid_amount=0.0,
            asset_type="property", annual_adjustment_rate=0.0666,
            group_size=300, contemplated_per_month=2,
            bid_mean_initial=0.35, bid_std=0.12, num_simulations=400, seed=3,
        )
        assert resultados[300] == direto.contemplation_month_expected

    def test_sensibilidade_nao_usa_amostra_unica(self):
        """
        1 simulação não é estimativa pontual, é ruído — e num gráfico que mede a
        DIFERENÇA entre pontos o ruído engole o sinal.
        """
        assert cost_basis.SIMS_SENSIBILIDADE >= 100
        assert cost_basis.SEED_SENSIBILIDADE is not None

    def test_entrada_do_usuario_chega_na_simulacao(self):
        """
        `bid_strategy` caía no default 'fixed', que DESCARTAVA o bid_amount e
        usava 25% fixos da carta. Como nenhum caller passava bid_strategy, todo
        usuário era simulado com o mesmo lance — com R$ 0 ou R$ 120 mil de
        entrada — enquanto o fluxo de caixa abatia a entrada real.
        """
        req = _request(AssetType.IMOVEL, meses=180)
        meses = [
            cost_basis.simular_consorcio(
                req, self.RATES, entrada, num_simulations=2000, seed=42
            ).contemplation_month_expected
            for entrada in (0.0, 60_000.0, 120_000.0)
        ]
        assert meses == sorted(meses, reverse=True), (
            f"entrada maior tem que antecipar a contemplação: {meses}"
        )
        assert meses[0] != meses[-1]


class TestAlvoMovel:
    """
    Quem poupa para comprar mira o preço que o bem terá na data da compra.

    O modelo mirava `target_amount` — o preço de HOJE, congelado — enquanto o
    aluguel pago durante a espera era corrigido pelo IPCA mês a mês, oito linhas
    acima no mesmo método. Encarecia a espera de um lado e congelava do outro, e
    o viés tinha direção única: inflava SAVE_INVEST, que é justamente a
    estratégia concorrente do financiamento.
    """

    RATES = {"ipca_annual": 0.045, "cdi_annual": 0.1465, "selic_annual": 0.1475}

    def test_preco_do_bem_cresce_com_o_prazo(self):
        req = _request(AssetType.IMOVEL)
        precos = [cost_basis.preco_do_bem_em(req, self.RATES, m) for m in (0, 36, 120)]

        assert precos[0] == pytest.approx(300_000.0)
        assert precos == sorted(precos)
        assert precos[2] > 500_000.0, f"120 meses a 6% a.a.: {precos[2]:,.0f}"

    def test_aporte_necessario_e_maior_que_o_do_alvo_congelado(self):
        """
        Imóvel de R$ 300 mil, 120 meses: o modelo pedia R$ 616/mês contra os
        R$ 1.742 de que a pessoa precisa. Aos 180 meses pedia R$ 30 — porque a
        entrada rendendo sozinha quase alcançava um alvo que não anda.
        """
        from app.architect.calculators import investment as inv_calc

        req = _request(AssetType.IMOVEL)
        for meses in (36, 60, 120, 180):
            congelado = inv_calc.calculate_pmt_needed(300_000.0, 0.11, meses, 60_000.0)
            movel = cost_basis.aporte_para_alcancar_o_bem(req, self.RATES, 0.11, meses)
            assert movel > congelado, f"{meses}m: {movel:.0f} vs {congelado:.0f}"

    def test_bem_que_sobe_mais_que_o_rendimento_nao_e_alcancavel(self):
        """
        Resultado, não falha de cálculo: se o imóvel valoriza 6% a.a. e o
        dinheiro rende 4%, a meta se afasta a cada mês. Antes isso virava um
        prazo de 120 meses inventado, indistinguível de um plano que fecha.
        """
        req = _request(AssetType.IMOVEL)
        assert cost_basis.meses_para_alcancar_o_bem(req, self.RATES, 2_000.0, 0.04) is None
        assert cost_basis.meses_para_alcancar_o_bem(req, self.RATES, 2_000.0, 0.11) is not None

    def test_bem_sem_indice_proprio_cresce_pelo_ipca(self):
        """
        Não existe índice de veículo no projeto. Crescer pelo IPCA é o neutro;
        congelar não é — congelar afirma que o preço não muda.
        """
        for asset in (AssetType.VEICULO, AssetType.REFORMA, AssetType.OUTRO):
            assert cost_basis.taxa_reajuste_do_bem(asset, self.RATES) == pytest.approx(0.045)
        assert cost_basis.taxa_reajuste_do_bem(AssetType.IMOVEL, self.RATES) > 0.045

    def test_valorizacao_do_var_deixou_de_ser_codigo_morto(self):
        """
        `paths.appreciation` era gerado, calibrado, clampado e DESCARTADO —
        nenhum consumidor o lia. Agora é ele que move o alvo por trajetória.
        """
        import inspect

        from app.architect.simulators import macro_scenario

        # Consumo tem que existir FORA da função que gera as trajetórias.
        fonte = inspect.getsource(macro_scenario.run_macro_simulation)
        assert "paths.appreciation" in fonte

        # E tem que chegar até o cálculo de NPV.
        assert "asset_growth" in inspect.getsource(macro_scenario._compute_raw_npvs)
        assert "asset_growth" in inspect.getsource(macro_scenario._npv_save_invest)

    def test_alvo_movel_encarece_poupar_na_simulacao_macro(self):
        import numpy as np

        from app.architect.simulators.macro_scenario import (
            _npv_save_invest, generate_macro_paths,
        )

        p = generate_macro_paths(n_sims=800, n_months=240, initial_selic_annual=0.12, seed=5)
        congelado = _npv_save_invest(2_500.0, 300_000.0, 60_000.0, p.selic, 0.85)
        movel = _npv_save_invest(
            2_500.0, 300_000.0, 60_000.0, p.selic, 0.85, asset_growth=p.appreciation
        )
        assert float(np.median(movel)) < float(np.median(congelado))


class TestIncertezaDosParametrosDoGrupo:
    """
    Dois parâmetros do consórcio não são conhecidos: a divisão das vagas entre
    sorteio e lance, e a fração da carta usada como lance embutido. A ABAC não
    publica nenhum dos dois e o dataset do BACEN que traria isso
    (PANORAMA_DE_CONSORCIOS, no Olinda) responde 500 nos endpoints de dado.

    A resposta não é escolher melhor o número — é parar de reportar precisão
    que não existe.
    """

    KW = dict(
        letter_value=300_000.0, months=180, admin_rate=0.19,
        reserve_fund_rate=0.02, asset_type="property",
        annual_adjustment_rate=0.0666, group_size=150,
        num_simulations=4800, seed=42,
    )

    def _percentis(self, **extra):
        return cons_calc.calculate_consortium_metrics(
            bid_amount=120_000.0, **extra, **self.KW
        ).contemplation_percentiles

    def test_intervalo_alarga_com_a_incerteza(self):
        """
        Com lance alto a data depende muito de quanto os OUTROS ofertam — que é
        exatamente o que ninguém publica. O intervalo tem que refletir isso.
        """
        incerto = self._percentis()
        fixo = self._percentis(sorteio_share=0.5)

        largura = lambda p: p["p90"] - p["p10"]
        assert largura(incerto) > largura(fixo), (
            f"incerteza não alargou: {largura(incerto)} vs {largura(fixo)}"
        )

    def test_share_explicito_desliga_a_propagacao(self):
        """Determinismo continua disponível — é o que a sensibilidade usa."""
        a = self._percentis(sorteio_share=0.5)
        b = self._percentis(sorteio_share=0.5)
        assert a == b

    def test_sensibilidade_roda_sem_ruido_de_parametro(self):
        """
        Gráfico de tornado isola UMA variável. Ruído de parâmetro em cada ponto
        mede ruído, não sensibilidade — e custava 25 s por teste.
        """
        import inspect

        from app.architect.simulators import sensitivity_analyzer

        fonte = inspect.getsource(sensitivity_analyzer._simular_consorcio)
        assert "sorteio_share" in fonte

    def test_faixas_declaradas_sao_plausiveis(self):
        from app.architect.calculators.consortium import (
            _LANCE_EMBUTIDO_FAIXA, _SORTEIO_SHARE_FAIXA,
        )

        # embutido: faixa real citada pela ABAC
        assert _LANCE_EMBUTIDO_FAIXA == (0.10, 0.30)
        # sorteio: simétrica em torno do 50/50 que o modelo sempre assumiu
        assert sum(_SORTEIO_SHARE_FAIXA) == pytest.approx(1.0)
        assert 0.0 < _SORTEIO_SHARE_FAIXA[0] < _SORTEIO_SHARE_FAIXA[1] < 1.0

    def test_busca_do_prazo_e_por_bisseccao(self):
        """
        `calculate_months_needed` itera até 1200 meses em Python puro. Com o
        alvo móvel ela deixou de convergir cedo e, sozinha, multiplicou por 5 o
        tempo da suíte do architect (143 s → 720 s).
        """
        import time

        req = _request(AssetType.IMOVEL)
        rates = {"ipca_annual": 0.045}

        t0 = time.perf_counter()
        for _ in range(500):
            cost_basis.meses_para_alcancar_o_bem(req, rates, 2_000.0, 0.11)
        us = (time.perf_counter() - t0) / 500 * 1e6

        assert us < 200, f"{us:.0f} µs/chamada — busca linear de volta?"

