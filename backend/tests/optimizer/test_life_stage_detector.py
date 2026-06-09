# tests/optimizer/test_life_stage_detector.py
# Testes unitários para LifeStageDetector e refine_with_life_events.

from __future__ import annotations

import pytest

from app.optimizer.constants import (
    LIFE_STAGE_FAMILIA_BEBE,
    LIFE_STAGE_NOMADE_DIGITAL,
    LIFE_STAGE_INVESTIDOR_PREMIUM,
    LIFE_STAGE_SOLTEIRO_URBANO,
    LIFE_STAGE_NAO_IDENTIFICADO,
    LIFE_STAGE_MIN_CONFIDENCE,
)
from app.optimizer.detectors.life_stage_detector import LifeStageDetector, refine_with_life_events
from app.optimizer.profiler import UserProfile


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _profile(**kwargs) -> UserProfile:
    """Cria um UserProfile vazio e aplica os kwargs como atributos."""
    p = UserProfile()
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


def _detect(profile: UserProfile) -> dict:
    return LifeStageDetector().detect(profile)


# ─── FAMILIA_BEBE ─────────────────────────────────────────────────────────────

class TestFamiliaBebe:

    def test_sinal_primario_is_family_with_kids(self):
        p = _profile(is_family_with_kids=True, family_score=70.0)
        result = _detect(p)
        assert result["life_stage"] == LIFE_STAGE_FAMILIA_BEBE
        assert result["life_stage_confidence"] >= 0.65

    def test_family_score_alto_eleva_confianca(self):
        p_low  = _profile(is_family_with_kids=True, family_score=40.0)
        p_high = _profile(is_family_with_kids=True, family_score=100.0)
        r_low  = _detect(p_low)
        r_high = _detect(p_high)
        assert r_high["life_stage_confidence"] > r_low["life_stage_confidence"]

    def test_farmacia_reforco_adiciona_score(self):
        base = _profile(is_family_with_kids=True, family_score=60.0)
        com_farmacia = _profile(
            is_family_with_kids=True, family_score=60.0,
            spend_by_category={"farmacia": 250},
        )
        assert _detect(com_farmacia)["life_stage_scores"][LIFE_STAGE_FAMILIA_BEBE] > \
               _detect(base)["life_stage_scores"][LIFE_STAGE_FAMILIA_BEBE]

    def test_educacao_reforco_adiciona_score(self):
        base = _profile(is_family_with_kids=True, family_score=60.0)
        com_edu = _profile(
            is_family_with_kids=True, family_score=60.0,
            spend_by_category={"educacao": 250},
        )
        assert _detect(com_edu)["life_stage_scores"][LIFE_STAGE_FAMILIA_BEBE] > \
               _detect(base)["life_stage_scores"][LIFE_STAGE_FAMILIA_BEBE]

    def test_sem_is_family_nao_classifica(self):
        p = _profile(is_family_with_kids=False, spend_by_category={"farmacia": 300})
        result = _detect(p)
        assert result["life_stage_scores"][LIFE_STAGE_FAMILIA_BEBE] < 0.40

    def test_familia_bebe_nao_coexiste_com_nomade(self):
        p = _profile(
            is_family_with_kids=True, family_score=80.0,
            is_digital_nomad=False,
        )
        result = _detect(p)
        assert result["life_stage"] == LIFE_STAGE_FAMILIA_BEBE


# ─── NOMADE_DIGITAL ───────────────────────────────────────────────────────────

class TestNomadeDigital:

    def test_is_digital_nomad_retorna_085(self):
        p = _profile(is_digital_nomad=True)
        result = _detect(p)
        assert result["life_stage"] == LIFE_STAGE_NOMADE_DIGITAL
        assert result["life_stage_confidence"] == pytest.approx(0.85, abs=0.01)

    def test_airbnb_mais_viagem_alta(self):
        p = _profile(is_airbnb_user=True, travel_spend_monthly=900)
        result = _detect(p)
        assert result["life_stage"] == LIFE_STAGE_NOMADE_DIGITAL
        assert result["life_stage_confidence"] >= 0.50

    def test_airbnb_sem_viagem_nao_atinge_threshold(self):
        p = _profile(is_airbnb_user=True, travel_spend_monthly=50)
        result = _detect(p)
        assert result["life_stage_scores"][LIFE_STAGE_NOMADE_DIGITAL] < 0.40

    def test_coworking_category_ativa_sinal(self):
        p = _profile(
            is_airbnb_user=True,
            travel_spend_monthly=400,
            spend_by_category={"coworking": 300},
        )
        result = _detect(p)
        assert result["life_stage"] == LIFE_STAGE_NOMADE_DIGITAL
        assert result["life_stage_confidence"] >= 0.55

    def test_subscription_burn_alto_reforco(self):
        sem = _profile(is_airbnb_user=True, travel_spend_monthly=400)
        com = _profile(is_airbnb_user=True, travel_spend_monthly=400, subscription_burn_monthly=200)
        assert _detect(com)["life_stage_scores"][LIFE_STAGE_NOMADE_DIGITAL] > \
               _detect(sem)["life_stage_scores"][LIFE_STAGE_NOMADE_DIGITAL]


# ─── INVESTIDOR_PREMIUM ───────────────────────────────────────────────────────

class TestInvestidorPremium:

    def test_investidor_ativo_mais_renda_alta_mais_baixa_divida(self):
        p = _profile(
            investor_type="ATIVO",
            estimated_monthly_income=15_000,
            committed_percentage=0.10,
            savings_rate=30.0,
        )
        result = _detect(p)
        assert result["life_stage"] == LIFE_STAGE_INVESTIDOR_PREMIUM
        assert result["life_stage_confidence"] >= 0.80

    def test_investidor_diversificado_classifica(self):
        p = _profile(
            investor_type="DIVERSIFICADO",
            estimated_monthly_income=10_000,
            committed_percentage=0.20,
        )
        result = _detect(p)
        assert result["life_stage"] == LIFE_STAGE_INVESTIDOR_PREMIUM

    def test_investidor_casual_renda_baixa_nao_atinge_threshold(self):
        p = _profile(
            investor_type="CASUAL",
            estimated_monthly_income=3_000,
            committed_percentage=0.50,
        )
        result = _detect(p)
        assert result["life_stage_scores"][LIFE_STAGE_INVESTIDOR_PREMIUM] < 0.40

    def test_sem_investor_type_nao_classifica(self):
        p = _profile(investor_type="NONE", estimated_monthly_income=20_000)
        result = _detect(p)
        assert result["life_stage_scores"][LIFE_STAGE_INVESTIDOR_PREMIUM] < 0.40

    def test_renda_alta_sem_investidor_nao_suficiente(self):
        p = _profile(investor_type="NONE", estimated_monthly_income=50_000)
        result = _detect(p)
        assert result["life_stage_scores"][LIFE_STAGE_INVESTIDOR_PREMIUM] < 0.40

    def test_committed_baixo_reforco(self):
        alto = _profile(investor_type="ATIVO", estimated_monthly_income=10_000, committed_percentage=0.60)
        baixo = _profile(investor_type="ATIVO", estimated_monthly_income=10_000, committed_percentage=0.10)
        assert _detect(baixo)["life_stage_scores"][LIFE_STAGE_INVESTIDOR_PREMIUM] > \
               _detect(alto)["life_stage_scores"][LIFE_STAGE_INVESTIDOR_PREMIUM]


# ─── SOLTEIRO_URBANO ──────────────────────────────────────────────────────────

class TestSolteiroUrbano:

    def test_delivery_alto_mais_pouco_supermercado(self):
        p = _profile(
            is_family_with_kids=False,
            category_trends={"_delivery": {"current_monthly": 400.0, "direction": "SUBINDO"}},
            spend_by_category={"supermercado": 60},
            subscription_burn_monthly=120,
            merchant_diversity_score=72,
        )
        result = _detect(p)
        assert result["life_stage"] == LIFE_STAGE_SOLTEIRO_URBANO
        assert result["life_stage_confidence"] >= 0.75

    def test_delivery_moderado_sem_supermercado_classifica(self):
        p = _profile(
            is_family_with_kids=False,
            category_trends={"_delivery": {"current_monthly": 200.0}},
            spend_by_category={"supermercado": 30},
        )
        result = _detect(p)
        assert result["life_stage_scores"][LIFE_STAGE_SOLTEIRO_URBANO] >= 0.40

    def test_family_with_kids_reduz_score(self):
        sem = _profile(
            is_family_with_kids=False,
            category_trends={"_delivery": {"current_monthly": 300.0}},
            spend_by_category={"supermercado": 50},
        )
        com = _profile(
            is_family_with_kids=True,
            family_score=60.0,
            category_trends={"_delivery": {"current_monthly": 300.0}},
            spend_by_category={"supermercado": 50},
        )
        # Com família, FAMILIA_BEBE deve ganhar; sem família, SOLTEIRO_URBANO deve liderar
        r_sem = _detect(sem)
        r_com = _detect(com)
        assert r_sem["life_stage_scores"][LIFE_STAGE_SOLTEIRO_URBANO] > \
               r_com["life_stage_scores"][LIFE_STAGE_SOLTEIRO_URBANO]
        assert r_com["life_stage"] == LIFE_STAGE_FAMILIA_BEBE

    def test_fallback_spend_by_category_delivery(self):
        # Sem category_trends, usa spend_by_category["delivery"] como fallback
        p = _profile(
            is_family_with_kids=False,
            spend_by_category={"delivery": 350, "supermercado": 60},
            subscription_burn_monthly=100,
        )
        result = _detect(p)
        assert result["life_stage"] == LIFE_STAGE_SOLTEIRO_URBANO

    def test_pouco_delivery_nao_atinge_threshold(self):
        p = _profile(
            is_family_with_kids=False,
            category_trends={"_delivery": {"current_monthly": 30.0}},
            spend_by_category={"supermercado": 800},  # alto supermercado → não é solteiro urbano
        )
        result = _detect(p)
        assert result["life_stage_scores"][LIFE_STAGE_SOLTEIRO_URBANO] < 0.40


# ─── NAO_IDENTIFICADO ─────────────────────────────────────────────────────────

class TestNaoIdentificado:

    def test_perfil_vazio_retorna_nao_identificado(self):
        p = UserProfile()
        result = _detect(p)
        assert result["life_stage"] == LIFE_STAGE_NAO_IDENTIFICADO
        assert result["life_stage_confidence"] == 0.0

    def test_sinais_fracos_nao_atingem_threshold(self):
        p = _profile(
            is_airbnb_user=True,  # travel mas fraco
            investor_type="CASUAL",  # investidor mas casual
            subscription_burn_monthly=30,
        )
        result = _detect(p)
        assert result["life_stage"] == LIFE_STAGE_NAO_IDENTIFICADO

    def test_todos_scores_retornados(self):
        p = UserProfile()
        result = _detect(p)
        assert set(result["life_stage_scores"].keys()) == {
            LIFE_STAGE_FAMILIA_BEBE,
            LIFE_STAGE_NOMADE_DIGITAL,
            LIFE_STAGE_INVESTIDOR_PREMIUM,
            LIFE_STAGE_SOLTEIRO_URBANO,
        }

    def test_confianca_zero_quando_nao_identificado(self):
        p = UserProfile()
        result = _detect(p)
        assert result["life_stage_confidence"] == 0.0


# ─── refine_with_life_events ─────────────────────────────────────────────────

class TestRefineWithLifeEvents:

    def test_new_baby_evento_promove_para_familia_bebe(self):
        p = UserProfile()
        assert p.life_stage == LIFE_STAGE_NAO_IDENTIFICADO
        events = [{"event": "new_baby", "confidence": 0.75}]
        refine_with_life_events(p, events)
        assert p.life_stage == LIFE_STAGE_FAMILIA_BEBE
        assert p.life_stage_confidence > 0.0

    def test_new_baby_eleva_confianca_quando_ja_familia_bebe(self):
        p = _profile(
            is_family_with_kids=True, family_score=70.0,
            life_stage=LIFE_STAGE_FAMILIA_BEBE,
            life_stage_confidence=0.80,
        )
        events = [{"event": "new_baby", "confidence": 0.85}]
        refine_with_life_events(p, events)
        assert p.life_stage_confidence > 0.80

    def test_new_baby_confianca_baixa_nao_dispara(self):
        p = UserProfile()
        events = [{"event": "new_baby", "confidence": 0.50}]  # < 0.60
        refine_with_life_events(p, events)
        assert p.life_stage == LIFE_STAGE_NAO_IDENTIFICADO

    def test_outros_eventos_nao_alteram_estagio(self):
        p = _profile(
            investor_type="ATIVO",
            estimated_monthly_income=15_000,
            committed_percentage=0.10,
            life_stage=LIFE_STAGE_INVESTIDOR_PREMIUM,
            life_stage_confidence=0.90,
        )
        events = [{"event": "income_increase", "confidence": 0.80}]
        refine_with_life_events(p, events)
        assert p.life_stage == LIFE_STAGE_INVESTIDOR_PREMIUM

    def test_lista_vazia_nao_altera_nada(self):
        p = _profile(life_stage=LIFE_STAGE_NOMADE_DIGITAL, life_stage_confidence=0.85)
        refine_with_life_events(p, [])
        assert p.life_stage == LIFE_STAGE_NOMADE_DIGITAL
        assert p.life_stage_confidence == 0.85

    def test_new_baby_confianca_cap_095(self):
        p = UserProfile()
        events = [{"event": "new_baby", "confidence": 0.95}]
        refine_with_life_events(p, events)
        assert p.life_stage_confidence <= 0.95

    def test_life_stage_scores_atualizado(self):
        p = UserProfile()
        events = [{"event": "new_baby", "confidence": 0.70}]
        refine_with_life_events(p, events)
        assert p.life_stage_scores.get(LIFE_STAGE_FAMILIA_BEBE, 0.0) > 0.0


# ─── Scores retornados são válidos ───────────────────────────────────────────

class TestScoresValidos:

    @pytest.mark.parametrize("stage,kwargs", [
        (LIFE_STAGE_FAMILIA_BEBE,       {"is_family_with_kids": True, "family_score": 80.0}),
        (LIFE_STAGE_NOMADE_DIGITAL,     {"is_digital_nomad": True}),
        (LIFE_STAGE_INVESTIDOR_PREMIUM, {"investor_type": "ATIVO", "estimated_monthly_income": 15_000, "committed_percentage": 0.10}),
        (LIFE_STAGE_SOLTEIRO_URBANO,    {"is_family_with_kids": False, "category_trends": {"_delivery": {"current_monthly": 400.0}}, "spend_by_category": {"supermercado": 60}}),
    ])
    def test_scores_entre_0_e_1(self, stage, kwargs):
        result = _detect(_profile(**kwargs))
        for v in result["life_stage_scores"].values():
            assert 0.0 <= v <= 1.0, f"Score fora do range: {v}"

    @pytest.mark.parametrize("stage,kwargs", [
        (LIFE_STAGE_FAMILIA_BEBE,       {"is_family_with_kids": True, "family_score": 80.0}),
        (LIFE_STAGE_NOMADE_DIGITAL,     {"is_digital_nomad": True}),
        (LIFE_STAGE_INVESTIDOR_PREMIUM, {"investor_type": "ATIVO", "estimated_monthly_income": 15_000, "committed_percentage": 0.10}),
        (LIFE_STAGE_SOLTEIRO_URBANO,    {"is_family_with_kids": False, "category_trends": {"_delivery": {"current_monthly": 400.0}}, "spend_by_category": {"supermercado": 60}}),
    ])
    def test_confianca_acima_do_threshold_quando_classificado(self, stage, kwargs):
        result = _detect(_profile(**kwargs))
        assert result["life_stage"] == stage
        assert result["life_stage_confidence"] >= LIFE_STAGE_MIN_CONFIDENCE
