"""
Inteligência comportamental — degraus, imunidade de CRITICAL e corroboração.

Três correções e uma melhoria de 2026-08-23, todas medidas antes de serem
feitas:

1. O FSS era uma soma de DEGRAUS. `income_drop < -0.15 → +20` fazia uma queda
   de 14,9% valer zero e uma de 15,1% valer 20 pontos — um terço da distância
   entre SAUDAVEL e CRITICO decidido por 0,2 ponto percentual, num número que
   dimensiona a reserva de emergência do OPP, os pesos do Bank Match, a
   penalidade de anuidade do optimizer e o tom do agente.

2. `overdraft_months / total_months` com um mês de histórico dava 1/1 = 1,0,
   o sinal MÁXIMO a partir de uma amostra de um mês — mesmo defeito de janela
   curta do Radar de Oportunidades, e para o lado perigoso.

3. A etapa 1 do filtro de notificações NÃO protegia CRITICAL, embora a doc, o
   docstring do módulo e as etapas 2 e 3 dissessem que sim. Uma anomalia
   CRITICAL de R$ 150 era descartada para quem ganha R$ 15 mil exatamente
   como um WARNING.

4. Melhoria: o híbrido abstinha e o piso de regras salvava 18,5% dos perfis;
   o resto virava NAO_CLASSIFICADO — a feature inteira desligada para aquele
   usuário. A corroboração aplica no classificador o princípio que o
   EvidenceScorer já usa nos eventos de vida.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from app.optimizer.detectors.fss_calculator import (
    _OVERDRAFT_PATTERN,
    FSSCalculator,
    _rampa,
)
from app.optimizer.profiler import UserProfile

HOJE = dt.date.today()


def _mes(atras: int) -> dt.date:
    d = HOJE.replace(day=15)
    for _ in range(atras):
        d = (d.replace(day=1) - dt.timedelta(days=1)).replace(day=15)
    return d


def _df(linhas: list[tuple[int, str]]) -> pl.DataFrame:
    return pl.DataFrame(
        [{"date": _mes(m), "amount": -120.0, "description": d} for m, d in linhas],
        schema={"date": pl.Date, "amount": pl.Float64, "description": pl.Utf8},
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Rampas no lugar de degraus
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestRampa:

    def test_satura_nos_dois_extremos(self):
        assert _rampa(10.0, 0.0, 5.0, 20.0) == 20.0
        assert _rampa(-1.0, 0.0, 5.0, 20.0) == 0.0

    def test_interpola_no_meio(self):
        assert _rampa(2.5, 0.0, 5.0, 20.0) == pytest.approx(10.0)

    def test_funciona_no_sentido_decrescente(self):
        """Sinais em que 'pior' é 'mais negativo' — queda de renda."""
        assert _rampa(-0.05, -0.05, -0.15, 20.0) == pytest.approx(0.0)
        assert _rampa(-0.10, -0.05, -0.15, 20.0) == pytest.approx(10.0)
        assert _rampa(-0.15, -0.05, -0.15, 20.0) == pytest.approx(20.0)
        assert _rampa(-0.50, -0.05, -0.15, 20.0) == pytest.approx(20.0)


class TestFSSSemDegraus:

    @pytest.fixture
    def calc(self):
        return FSSCalculator()

    def _fss_por_queda(self, calc, queda: float) -> float:
        return calc.calc_fss(
            UserProfile(), pl.DataFrame(),
            income_3m_avg=5_000 * (1 + queda), income_12m_avg=5_000,
        )["fss"]

    def test_queda_de_renda_e_monotonica(self, calc):
        """Quanto pior a queda, maior o estresse — sem platôs de valor zero."""
        quedas = [-0.04, -0.08, -0.12, -0.149, -0.15, -0.30]
        valores = [self._fss_por_queda(calc, q) for q in quedas]
        assert valores == sorted(valores), valores

    def test_o_ponto_de_disparo_antigo_vale_o_mesmo(self, calc):
        """
        A rampa alcança o valor cheio (+20) exatamente em -15%, onde o degrau
        disparava. Ninguém que era detectado deixa de ser.
        """
        base = self._fss_por_queda(calc, 0.0)
        assert self._fss_por_queda(calc, -0.15) == pytest.approx(base + 20.0, abs=0.1)

    def test_queda_intermediaria_deixou_de_valer_zero(self, calc):
        """Uma queda de 12% de renda era invisível para o FSS."""
        base = self._fss_por_queda(calc, 0.0)
        assert self._fss_por_queda(calc, -0.12) > base

    def test_nao_ha_salto_no_limiar(self, calc):
        """A diferença entre 14,9% e 15,1% era de 20 pontos."""
        antes = self._fss_por_queda(calc, -0.149)
        depois = self._fss_por_queda(calc, -0.151)
        assert abs(depois - antes) < 1.0

    def test_concentracao_em_credito_modula_em_vez_de_ligar_desligar(self, calc):
        """
        `credit_spend_ratio > 0.7` era portão binário: 0,699 zerava os 30
        pontos de rotativo, 0,701 liberava todos.
        """
        def fss(ratio):
            p = UserProfile(committed_percentage=0.8, credit_spend_ratio=ratio)
            return calc.calc_fss(p, pl.DataFrame(), resilience_score=70)["fss"]

        assert fss(0.45) < fss(0.60) < fss(0.70)
        assert fss(0.70) == pytest.approx(fss(0.95))   # satura no limiar antigo

    def test_poupanca_e_continua(self, calc):
        def fss(taxa):
            return calc.calc_fss(
                UserProfile(savings_rate=taxa), pl.DataFrame()
            )["fss"]

        # Monotônica decrescente: poupar mais nunca aumenta o estresse.
        valores = [fss(t) for t in (-10, -5, -2, 0, 3, 5, 10)]
        assert valores == sorted(valores, reverse=True), valores
        assert fss(-5) == pytest.approx(15.0)
        assert fss(5) == pytest.approx(0.0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cheque especial: vocabulário e base mínima
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestChequeEspecial:

    @pytest.mark.parametrize("descricao", [
        "CHEQUE ESPECIAL",
        "LIMITE ESPECIAL",
        "IOF ESPECIAL",
        "JUROS ESPECIAL",
        "ENCARGOS ESPECIAIS",          # plural — a lição do D3 na Defesa
        "ADIANTAMENTO A DEPOSITANTE",  # o termo regulado, que faltava
        "ADIANT DEPOSITANTE",
        "IOF ADIANT DEPOSITANTE",
        "JUROS LIS",                   # nome comercial do Itaú
        "USO DO LIMITE",
        "SALDO DEVEDOR",
    ])
    def test_reconhece_como_o_extrato_escreve(self, descricao):
        assert _OVERDRAFT_PATTERN.search(descricao), descricao

    @pytest.mark.parametrize("descricao", [
        "LISBOA RESTAURANTE",          # \bLIS\b não pode casar dentro de palavra
        "ESPECIARIAS LTDA",
        "COMPRA ESPECIAL DIA DAS MAES",
        "SUPERMERCADO EXTRA",
    ])
    def test_nao_captura_o_que_nao_e(self, descricao):
        assert not _OVERDRAFT_PATTERN.search(descricao), descricao

    def test_um_mes_de_historico_nao_estima_fracao(self):
        """1 mês com cobrança ÷ 1 mês de dado = 1,0 — o sinal máximo."""
        calc = FSSCalculator()
        r = calc.calc_fss(UserProfile(), _df([(0, "JUROS CHEQUE ESPECIAL")]),
                          resilience_score=80)
        assert not any("overdraft" in s for s in r["fss_signals"])

    def test_com_base_suficiente_dispara(self):
        calc = FSSCalculator()
        r = calc.calc_fss(
            UserProfile(),
            _df([(0, "JUROS CHEQUE ESPECIAL"), (1, "COMPRA MERCADO"),
                 (2, "COMPRA MERCADO")]),
            resilience_score=80,
        )
        assert any("overdraft" in s for s in r["fss_signals"])

    def test_a_fracao_e_de_meses_e_nao_de_lancamentos(self):
        """Dez cobranças no mesmo mês valem um mês, não dez."""
        calc = FSSCalculator()
        um_mes = [(0, "JUROS CHEQUE ESPECIAL")] * 10 + [(1, "MERCADO"), (2, "MERCADO")]
        dois_meses = [(0, "JUROS CHEQUE ESPECIAL"), (1, "JUROS CHEQUE ESPECIAL"),
                      (2, "MERCADO")]
        a = calc.calc_fss(UserProfile(), _df(um_mes), resilience_score=80)["fss"]
        b = calc.calc_fss(UserProfile(), _df(dois_meses), resilience_score=80)["fss"]
        assert b > a


class TestConfiancaDoFSS:
    """
    O FSS muda o comportamento de quatro módulos. Antes ele saía igual para
    quem tem 3 meses de histórico e para quem conectou a conta ontem.
    """

    @pytest.mark.parametrize("meses,esperado", [(1, 0.3), (2, 0.6), (3, 1.0), (4, 1.0)])
    def test_confianca_acompanha_a_cobertura(self, meses, esperado):
        linhas = [(m, "COMPRA MERCADO") for m in range(meses)]
        r = FSSCalculator().calc_fss(UserProfile(), _df(linhas), resilience_score=80)
        assert r["fss_confidence"] == esperado
        assert r["fss_months_covered"] == meses

    def test_sem_dado_nenhum_confianca_zero(self):
        r = FSSCalculator().calc_fss(UserProfile(), pl.DataFrame(), resilience_score=80)
        assert r["fss_confidence"] == 0.0

    def test_cobertura_parcial_aparece_nos_sinais(self):
        r = FSSCalculator().calc_fss(UserProfile(), _df([(0, "MERCADO")]),
                                     resilience_score=80)
        assert any("cobertura_parcial" in s for s in r["fss_signals"])

    def test_o_score_continua_saindo_mesmo_com_pouca_base(self):
        """Confiança baixa não é ausência de resposta — é resposta qualificada."""
        r = FSSCalculator().calc_fss(UserProfile(), _df([(0, "MERCADO")]),
                                     resilience_score=20)
        assert r["fss"] > 0
        assert r["fss_level"] in ("SAUDAVEL", "ATENCAO", "ALERTA", "CRITICO")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Corroboração no híbrido ML + regras
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCorroboracao:
    """
    Dois sinais fracos que apontam para o MESMO lugar valem mais que um sinal
    fraco sozinho — o princípio que o EvidenceScorer já aplica nos eventos de
    vida (BUFFET isolado é bloqueado; BUFFET+NOIVAS+FOTÓGRAFO passa com
    folga), aplicado no ponto mais fraco do classificador.

    Antes: ML abstém → só o piso de 0,60 salvava. O resto virava
    NAO_CLASSIFICADO, que no produto significa tom neutro no chat, nenhum
    ajuste de orçamento e nenhum bônus de ranking.
    """

    @pytest.fixture
    def lc(self):
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        return LifestyleClassifier()

    def test_ml_e_regras_concordando_abaixo_do_piso_classificam(self, lc):
        from app.optimizer.detectors.lifestyle_classifier import CLUSTER_UNCLASSIFIED

        ml_result = {
            "lifestyle_cluster": CLUSTER_UNCLASSIFIED,   # ML absteve
            "secondary_clusters": [],
            "cluster_scores": {"URBANO_FOODIE": 0.45, "DIGITAL_NATIVO": 0.20},
            "ml_probabilities": {"URBANO_FOODIE": 0.31, "DIGITAL_NATIVO": 0.22},
            "classification_source": "ml",
            "ml_confidence": 0.31,
        }
        r = lc._apply_rules_floor(UserProfile(), ml_result)
        assert r["lifestyle_cluster"] == "URBANO_FOODIE"
        assert r["classification_source"] == "ml+rules_agreement"

    def test_discordando_continua_abstendo(self, lc):
        """Corroboração exige concordância — não é só baixar o limiar."""
        from app.optimizer.detectors.lifestyle_classifier import CLUSTER_UNCLASSIFIED

        ml_result = {
            "lifestyle_cluster": CLUSTER_UNCLASSIFIED,
            "secondary_clusters": [],
            "cluster_scores": {"URBANO_FOODIE": 0.45, "DIGITAL_NATIVO": 0.20},
            "ml_probabilities": {"DIGITAL_NATIVO": 0.33, "URBANO_FOODIE": 0.10},
            "classification_source": "ml",
            "ml_confidence": 0.33,
        }
        r = lc._apply_rules_floor(UserProfile(), ml_result)
        assert r["lifestyle_cluster"] == CLUSTER_UNCLASSIFIED

    def test_regras_fracas_demais_nao_corroboram(self, lc):
        from app.optimizer.detectors.lifestyle_classifier import CLUSTER_UNCLASSIFIED

        ml_result = {
            "lifestyle_cluster": CLUSTER_UNCLASSIFIED,
            "secondary_clusters": [],
            "cluster_scores": {"URBANO_FOODIE": 0.25},   # abaixo de 0,40
            "ml_probabilities": {"URBANO_FOODIE": 0.31},
            "classification_source": "ml",
            "ml_confidence": 0.31,
        }
        assert lc._apply_rules_floor(UserProfile(), ml_result)[
            "lifestyle_cluster"] == CLUSTER_UNCLASSIFIED

    def test_ml_fraco_demais_nao_corrobora(self, lc):
        from app.optimizer.detectors.lifestyle_classifier import CLUSTER_UNCLASSIFIED

        ml_result = {
            "lifestyle_cluster": CLUSTER_UNCLASSIFIED,
            "secondary_clusters": [],
            "cluster_scores": {"URBANO_FOODIE": 0.55},
            "ml_probabilities": {"URBANO_FOODIE": 0.12},  # abaixo de 0,25
            "classification_source": "ml",
            "ml_confidence": 0.12,
        }
        assert lc._apply_rules_floor(UserProfile(), ml_result)[
            "lifestyle_cluster"] == CLUSTER_UNCLASSIFIED

    def test_o_piso_de_060_continua_valendo_sozinho(self, lc):
        """Regras confiantes vencem a abstenção mesmo sem o ML concordar."""
        from app.optimizer.detectors.lifestyle_classifier import CLUSTER_UNCLASSIFIED

        ml_result = {
            "lifestyle_cluster": CLUSTER_UNCLASSIFIED,
            "secondary_clusters": [],
            "cluster_scores": {"URBANO_FOODIE": 0.75, "DIGITAL_NATIVO": 0.10},
            "ml_probabilities": {"DIGITAL_NATIVO": 0.30, "URBANO_FOODIE": 0.05},
            "classification_source": "ml",
            "ml_confidence": 0.30,
        }
        r = lc._apply_rules_floor(UserProfile(), ml_result)
        assert r["lifestyle_cluster"] == "URBANO_FOODIE"
        assert r["classification_source"] == "ml+rules_floor"

    def test_nunca_derruba_uma_classificacao_que_o_ML_ja_fez(self, lc):
        ml_result = {
            "lifestyle_cluster": "EXPLORADOR_GLOBAL",
            "secondary_clusters": [],
            "cluster_scores": {"URBANO_FOODIE": 0.90},
            "ml_probabilities": {"EXPLORADOR_GLOBAL": 0.80},
            "classification_source": "ml",
            "ml_confidence": 0.80,
        }
        assert lc._apply_rules_floor(UserProfile(), ml_result) is ml_result


class TestInvarianteDeEstresseIntacta:
    """
    A única classificação com consequência de segurança do usuário. Nenhuma
    das mudanças pode ter tocado nela.
    """

    @pytest.fixture
    def lc(self):
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        return LifestyleClassifier()

    def test_fss_critico_nunca_passa_pelo_ML(self, lc):
        p = UserProfile(fss_level="CRITICO", fss=80.0, savings_rate=-12.0,
                        committed_percentage=0.70, spending_stability=0.20,
                        monthly_avg_spend=3_000.0)
        r = lc.classify(p)
        assert r["classification_source"] == "rules"
        assert r["lifestyle_cluster"] == "ESTRESSE_FINANCEIRO"

    @pytest.mark.parametrize("nivel", ["ALERTA", "CRITICO"])
    def test_perfil_estressado_continua_sendo_estresse(self, lc, nivel):
        p = UserProfile(fss_level=nivel, savings_rate=-15.0,
                        committed_percentage=0.75, spending_stability=0.15,
                        monthly_avg_spend=3_000.0, credit_spend_ratio=0.8)
        assert lc.classify(p)["lifestyle_cluster"] == "ESTRESSE_FINANCEIRO"
