# tests/optimizer/test_ab_testing.py
# Testes para T3.5 — A/B Testing Framework

import pytest
from unittest.mock import MagicMock, patch

from app.core.ab_testing import (
    ABVariant,
    Experiment,
    EXPERIMENTS,
    get_variant,
    log_exposure,
)
from app.optimizer.insight_generator import InsightGenerator
from app.optimizer.profiler import UserProfile
from app.optimizer.models import (
    CardSimulationResult,
    CardFlag,
    LiquidityRisk,
    BenefitTag,
)


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _result(
    card_id: str = "card-a",
    net_gain_expected: float = 600.0,
    confidence_score: float = 0.80,
    eligibility_score: float = 0.90,
    benefit_tags: list[BenefitTag] | None = None,
) -> CardSimulationResult:
    return CardSimulationResult(
        card_id=card_id,
        card_name=f"Cartão {card_id}",
        issuer="Banco Teste",
        flag=CardFlag.VISA,
        annuity_effective=0.0,
        annuity_waived=True,
        points_value_min=net_gain_expected * 0.8,
        points_value_expected=net_gain_expected,
        points_value_max=net_gain_expected * 1.2,
        net_gain_min=net_gain_expected * 0.8,
        net_gain_expected=net_gain_expected,
        net_gain_max=net_gain_expected * 1.2,
        liquidity_impact=0.0,
        liquidity_risk=LiquidityRisk.SAFE,
        confidence_score=confidence_score,
        eligibility_score=eligibility_score,
        benefit_tags=benefit_tags or [],
    )


def _profile(cluster: str = "NAO_CLASSIFICADO", monthly_avg_spend: float = 3000.0) -> UserProfile:
    return UserProfile(
        monthly_avg_spend=monthly_avg_spend,
        lifestyle_cluster=cluster,
    )


# ─── Testes: get_variant ─────────────────────────────────────────────────────────

class TestGetVariant:
    def test_deterministic_same_user_same_result(self):
        v1 = get_variant("user-abc", "ranker_v2_hyperpersonalized")
        v2 = get_variant("user-abc", "ranker_v2_hyperpersonalized")
        assert v1 == v2

    def test_deterministic_across_experiments(self):
        # experimentos diferentes podem dar variantes diferentes para o mesmo usuário
        v_ranker = get_variant("user-xyz", "ranker_v2_hyperpersonalized")
        v_tone = get_variant("user-xyz", "cluster_tone_personalization")
        # só verificamos que ambos são ABVariant válidos
        assert v_ranker in (ABVariant.CONTROL, ABVariant.TREATMENT)
        assert v_tone in (ABVariant.CONTROL, ABVariant.TREATMENT)

    def test_returns_abvariant_enum(self):
        v = get_variant("any-user", "life_events_nudge")
        assert isinstance(v, ABVariant)

    def test_unknown_experiment_raises_valueerror(self):
        with pytest.raises(ValueError, match="não registrado"):
            get_variant("user-1", "experimento_que_nao_existe")

    def test_distribution_approximately_50_50(self):
        n = 10_000
        treatment = sum(
            1 for i in range(n)
            if get_variant(f"u-{i}", "ranker_v2_hyperpersonalized") == ABVariant.TREATMENT
        )
        ratio = treatment / n
        # Tolerância de ±3% sobre 10k amostras
        assert 0.47 <= ratio <= 0.53, f"Distribuição fora do esperado: {ratio:.3f}"

    def test_different_users_can_have_different_variants(self):
        # Com 20 usuários e hash MD5, é quase certo ter pelo menos 1 de cada lado
        variants = {get_variant(f"user-{i}", "ranker_v2_hyperpersonalized") for i in range(20)}
        assert len(variants) == 2, "Esperava encontrar CONTROL e TREATMENT entre 20 usuários"

    @pytest.mark.parametrize("exp_name", list(EXPERIMENTS))
    def test_all_registered_experiments_work(self, exp_name):
        v = get_variant("test-user", exp_name)
        assert v in (ABVariant.CONTROL, ABVariant.TREATMENT)


# ─── Testes: EXPERIMENTS registry ───────────────────────────────────────────────

class TestExperimentsRegistry:
    def test_three_experiments_registered(self):
        assert len(EXPERIMENTS) == 3

    def test_required_experiments_present(self):
        assert "ranker_v2_hyperpersonalized" in EXPERIMENTS
        assert "cluster_tone_personalization" in EXPERIMENTS
        assert "life_events_nudge" in EXPERIMENTS

    def test_experiment_is_dataclass(self):
        exp = EXPERIMENTS["ranker_v2_hyperpersonalized"]
        assert isinstance(exp, Experiment)
        assert exp.name == "ranker_v2_hyperpersonalized"
        assert 0.0 < exp.traffic_pct <= 1.0

    def test_all_experiments_have_description(self):
        for name, exp in EXPERIMENTS.items():
            assert exp.description, f"Experimento '{name}' sem descrição"


# ─── Testes: log_exposure ────────────────────────────────────────────────────────

class TestLogExposure:
    def test_logs_at_info_level(self):
        with patch("app.core.ab_testing.logger") as mock_logger:
            log_exposure("user-1", "ranker_v2_hyperpersonalized", ABVariant.TREATMENT)
            mock_logger.info.assert_called_once()

    def test_log_contains_user_id(self):
        with patch("app.core.ab_testing.logger") as mock_logger:
            log_exposure("user-99", "ranker_v2_hyperpersonalized", ABVariant.CONTROL)
            call_args = mock_logger.info.call_args
            # O formato é posicional: (msg, user_id, experiment, variant)
            assert "user-99" in call_args.args

    def test_log_contains_variant(self):
        with patch("app.core.ab_testing.logger") as mock_logger:
            log_exposure("u", "life_events_nudge", ABVariant.TREATMENT)
            call_args = mock_logger.info.call_args
            assert "treatment" in call_args.args or ABVariant.TREATMENT.value in str(call_args)


# ─── Testes: InsightGenerator — enable_cluster_tone ────────────────────────────

class TestInsightGeneratorClusterTone:
    def setup_method(self):
        self.ig = InsightGenerator()

    def test_control_returns_base_description_unchanged(self):
        profile = _profile(cluster="EXPLORADOR_GLOBAL")
        base = "Texto base do insight."
        result = self.ig._personalize_description(
            base, profile, 1200.0, enable_cluster_tone=False
        )
        assert result == base

    def test_treatment_personalizes_known_cluster(self):
        profile = _profile(cluster="EXPLORADOR_GLOBAL")
        base = "Texto base do insight."
        result = self.ig._personalize_description(
            base, profile, 1200.0, enable_cluster_tone=True
        )
        assert result != base
        assert "viaja" in result.lower() or "milhas" in result.lower()

    def test_treatment_unknown_cluster_returns_base(self):
        profile = _profile(cluster="NAO_CLASSIFICADO")
        base = "Texto base do insight."
        result = self.ig._personalize_description(
            base, profile, 1200.0, enable_cluster_tone=True
        )
        assert result == base

    def test_control_cluster_insights_not_generated(self):
        # enable_cluster_tone=False → _generate_cluster_insights não deve ser chamado
        results = [_result()]
        profile = _profile(cluster="EXPLORADOR_GLOBAL", monthly_avg_spend=3000.0)
        profile.travel_spend_monthly = 1000.0  # gatilho para cluster insight de viagem

        with patch.object(self.ig, "_generate_cluster_insights", return_value=[]) as mock_cluster:
            self.ig.generate(
                ranked_results=results,
                profile=profile,
                enable_cluster_tone=False,
            )
            mock_cluster.assert_not_called()

    def test_treatment_cluster_insights_are_generated(self):
        results = [_result()]
        profile = _profile(cluster="EXPLORADOR_GLOBAL", monthly_avg_spend=3000.0)
        profile.travel_spend_monthly = 1000.0

        with patch.object(self.ig, "_generate_cluster_insights", return_value=[]) as mock_cluster:
            self.ig.generate(
                ranked_results=results,
                profile=profile,
                enable_cluster_tone=True,
            )
            mock_cluster.assert_called_once()

    def test_default_enable_cluster_tone_is_true(self):
        # Sem passar o parâmetro, comportamento é TREATMENT (True)
        results = [_result()]
        profile = _profile(cluster="NAO_CLASSIFICADO")

        with patch.object(self.ig, "_generate_cluster_insights", return_value=[]) as mock_cluster:
            self.ig.generate(ranked_results=results, profile=profile)
            mock_cluster.assert_called_once()

    @pytest.mark.parametrize("cluster,expected_keyword", [
        ("URBANO_FOODIE",       "alimentação"),
        ("INVESTIDOR_CAUTELOSO","oportunidade"),
        ("FAMILIA_ESTRUTURADA", "família"),
    ])
    def test_each_cluster_has_distinct_tone(self, cluster, expected_keyword):
        profile = _profile(cluster=cluster)
        result = self.ig._personalize_description(
            "base text.", profile, 500.0, enable_cluster_tone=True
        )
        assert expected_keyword.lower() in result.lower(), (
            f"Cluster {cluster}: esperava '{expected_keyword}' em '{result}'"
        )


# ─── Testes: integração OptimizerService — seleção de ranker ────────────────────

class TestOptimizerServiceABRanker:
    """Verifica que o OptimizerService usa o ranker correto conforme a variante."""

    def _make_service(self):
        from app.optimizer.services.optimizer_service import OptimizerService
        from app.optimizer.ranking import CardRanking

        svc = OptimizerService.__new__(OptimizerService)
        svc.knowledge_base = MagicMock()
        svc.knowledge_base._cards = [MagicMock()]
        svc.knowledge_base.filter_eligible.return_value = []
        svc.knowledge_base.get_by_id.return_value = None
        svc.profiler = MagicMock()
        svc.profiler.build.return_value = UserProfile(monthly_avg_spend=2000.0)
        svc.simulator = MagicMock()
        svc.ranking = MagicMock(spec=CardRanking)
        svc.ranking.rank.return_value = []
        svc.ranking.rank_hyperpersonalized.return_value = []
        svc.insight_generator = MagicMock()
        svc.insight_generator.generate.return_value = []
        svc.validator = MagicMock()
        return svc

    def _make_request(self, user_id: str):
        from app.optimizer.models import OptimizationRequest
        return OptimizationRequest(
            user_id=user_id,
            current_cards=[],
            safe_to_spend=2000.0,
        )

    def _run_analyze(self, svc, user_id: str):
        import polars as pl
        from datetime import date

        request = self._make_request(user_id)
        df = pl.DataFrame(
            {"date": [date(2026, 1, 15)], "amount": [-500.0], "description": ["test"]},
            schema={"date": pl.Date, "amount": pl.Float64, "description": pl.Utf8},
        )
        svc.analyze(request, df)

    def _find_user_for_variant(self, experiment: str, wanted: ABVariant) -> str:
        for i in range(200):
            uid = f"ab-test-user-{i}"
            if get_variant(uid, experiment) == wanted:
                return uid
        raise RuntimeError(f"Não encontrou usuário para variante {wanted} em {experiment}")

    def test_control_uses_classic_rank(self):
        svc = self._make_service()
        uid = self._find_user_for_variant("ranker_v2_hyperpersonalized", ABVariant.CONTROL)

        self._run_analyze(svc, uid)

        svc.ranking.rank.assert_called_once()
        svc.ranking.rank_hyperpersonalized.assert_not_called()

    def test_treatment_uses_hyperpersonalized_rank(self):
        svc = self._make_service()
        uid = self._find_user_for_variant("ranker_v2_hyperpersonalized", ABVariant.TREATMENT)

        self._run_analyze(svc, uid)

        svc.ranking.rank_hyperpersonalized.assert_called_once()
        svc.ranking.rank.assert_not_called()

    def test_life_events_nudge_control_passes_empty_events(self):
        svc = self._make_service()
        uid = "test-control-user"

        # life_events_nudge tem traffic_pct=1.0 (100% TREATMENT) — nenhum usuário cai em
        # CONTROL via hash. Forçamos CONTROL diretamente para testar o code path.
        def _mock_variant(user_id, experiment_name):
            if experiment_name == "life_events_nudge":
                return ABVariant.CONTROL
            return get_variant(user_id, experiment_name)

        _LED_PATH = "app.optimizer.detectors.life_events_detector.LifeEventsDetector"
        with patch("app.core.ab_testing.get_variant", side_effect=_mock_variant):
            with patch(_LED_PATH) as mock_led:
                mock_led.return_value.detect_all.return_value = [
                    MagicMock(event="NOVO_BEBE", confidence=0.9,
                              detected_at=MagicMock(isoformat=lambda: "2026-04-01"),
                              trigger_action="REBALANCEAR", supporting_signals=[])
                ]
                with patch.object(svc, "_build_report") as mock_report:
                    mock_report.return_value = MagicMock()
                    self._run_analyze(svc, uid)
                    call_kwargs = mock_report.call_args.kwargs
                    assert call_kwargs["life_events"] == []

    def test_life_events_nudge_treatment_passes_detected_events(self):
        svc = self._make_service()
        uid = self._find_user_for_variant("life_events_nudge", ABVariant.TREATMENT)

        fake_event = MagicMock()
        fake_event.event = "NOVO_BEBE"
        fake_event.confidence = 0.9
        fake_event.detected_at = MagicMock()
        fake_event.detected_at.isoformat.return_value = "2026-04-01"
        fake_event.trigger_action = "REBALANCEAR"
        fake_event.supporting_signals = ["FRALDA", "PAMPERS"]

        _LED_PATH = "app.optimizer.detectors.life_events_detector.LifeEventsDetector"
        with patch(_LED_PATH) as mock_led:
            mock_led.return_value.detect_all.return_value = [fake_event]
            with patch.object(svc, "_build_report") as mock_report:
                mock_report.return_value = MagicMock()
                self._run_analyze(svc, uid)
                call_kwargs = mock_report.call_args.kwargs
                assert len(call_kwargs["life_events"]) == 1
                assert call_kwargs["life_events"][0]["event"] == "NOVO_BEBE"

    def test_cluster_tone_control_disables_tone_in_insight_generator(self):
        svc = self._make_service()
        uid = self._find_user_for_variant("cluster_tone_personalization", ABVariant.CONTROL)

        self._run_analyze(svc, uid)

        call_kwargs = svc.insight_generator.generate.call_args.kwargs
        assert call_kwargs.get("enable_cluster_tone") is False

    def test_cluster_tone_treatment_enables_tone_in_insight_generator(self):
        svc = self._make_service()
        uid = self._find_user_for_variant("cluster_tone_personalization", ABVariant.TREATMENT)

        self._run_analyze(svc, uid)

        call_kwargs = svc.insight_generator.generate.call_args.kwargs
        assert call_kwargs.get("enable_cluster_tone") is True
