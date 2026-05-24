"""
tests/architect/test_llm_reasoner.py — LLM co-raciocínio estruturado

Testa LLMReasoner sem chamar APIs externas:
- Degradação graciosa sem API key
- Parsing do JSON de consistência (válido / malformado / override_params)
- Sanitização de override_params (chaves não-permitidas filtradas)
- Rerun do motor quando override_params presente
- Parsing da narrativa (3 parágrafos / fallback split)
- Integração com ArchitectService (llm_reasoning no response)
"""

import json
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from app.architect.models import (
    ActionStep,
    AmortizationMethod,
    AssetType,
    CostScenario,
    LLMConsistencyResult,
    LLMNarrative,
    LLMReasoningResult,
    NPVComparison,
    RiskProfile,
    SimulationRequest,
    SimulationResponse,
    StrategyType,
)
from app.architect.services.llm_reasoner import LLMReasoner


# ─────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_request():
    return SimulationRequest(
        user_id="test-llm",
        target_amount=500_000.0,
        down_payment=100_000.0,
        financing_months=240,
        risk_profile=RiskProfile.MODERADO,
        asset_type=AssetType.IMOVEL,
        amortization_method=AmortizationMethod.PRICE,
    )


@pytest.fixture
def sample_response():
    return SimulationResponse(
        recommended_strategy=StrategyType.SAVE_INVEST,
        costs=CostScenario(min_cost=0, expected_cost=500_000, max_cost=550_000),
        npv=NPVComparison(
            financing=-350_000.0,
            save_invest=-180_000.0,
            consortium=-290_000.0,
            discount_rate_used=0.009,
        ),
        liquidity_impact=-0.25,
        months_to_achieve=240,
        action_plan=[ActionStep(step=1, action="Abrir conta investimento", deadline_days=30)],
        confidence_score=0.75,
        data_sources=["bacen"],
        warnings=[],
    )


@pytest.fixture
def market_rates():
    return {
        "selic_annual": 0.1475,
        "cdi_annual": 0.1465,
        "best_cet_annual": 0.13,
        "ipca_annual": 0.045,
    }


def _make_reasoner(api_key="test-key", provider="openai", model="gpt-4o-mini"):
    """Cria LLMReasoner sem depender de settings."""
    r = LLMReasoner.__new__(LLMReasoner)
    r._provider = provider
    r._model = model
    r._api_key = api_key
    return r


# ─────────────────────────────────────────────────────────────────────
# DEGRADAÇÃO GRACIOSA
# ─────────────────────────────────────────────────────────────────────

class TestGracefulDegradation:
    def test_no_api_key_returns_none(self, sample_request, sample_response, market_rates):
        reasoner = _make_reasoner(api_key=None)
        result, resp = reasoner.reason(
            sample_request, sample_response, market_rates,
            rerun_fn=lambda r: sample_response,
        )
        assert result is None
        assert resp is sample_response

    def test_llm_exception_returns_none(self, sample_request, sample_response, market_rates):
        reasoner = _make_reasoner()
        with patch.object(reasoner, "_check_consistency", side_effect=RuntimeError("timeout")):
            result, resp = reasoner.reason(
                sample_request, sample_response, market_rates,
                rerun_fn=lambda r: sample_response,
            )
        assert result is None
        assert resp is sample_response


# ─────────────────────────────────────────────────────────────────────
# PARSING DA CONSISTÊNCIA
# ─────────────────────────────────────────────────────────────────────

class TestConsistencyParsing:
    def test_consistent_no_flags(self):
        reasoner = _make_reasoner()
        raw = json.dumps({"consistent": True, "flags": [], "override_suggestion": None, "override_params": None})
        result = reasoner._parse_consistency(raw)
        assert result.consistent is True
        assert result.flags == []
        assert result.override_params is None

    def test_flags_with_override(self):
        reasoner = _make_reasoner()
        raw = json.dumps({
            "consistent": False,
            "flags": ["Perfil AGRESSIVO com veículo depreciável"],
            "override_suggestion": "Considere MODERADO",
            "override_params": {"risk_profile": "moderado"},
        })
        result = reasoner._parse_consistency(raw)
        assert result.consistent is False
        assert len(result.flags) == 1
        assert result.override_params == {"risk_profile": "moderado"}
        assert result.override_suggestion is not None

    def test_malformed_json_returns_safe_fallback(self):
        reasoner = _make_reasoner()
        result = reasoner._parse_consistency("not json at all {{{")
        assert result.consistent is True
        assert any("inválido" in f.lower() for f in result.flags)

    def test_override_params_sanitization_filters_bad_keys(self):
        reasoner = _make_reasoner()
        raw = json.dumps({
            "consistent": False,
            "flags": ["x"],
            "override_suggestion": "y",
            "override_params": {
                "risk_profile": "conservador",
                "target_amount": "999999",   # chave não permitida
                "__inject__": "malicious",
            },
        })
        result = reasoner._parse_consistency(raw)
        assert result.override_params == {"risk_profile": "conservador"}

    def test_override_params_all_bad_keys_becomes_none(self):
        reasoner = _make_reasoner()
        raw = json.dumps({
            "consistent": False,
            "flags": [],
            "override_params": {"target_amount": "100000"},
        })
        result = reasoner._parse_consistency(raw)
        assert result.override_params is None


# ─────────────────────────────────────────────────────────────────────
# APPLY OVERRIDES
# ─────────────────────────────────────────────────────────────────────

class TestApplyOverrides:
    def test_valid_risk_profile_override(self, sample_request):
        result = LLMReasoner._apply_overrides(sample_request, {"risk_profile": "conservador"})
        assert result is not None
        assert result.risk_profile == RiskProfile.CONSERVADOR
        assert result.target_amount == sample_request.target_amount  # resto inalterado

    def test_valid_financing_months_override(self, sample_request):
        result = LLMReasoner._apply_overrides(sample_request, {"financing_months": "120"})
        assert result is not None
        assert result.financing_months == 120

    def test_invalid_risk_profile_returns_none(self, sample_request):
        result = LLMReasoner._apply_overrides(sample_request, {"risk_profile": "ultra-risk"})
        assert result is None

    def test_financing_months_out_of_range_returns_none(self, sample_request):
        result = LLMReasoner._apply_overrides(sample_request, {"financing_months": "600"})
        assert result is None

    def test_empty_params_returns_none(self, sample_request):
        result = LLMReasoner._apply_overrides(sample_request, {})
        assert result is None


# ─────────────────────────────────────────────────────────────────────
# PARSING DA NARRATIVA
# ─────────────────────────────────────────────────────────────────────

class TestNarrativeParsing:
    def test_three_paragraphs_parsed_correctly(self):
        reasoner = _make_reasoner()
        raw = "Parágrafo 1 sobre por que vence.\n\nParágrafo 2 sobre riscos.\n\nParágrafo 3 próximos passos."
        result = reasoner._parse_narrative(raw)
        assert result.why_this_strategy == "Parágrafo 1 sobre por que vence."
        assert result.risks == "Parágrafo 2 sobre riscos."
        assert result.next_steps == "Parágrafo 3 próximos passos."

    def test_fallback_when_less_than_three_paragraphs(self):
        reasoner = _make_reasoner()
        raw = "Texto único sem parágrafos duplos."
        result = reasoner._parse_narrative(raw)
        assert isinstance(result, LLMNarrative)
        # Fallback divide em 3: conteúdo não é vazio
        assert result.why_this_strategy or result.risks or result.next_steps


# ─────────────────────────────────────────────────────────────────────
# RERUN DO MOTOR
# ─────────────────────────────────────────────────────────────────────

class TestEngineRerun:
    def test_rerun_called_when_override_params_present(
        self, sample_request, sample_response, market_rates
    ):
        reasoner = _make_reasoner()
        rerun_response = sample_response.model_copy(
            update={"recommended_strategy": StrategyType.CONSORTIUM}
        )
        rerun_fn = MagicMock(return_value=rerun_response)

        consistency_json = json.dumps({
            "consistent": False,
            "flags": ["perfil inconsistente"],
            "override_suggestion": "Usar CONSERVADOR",
            "override_params": {"risk_profile": "conservador"},
        })
        narrative_text = "§1 texto.\n\n§2 riscos.\n\n§3 passos."

        with patch.object(reasoner, "_call_llm", side_effect=[consistency_json, narrative_text]):
            result, final_response = reasoner.reason(
                sample_request, sample_response, market_rates, rerun_fn=rerun_fn
            )

        rerun_fn.assert_called_once()
        adjusted_req = rerun_fn.call_args[0][0]
        assert adjusted_req.risk_profile == RiskProfile.CONSERVADOR

        assert result is not None
        assert result.engine_rerun is True
        assert final_response is rerun_response

    def test_no_rerun_when_consistent(
        self, sample_request, sample_response, market_rates
    ):
        reasoner = _make_reasoner()
        rerun_fn = MagicMock(return_value=sample_response)

        consistency_json = json.dumps({
            "consistent": True, "flags": [], "override_params": None
        })
        narrative_text = "§1.\n\n§2.\n\n§3."

        with patch.object(reasoner, "_call_llm", side_effect=[consistency_json, narrative_text]):
            result, final_response = reasoner.reason(
                sample_request, sample_response, market_rates, rerun_fn=rerun_fn
            )

        rerun_fn.assert_not_called()
        assert result is not None
        assert result.engine_rerun is False


# ─────────────────────────────────────────────────────────────────────
# RESULTADO COMPLETO
# ─────────────────────────────────────────────────────────────────────

class TestFullReasoningResult:
    def test_result_shape_when_consistent(
        self, sample_request, sample_response, market_rates
    ):
        reasoner = _make_reasoner(provider="anthropic", model="claude-haiku-4-5-20251001")
        consistency_json = json.dumps({
            "consistent": True,
            "flags": [],
            "override_suggestion": None,
            "override_params": None,
        })
        narrative_text = "Por que vence: análise.\n\nRiscos: dois pontos.\n\nPassos: três ações."

        with patch.object(reasoner, "_call_llm", side_effect=[consistency_json, narrative_text]):
            result, resp = reasoner.reason(
                sample_request, sample_response, market_rates,
                rerun_fn=lambda r: sample_response,
            )

        assert isinstance(result, LLMReasoningResult)
        assert result.consistency.consistent is True
        assert result.engine_rerun is False
        assert result.provider_used == "anthropic"
        assert result.model_used == "claude-haiku-4-5-20251001"
        assert "vence" in result.narrative.why_this_strategy
        assert "Riscos" in result.narrative.risks

    def test_flags_propagated_to_warnings_via_service(
        self, sample_request, market_rates
    ):
        """Verifica que flags do LLM viram warnings com prefixo [LLM]."""
        from app.architect.services.architect_service import ArchitectService
        from unittest.mock import MagicMock

        bacen = MagicMock(); bacen.get_selic.return_value = 0.1475
        anbima = MagicMock(); anbima.get_cdi.return_value = 0.1465
        mkt = MagicMock(); mkt.get_best_cet.return_value = 0.13

        llm_mock = MagicMock()
        llm_result = LLMReasoningResult(
            consistency=LLMConsistencyResult(
                consistent=False,
                flags=["Risco não modelado: depreciação acelerada"],
            ),
            narrative=LLMNarrative(
                why_this_strategy="Vence.",
                risks="Riscos.",
                next_steps="Passos.",
            ),
        )
        mock_base_response = SimulationResponse(
            recommended_strategy=StrategyType.SAVE_INVEST,
            costs=CostScenario(min_cost=0, expected_cost=500_000, max_cost=550_000),
            npv=NPVComparison(
                financing=-350_000.0,
                save_invest=-180_000.0,
                discount_rate_used=0.009,
            ),
            liquidity_impact=-0.25,
            months_to_achieve=240,
            action_plan=[ActionStep(step=1, action="Abrir conta", deadline_days=30)],
            confidence_score=0.75,
            data_sources=["bacen"],
            warnings=[],
        )
        llm_mock.reason.return_value = (llm_result, mock_base_response)

        service = ArchitectService(
            bacen=bacen, anbima=anbima, market_rates=mkt,
            llm_reasoner=llm_mock,
        )
        resp = service.simulate(sample_request)

        llm_flagged_warnings = [w for w in resp.warnings if w.startswith("[LLM]")]
        assert len(llm_flagged_warnings) == 1
        assert "depreciação" in llm_flagged_warnings[0]
