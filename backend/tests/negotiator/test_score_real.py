"""
O Score Nexa do F13 era 50 para todo mundo, sempre.

Duas cópias idênticas de um helper — `negotiator/router.py` e
`agent/tools/get_negotiation_script.py` — faziam:

    from app.profile.user_profile_analyzer import UserProfileAnalyzer
    profile = UserProfileAnalyzer().analyze(transactions_df, user_id=user_id)
    return profile.health_score

`app.profile` não existe no projeto. Três erros na mesma linha e meia: o módulo
(o analisador vive em `app.forecast.etl.profiles`), o parâmetro (`analyze()`
recebe `df, income_profile, committed_pct` — nunca `user_id`) e o campo (é
`financial_health_score`). O `ModuleNotFoundError` caía no `except` e voltava
50 — um número que atravessava dois portões de detecção, o prompt do Claude, o
texto do roteiro de emergência e o `estimated_success_pct`.

Consequência mais dura: `_detect_score_only` exige ≥ 70. Com 50 fixo, o gatilho
`HEALTH_SCORE_ALTO` NUNCA disparou — nem para quem tem 90.

O card viral não muda: `HEALTH_SCORE_ALTO` nasce com
`potential_saving_monthly=0.0`.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from app.negotiator.health_score import score_nexa
from app.negotiator.models import NegotiationTrigger
from app.negotiator.opportunity_detector import NegotiationOpportunityDetector
from app.negotiator.script_generator import NegotiationScriptGenerator


def _extrato(renda: float, despesa: float, meses: int = 6) -> pl.DataFrame:
    linhas = []
    for m in range(1, meses + 1):
        linhas += [
            {"date": dt.date(2026, m, 5), "amount": renda,
             "description": "SALARIO EMPRESA XYZ", "category": "Renda"},
            {"date": dt.date(2026, m, 12), "amount": -despesa,
             "description": "ALUGUEL", "category": "Moradia"},
        ]
    return pl.DataFrame(linhas)


# ── 1. O score responde ao extrato ─────────────────────────────────────────

class TestScoreEhReal:

    def test_o_modulo_que_o_codigo_importava_nao_existe(self):
        """A causa raiz, travada: se `app.profile` um dia existir, é outro
        módulo — e ninguém deve voltar a importar de lá sem revisar."""
        with pytest.raises(ModuleNotFoundError):
            __import__("app.profile.user_profile_analyzer")

    def test_o_analisador_de_verdade_nao_aceita_user_id(self):
        """O segundo erro da linha: `analyze()` nunca teve esse parâmetro."""
        import inspect

        from app.forecast.etl.profiles import UserProfileAnalyzer

        params = inspect.signature(UserProfileAnalyzer.analyze).parameters
        assert "user_id" not in params
        assert {"df", "income_profile", "committed_pct"} <= set(params)

    def test_o_campo_e_financial_health_score(self):
        """O terceiro erro: `profile.health_score` não existe."""
        from app.forecast.etl.profiles import UserProfile

        assert "financial_health_score" in UserProfile.__dataclass_fields__
        assert "health_score" not in UserProfile.__dataclass_fields__

    def test_poupador_e_gastador_nao_recebem_o_mesmo_numero(self):
        """
        O sintoma direto: enquanto o import quebrava, os dois valiam 50.
        """
        poupador = score_nexa(_extrato(renda=10_000.0, despesa=3_000.0))
        gastador = score_nexa(_extrato(renda=10_000.0, despesa=9_800.0))

        assert poupador is not None and gastador is not None
        assert poupador > gastador
        assert poupador - gastador >= 20

    def test_bate_com_a_regua_unica(self):
        """Mesma fonte do resto do produto — não uma quinta fórmula."""
        from app.forecast.etl.income_profiler import IncomeProfiler
        from app.forecast.etl.profiles import UserProfileAnalyzer

        df = _extrato(renda=8_000.0, despesa=5_000.0)
        esperado = UserProfileAnalyzer().analyze(
            df, income_profile=IncomeProfiler().build(df)
        ).financial_health_score
        assert score_nexa(df) == esperado

    @pytest.mark.parametrize("entrada", [None, pl.DataFrame({"amount": [], "date": []})])
    def test_sem_dado_devolve_None_e_nao_50(self, entrada):
        """
        `None` é "não sei". `50` é uma afirmação — e era falsa para todos.
        """
        assert score_nexa(entrada) is None

    def test_nunca_devolve_50_fixo_para_extratos_diferentes(self):
        scores = {
            score_nexa(_extrato(renda=10_000.0, despesa=d))
            for d in (1_000.0, 4_000.0, 7_000.0, 9_500.0)
        }
        assert len(scores) > 1
        assert scores != {50}


# ── 2. O gatilho que estava morto para 100% dos usuários ───────────────────

class TestHealthScoreAltoVoltouAExistir:

    @staticmethod
    def _detectar(score):
        # Extrato limpo: sem tarifas, para que só o caminho de score reste.
        df = _extrato(renda=12_000.0, despesa=2_000.0)
        return NegotiationOpportunityDetector().detect(df, health_score=score)

    def test_com_score_alto_o_gatilho_dispara(self):
        gatilhos = {o.trigger for o in self._detectar(85)}
        assert NegotiationTrigger.HEALTH_SCORE_ALTO in gatilhos

    @pytest.mark.parametrize("score", [50, 59, 69])
    def test_abaixo_de_70_nao_dispara(self, score):
        """
        Inclui o 50 que o import quebrado devolvia: é por isso que o caminho
        nunca era exercitado.
        """
        gatilhos = {o.trigger for o in self._detectar(score)}
        assert NegotiationTrigger.HEALTH_SCORE_ALTO not in gatilhos

    def test_sem_score_nao_dispara(self):
        """
        A oportunidade INTEIRA é a frase "seu score é X/100". Sem X, não há
        oportunidade — e chutar seria pior que não oferecer.
        """
        assert self._detectar(None) == []

    def test_nao_altera_o_card_viral(self):
        """
        `HEALTH_SCORE_ALTO` nasce com economia zero, então o total do
        consolidador não muda por causa desta correção.
        """
        opps = [o for o in self._detectar(85)
                if o.trigger == NegotiationTrigger.HEALTH_SCORE_ALTO]
        assert opps and all(o.potential_saving_monthly == 0.0 for o in opps)


# ── 3. O número não vaza como se tivesse sido medido ───────────────────────

class TestSemScoreNadaAfirmaScore:

    @staticmethod
    def _oportunidade(score):
        from app.negotiator.models import NegotiationOpportunity

        return NegotiationOpportunity(
            trigger=NegotiationTrigger.ANUIDADE_ALTA,
            bank_name="Banco X",
            product="Anuidade Cartão",
            user_fee_monthly=40.0,
            potential_saving_monthly=40.0,
            health_score=score,
            months_as_good_payer=6,
        )

    def test_o_roteiro_de_emergencia_omite_o_argumento_de_score(self):
        script = NegotiationScriptGenerator._fallback_script(self._oportunidade(None))
        assert not any("score" in a.lower() for a in script.key_arguments)
        assert all(a for a in script.key_arguments)

    def test_com_score_o_argumento_aparece_com_o_numero_certo(self):
        script = NegotiationScriptGenerator._fallback_script(self._oportunidade(88))
        assert any("88/100" in a for a in script.key_arguments)

    def test_estimated_success_nao_herda_um_50_fabricado(self):
        sem = NegotiationScriptGenerator._fallback_script(self._oportunidade(None))
        com = NegotiationScriptGenerator._fallback_script(self._oportunidade(80))
        assert sem.estimated_success_pct == 40
        assert com.estimated_success_pct == 80

    def test_o_prompt_do_modelo_nao_inventa_score(self):
        gen = NegotiationScriptGenerator()
        prompt = gen._build_prompt(self._oportunidade(None))
        assert "None" not in prompt
        assert "não calculado" in prompt

    def test_o_prompt_carrega_o_score_quando_existe(self):
        gen = NegotiationScriptGenerator()
        assert "77/100" in gen._build_prompt(self._oportunidade(77))


# ── 4. A confiança do relatório não some um termo constante ────────────────

class TestConfiancaDoRelatorio:

    def test_sem_score_o_termo_vale_zero(self):
        from app.negotiator.router import _compute_confidence

        assert _compute_confidence(None, 1, 90) == pytest.approx(0.70)

    def test_com_score_o_termo_entra(self):
        from app.negotiator.router import _compute_confidence

        assert _compute_confidence(90, 1, 90) == pytest.approx(0.97)

    def test_o_50_fabricado_valia_sempre_o_mesmo(self):
        """
        Trava a diferença: 50 dava 0,15 fixo para todo usuário, indistinguível
        de um score real de 50.
        """
        from app.negotiator.router import _compute_confidence

        assert _compute_confidence(50, 1, 90) == pytest.approx(0.85)
        assert _compute_confidence(None, 1, 90) < _compute_confidence(50, 1, 90)


# ── 5. Uma fonte só ────────────────────────────────────────────────────────

class TestFonteUnicaDoScore:

    def test_nao_ha_mais_copia_local_do_helper(self):
        import app.agent.tools.get_negotiation_script as tool
        import app.negotiator.router as router

        assert not hasattr(router, "_get_health_score")
        assert not hasattr(tool, "_get_health_score")
        assert tool.score_nexa is router.score_nexa is score_nexa

    def test_o_quarto_health_score_nao_existe_mais(self):
        """
        `app/domain/finance_engine.py` tinha uma QUINTA régua (baldes 50/30/20),
        sem nenhum consumidor — armadilha para quem procurasse "o health score".
        """
        with pytest.raises(ModuleNotFoundError):
            __import__("app.domain.finance_engine")


# ── 6. O marcador que teria denunciado o import quebrado ───────────────────

class TestMarcadorDeFonte:
    """
    `data_sources` é o padrão que expôs as quatro integrações mortas do F7
    (ver tests/purchase/test_advisor_producao.py). O F13 não tinha marcador
    nenhum para o perfil — por isso o helper pôde morrer sem ninguém notar.
    """

    @staticmethod
    def _relatorio(score):
        import datetime as _dt
        from unittest.mock import MagicMock, patch

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.core.security import get_current_user
        from app.negotiator.router import router

        usuario = "user_marcador_fonte"
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: usuario
        cliente = TestClient(app)

        hoje = _dt.date.today()
        df = pl.DataFrame({
            "user_id": [usuario] * 6,
            "date": [hoje - _dt.timedelta(days=i * 10) for i in range(6)],
            "description": ["MERCADO"] * 6,
            "amount": [-150.0] * 6,
            "category": ["alimentacao"] * 6,
            "transaction_type": ["DEBIT"] * 6,
        })

        detector = MagicMock()
        detector.detect.return_value = []
        with patch("app.core.db.queries.get_transactions_for_user", return_value=df), \
             patch("app.negotiator.router.score_nexa", return_value=score), \
             patch("app.negotiator.router.NegotiationOpportunityDetector",
                   return_value=detector):
            resposta = cliente.post(
                "/negotiator/generate-script", json={"user_id": usuario}
            )
        assert resposta.status_code == 200
        return resposta.json()

    def test_com_score_o_relatorio_declara_a_fonte(self):
        assert "user_profile_analyzer" in self._relatorio(78)["data_sources"]

    def test_sem_score_a_fonte_nao_e_declarada_e_ha_aviso(self):
        dados = self._relatorio(None)
        assert "user_profile_analyzer" not in dados["data_sources"]
        assert any("Score Nexa indisponível" in a for a in dados["warnings"])

    def test_o_resumo_nao_afirma_um_score_que_nao_existe(self):
        assert "/100" not in self._relatorio(None)["summary"]
