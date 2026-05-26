"""
tests/architect/test_f3_completo.py - Teste Abrangente da F3 (Nexa Architect)

COBERTURA:
    1. TestCacheIntegracao     — L1/L2 cache, TTL, get_or_compute, invalidação, chaves
    2. TestSensitivityEndpoint — GET /simulations/{id}/sensitivity (zero cobertura anterior)
    3. TestPipelineCompletoF3  — service E2E com mocks; todos os asset types e estratégias
    4. TestTodosComponentesF3  — smoke test de cada módulo da F3
    5. TestRegressao           — bugs documentados em FUNCIONALIDADE_3.md (backend)

COMO RODAR:
    cd backend
    pytest tests/architect/test_f3_completo.py -v
    # Esperado: 30 passed

    # Suite completa:
    pytest tests/architect/ -v
    # Esperado: 411 passed
"""

import json
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient

from app.architect.models import (
    ActionStep,
    AmortizationMethod,
    AssetType,
    CostScenario,
    NPVComparison,
    RiskProfile,
    SimulationRequest,
    SimulationResponse,
    StrategyType,
)
from app.architect.simulators.sensitivity_analyzer import (
    SensitivityAnalyzer,
    SensitivityPoint,
    SensitivityReport,
    VariableSensitivity,
)
from app.architect.utils.cache import (
    SimulationCache,
    make_sensitivity_key,
    make_simulation_key,
    simulation_cache,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS INTERNOS (não são fixtures pytest — auxiliam na construção dos testes)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _mock_response(strategy: StrategyType = StrategyType.SAVE_INVEST) -> SimulationResponse:
    """SimulationResponse mínimo e válido para uso nos testes."""
    return SimulationResponse(
        recommended_strategy=strategy,
        costs=CostScenario(min_cost=45_000.0, expected_cost=50_000.0, max_cost=58_000.0),
        npv=NPVComparison(
            financing=-62_000.0,
            consortium=-57_000.0,
            save_invest=-50_000.0,
            discount_rate_used=0.0104,
        ),
        liquidity_impact=-0.18,
        months_to_achieve=36,
        action_plan=[ActionStep(step=1, action="Aplicar mensalmente em CDB", is_critical=True)],
        confidence_score=0.87,
        data_sources=["bacen", "anbima", "market_rates"],
        warnings=[],
    )


def _mock_sensitivity_report(strategy: str = "SAVE_INVEST") -> SensitivityReport:
    """SensitivityReport mínimo para uso nos testes de endpoint."""
    pt = SensitivityPoint(
        delta=0.0,
        param_value=0.1950,
        npv_financing=-62_000.0,
        npv_invest=-50_000.0,
        npv_consortium=-57_000.0,
        recommended=strategy,
    )
    var = VariableSensitivity(
        variable="interest_rate",
        description="Taxa de Juros do Financiamento (CET)",
        unit="p.p.",
        base_value=0.195,
        points=[pt],
        npv_range=5_000.0,
        elasticity=250_000.0,
        strategy_flips=0,
    )
    return SensitivityReport(
        variables=[var],
        most_sensitive_variable="interest_rate",
        strategy_stability=1.0,
        risk_profile="baixo",
        baseline_strategy=strategy,
    )


def _base_request_dict() -> dict:
    """SimulationRequest como dict serializável (simula o que o banco armazena)."""
    return {
        "user_id": "test_e2e_user",
        "target_amount": 50_000.0,
        "down_payment": 10_000.0,
        "max_monthly_budget": 2_000.0,
        "risk_profile": "moderado",
        "asset_type": "VEICULO",
        "include_consortium": True,
        "prefers_consortium": False,
        "financing_months": 48,
        "amortization_method": "PRICE",
        "target_date": None,
    }


def _stored_sim(sim_id: str = "sim-uuid-1234") -> dict:
    """Simulação como o banco retorna (com request e response como dicts Python)."""
    response_obj = _mock_response()
    return {
        "id": sim_id,
        "created_at": "2026-02-22T12:00:00+00:00",
        "target_amount": 50_000.0,
        "asset_type": "VEICULO",
        "recommended_strategy": "SAVE_INVEST",
        "confidence_score": 0.87,
        "liquidity_impact": -0.18,
        "months_to_achieve": 36,
        "expected_cost": 50_000.0,
        "request": _base_request_dict(),
        "response": response_obj.model_dump(mode="json"),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIXTURES COMPARTILHADAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="function")
def app():
    """Aplicação FastAPI isolada por teste.

    Usa scope="function" (não "module") para evitar contaminação de estado global
    entre testes — em especial o singleton simulation_cache e qualquer middleware
    que acumule estado durante a sessão.
    """
    from app.main import app as fastapi_app
    from app.core.security import get_current_user, require_owner

    async def _test_current_user():
        return "test_user"

    fastapi_app.dependency_overrides[get_current_user] = _test_current_user
    fastapi_app.dependency_overrides[require_owner] = lambda: "test_user"
    yield fastapi_app
    fastapi_app.dependency_overrides.pop(get_current_user, None)
    fastapi_app.dependency_overrides.pop(require_owner, None)


@pytest.fixture
def client(app):
    """TestClient para requests HTTP sem servidor real."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def cache(tmp_path: Path) -> SimulationCache:
    """Cache isolado por teste: L2 em diretório temporário."""
    return SimulationCache(cache_dir=tmp_path)


@pytest.fixture
def market_rates() -> dict:
    return {
        "selic_annual":                0.1325,
        "cdi_annual":                  0.1315,
        "best_cet_annual":             0.1950,
        "consortium_admin_rate":        0.17,
        "consortium_months":            72.0,
        "consortium_reserve_fund_rate": 0.02,
    }


@pytest.fixture
def mock_service_connectors():
    """Retorna mocks para os 3 conectores + ABAC do ArchitectService.

    O ABAC mock implementa get_consortium_stats(asset_type) com a
    interface real: retorna dict com 'admin_rate', 'typical_months' e
    'reserve_fund_rate'.
    """
    bacen = MagicMock()
    bacen.get_selic.return_value = 0.1325
    bacen.get_fallback_rates.return_value = {"selic_annual": 0.1325}

    anbima = MagicMock()
    anbima.get_cdi.return_value = 0.1315
    anbima.get_fallback_rates.return_value = {"cdi_annual": 0.1315}

    market = MagicMock()
    market.get_best_cet.return_value = 0.1950
    market.get_fallback_rates.return_value = {"cet_VEICULO_min": 0.1620}

    abac = MagicMock()
    # get_consortium_stats(asset_type) — interface real do AbacConnector
    abac.get_consortium_stats.return_value = {
        "admin_rate": 0.17,
        "typical_months": 72,
        "reserve_fund_rate": 0.02,
    }

    return bacen, anbima, market, abac


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. CACHE — INTEGRAÇÃO L1 + L2
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCacheIntegracao:
    """Testa o cache em dois níveis (L1 memória + L2 disco) da F3."""

    def test_cache_l1_set_e_get_basico(self, cache: SimulationCache):
        """set() e get() básicos em L1 (memória)."""
        cache.set("chave_teste", {"valor": 42}, l1_ttl=60)
        resultado = cache.get("chave_teste")
        assert resultado == {"valor": 42}

    def test_cache_l1_retorna_none_para_chave_inexistente(self, cache: SimulationCache):
        """get() de chave desconhecida retorna None — não levanta exceção."""
        assert cache.get("chave_que_nao_existe") is None

    def test_cache_l2_persiste_em_disco(self, cache: SimulationCache, tmp_path: Path):
        """Valor gravado com set() aparece como arquivo .json em disco (L2)."""
        cache.set("chave_disco", {"dados": "persistidos"}, l1_ttl=60, l2_ttl=3600)
        arquivos = list(tmp_path.glob("*.json"))
        assert len(arquivos) == 1
        conteudo = json.loads(arquivos[0].read_text())
        assert conteudo["value"] == {"dados": "persistidos"}

    def test_cache_l2_promove_para_l1_no_hit(self, tmp_path: Path):
        """Hit em L2 promove automaticamente o valor para L1."""
        # Cria cache com L1 vazio mas L2 preenchido
        cache1 = SimulationCache(cache_dir=tmp_path)
        cache1.set("chave_prom", {"v": 1}, l1_ttl=60, l2_ttl=3600)

        # Novo cache — L1 vazio, mas L2 com dados
        cache2 = SimulationCache(cache_dir=tmp_path)
        assert cache2._l1.get("chave_prom") is None  # L1 vazio

        valor = cache2.get("chave_prom")  # deve ler do L2 e promover
        assert valor == {"v": 1}
        assert "chave_prom" in cache2._l1  # promovido para L1

    def test_cache_get_or_compute_chama_fn_apenas_uma_vez(self, cache: SimulationCache):
        """get_or_compute executa compute_fn na primeira chamada e usa cache nas seguintes."""
        chamadas = []

        def compute():
            chamadas.append(1)
            return {"resultado": "caro"}

        r1 = cache.get_or_compute("gc_key", compute, l1_ttl=60)
        r2 = cache.get_or_compute("gc_key", compute, l1_ttl=60)

        assert r1 == r2 == {"resultado": "caro"}
        assert len(chamadas) == 1  # compute chamado apenas 1x

    def test_cache_delete_remove_l1_e_l2(self, cache: SimulationCache, tmp_path: Path):
        """delete() remove a entrada de ambos os níveis."""
        cache.set("del_key", {"x": 1})
        cache.delete("del_key")

        assert cache.get("del_key") is None
        assert not (tmp_path / "del_key.json").exists()

    def test_cache_invalidate_pattern_remove_por_prefixo(
        self, cache: SimulationCache, tmp_path: Path
    ):
        """invalidate_pattern('sim_') remove apenas entradas com esse prefixo.

        Verifica remoção em L1 (memória) e em L2 (disco), pois o método usa
        um set() para contar chaves únicas entre os dois níveis.
        As três entradas são escritas no cache isolado do fixture (tmp_path),
        sem risco de poluição por testes anteriores.
        """
        cache.set("sim_aaa", {"a": 1})
        cache.set("sim_bbb", {"b": 2})
        cache.set("sens_ccc", {"c": 3})

        # Confirma que L2 tem 3 arquivos antes da invalidação
        assert len(list(tmp_path.glob("*.json"))) == 3

        removidas = cache.invalidate_pattern("sim_")

        # Deve remover exatamente 2 chaves únicas (sim_aaa e sim_bbb)
        assert removidas == 2

        # L1: entradas com prefixo removidas
        assert cache.get("sim_aaa") is None
        assert cache.get("sim_bbb") is None

        # L2: arquivos físicos removidos
        assert not (tmp_path / "sim_aaa.json").exists()
        assert not (tmp_path / "sim_bbb.json").exists()

        # Entrada sem o prefixo intacta em L1 e L2
        assert cache.get("sens_ccc") == {"c": 3}
        assert (tmp_path / "sens_ccc.json").exists()

    def test_make_simulation_key_e_deterministica(self, market_rates: dict):
        """Mesmos parâmetros → mesmo hash; user_id diferente → mesmo hash."""
        req_a = {"user_id": "user_A", "target_amount": 50_000.0, "asset_type": "VEICULO",
                 "down_payment": 10_000.0, "max_monthly_budget": 2_000.0,
                 "financing_months": 48, "amortization_method": "PRICE",
                 "include_consortium": True, "risk_profile": "moderado"}
        req_b = {**req_a, "user_id": "user_B"}  # mesmo conteúdo, user diferente

        k1 = make_simulation_key(req_a, market_rates)
        k2 = make_simulation_key(req_b, market_rates)

        assert k1 == k2
        assert k1.startswith("sim_")
        assert len(k1) == len("sim_") + 48

    def test_make_sensitivity_key_inclui_simulation_id(self, market_rates: dict):
        """make_sensitivity_key embute o simulation_id no hash."""
        sim_id = "550e8400-e29b-41d4-a716-446655440000"
        key = make_sensitivity_key(sim_id, market_rates)

        assert key.startswith(f"sens_{sim_id}_")
        # Taxas diferentes → chave diferente
        taxas_novas = {**market_rates, "selic_annual": 0.1500}
        key2 = make_sensitivity_key(sim_id, taxas_novas)
        assert key != key2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. ENDPOINT GET /simulations/{id}/sensitivity
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_PATCH_GET_SIM   = "app.architect.router.get_simulation"
_PATCH_RATES     = "app.architect.router._service.fetch_market_rates"
_PATCH_ANALYZER  = "app.architect.router._sensitivity_analyzer.analyze"


class TestSensitivityEndpoint:
    """Testa GET /architect/simulations/{simulation_id}/sensitivity.

    Este endpoint não possuía nenhum teste antes deste arquivo.
    """

    _SIM_ID = "550e8400-e29b-41d4-a716-446655440000"
    _URL    = f"/api/v1/architect/simulations/{_SIM_ID}/sensitivity"

    def test_retorna_404_para_simulacao_inexistente(self, client):
        """Quando get_simulation retorna None → HTTP 404."""
        with patch(_PATCH_GET_SIM, return_value=None):
            resp = client.get(self._URL)
        assert resp.status_code == 404

    def test_retorna_200_com_simulacao_existente(self, client, market_rates):
        """Simulação existente + analyzer bem-sucedido → HTTP 200."""
        report = _mock_sensitivity_report()
        with (
            patch(_PATCH_GET_SIM, return_value=_stored_sim(self._SIM_ID)),
            patch(_PATCH_RATES, return_value=market_rates),
            patch(_PATCH_ANALYZER, return_value=report),
        ):
            resp = client.get(self._URL)
        assert resp.status_code == 200

    def test_estrutura_do_report_retornado(self, client, market_rates):
        """Response deve ter os campos chave do SensitivityReport.to_dict()."""
        report = _mock_sensitivity_report()
        with (
            patch(_PATCH_GET_SIM, return_value=_stored_sim(self._SIM_ID)),
            patch(_PATCH_RATES, return_value=market_rates),
            patch(_PATCH_ANALYZER, return_value=report),
        ):
            resp = client.get(self._URL)
        data = resp.json()
        assert "most_sensitive_variable" in data
        assert "strategy_stability" in data
        assert "risk_profile" in data
        assert "baseline_strategy" in data
        assert "variables" in data
        assert "generated_at" in data

    def test_variaveis_tem_pontos_validos(self, client, market_rates):
        """Cada variável deve ter pelo menos 1 ponto com os campos obrigatórios."""
        report = _mock_sensitivity_report()
        with (
            patch(_PATCH_GET_SIM, return_value=_stored_sim(self._SIM_ID)),
            patch(_PATCH_RATES, return_value=market_rates),
            patch(_PATCH_ANALYZER, return_value=report),
        ):
            resp = client.get(self._URL)
        data = resp.json()
        assert len(data["variables"]) >= 1
        for var in data["variables"]:
            assert len(var["points"]) >= 1
            pt = var["points"][0]
            assert "delta" in pt
            assert "npv_financing" in pt
            assert "npv_invest" in pt
            assert "recommended" in pt

    def test_risk_profile_e_valor_valido(self, client, market_rates):
        """risk_profile deve ser 'baixo', 'moderado' ou 'alto'."""
        report = _mock_sensitivity_report()
        with (
            patch(_PATCH_GET_SIM, return_value=_stored_sim(self._SIM_ID)),
            patch(_PATCH_RATES, return_value=market_rates),
            patch(_PATCH_ANALYZER, return_value=report),
        ):
            resp = client.get(self._URL)
        assert resp.json()["risk_profile"] in {"baixo", "moderado", "alto"}

    def test_retorna_500_para_erro_interno_no_analyzer(self, client, market_rates):
        """Exceção inesperada no analyzer → HTTP 500."""
        with (
            patch(_PATCH_GET_SIM, return_value=_stored_sim(self._SIM_ID)),
            patch(_PATCH_RATES, return_value=market_rates),
            patch(_PATCH_ANALYZER, side_effect=RuntimeError("erro inesperado")),
        ):
            resp = client.get(self._URL)
        assert resp.status_code == 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. PIPELINE COMPLETO DA F3 (Service Layer)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPipelineCompletoF3:
    """Testa o ArchitectService de ponta a ponta com conectores mockados.

    Não faz chamadas HTTP reais — os conectores são injetados como MagicMocks.
    Valida o pipeline completo: validação → taxas → engine → liquidez → resposta.
    """

    def _make_service(self, mock_service_connectors):
        from app.architect.services.architect_service import ArchitectService
        bacen, anbima, market, abac = mock_service_connectors
        return ArchitectService(bacen=bacen, anbima=anbima, market_rates=market, abac=abac)

    def test_simulate_retorna_simulation_response(self, mock_service_connectors):
        """Service.simulate() com request válido retorna SimulationResponse completo.

        Nota: usa include_consortium=False para evitar não-determinismo do Monte Carlo.
        O consórcio é testado extensivamente em test_consortium.py e test_monte_carlo.py.
        """
        service = self._make_service(mock_service_connectors)
        req = SimulationRequest(
            user_id="test_pipeline",
            target_amount=50_000.0,
            down_payment=10_000.0,
            max_monthly_budget=2_000.0,
            financing_months=48,
            include_consortium=False,
        )
        resp = service.simulate(req, safe_to_spend=None)
        assert isinstance(resp, SimulationResponse)
        assert resp.recommended_strategy in list(StrategyType)
        assert len(resp.action_plan) >= 1
        assert 0.0 <= resp.confidence_score <= 1.0

    def test_todos_os_asset_types_sao_aceitos(self, mock_service_connectors):
        """Cada AssetType (IMOVEL, VEICULO, REFORMA, VIAGEM, OUTRO) deve funcionar.

        Usa target_amount e financing_months compatíveis com os limites de cada tipo
        conforme documentado em FUNCIONALIDADE_3.md (InputValidator.validate()).
        IMOVEL: mín R$50k, VEICULO: mín R$5k, demais: mín R$1k.
        """
        service = self._make_service(mock_service_connectors)
        # Parâmetros mínimos válidos por asset_type (respeitam regras do InputValidator)
        asset_configs = {
            AssetType.IMOVEL:  {"target_amount": 60_000.0, "financing_months": 120},
            AssetType.VEICULO: {"target_amount": 30_000.0, "financing_months": 48},
            AssetType.REFORMA: {"target_amount": 15_000.0, "financing_months": 60},
            AssetType.VIAGEM:  {"target_amount": 10_000.0, "financing_months": 24},
            AssetType.OUTRO:   {"target_amount": 10_000.0, "financing_months": 36},
        }
        for asset, params in asset_configs.items():
            req = SimulationRequest(
                user_id="test_asset",
                asset_type=asset,
                include_consortium=False,  # evita não-determinismo do Monte Carlo
                **params,
            )
            resp = service.simulate(req)
            assert isinstance(resp, SimulationResponse), f"Falhou para asset_type={asset}"

    def test_com_safe_to_spend_confidence_aumenta(self, mock_service_connectors):
        """safe_to_spend real (F1) disponível → confidence_score > sem safe_to_spend.

        Invariante garantida pelo ArchitectService._compute_confidence():
            - safe_to_spend presente:  base(0.85) + F1_bonus(+0.10) - fallback_penalty(0)
            - safe_to_spend=None:      base(0.85) - liquidity_warning(-0.02)
        O primeiro cenário resulta em score sempre maior que o segundo,
        pois +0.10 > +0.02 (máx penalidade por aviso). Não há aleatoriedade.
        """
        service = self._make_service(mock_service_connectors)
        req = SimulationRequest(
            user_id="test_conf",
            target_amount=50_000.0,
            down_payment=5_000.0,
            max_monthly_budget=2_000.0,
            financing_months=36,
            include_consortium=False,
        )
        resp_sem = service.simulate(req, safe_to_spend=None)
        resp_com = service.simulate(req, safe_to_spend=8_000.0)

        # A diferença esperada é +0.10 (bônus F1) vs -0.02 (penalidade de aviso)
        assert resp_com.confidence_score > resp_sem.confidence_score

    def test_sem_consortium_estrategia_nao_e_consortium(self, mock_service_connectors):
        """include_consortium=False → estratégia nunca pode ser CONSORTIUM."""
        service = self._make_service(mock_service_connectors)
        req = SimulationRequest(
            user_id="test_no_cons",
            target_amount=30_000.0,
            down_payment=5_000.0,
            max_monthly_budget=1_500.0,
            include_consortium=False,
            financing_months=36,
        )
        resp = service.simulate(req)
        assert resp.recommended_strategy != StrategyType.CONSORTIUM

    def test_request_invalido_levanta_value_error(self, mock_service_connectors):
        """Principal < R$1.000 → InputValidator levanta ValueError (422 na API)."""
        service = self._make_service(mock_service_connectors)
        req = SimulationRequest(
            user_id="test_invalido",
            target_amount=1_050.0,
            down_payment=100.0,  # principal = 950 < 1000
            max_monthly_budget=500.0,
            financing_months=12,
            include_consortium=False,
        )
        with pytest.raises(ValueError):
            service.simulate(req)

    def test_response_tem_data_sources(self, mock_service_connectors):
        """Response deve listar ao menos uma fonte de dados."""
        service = self._make_service(mock_service_connectors)
        req = SimulationRequest(
            user_id="test_sources",
            target_amount=40_000.0,
            financing_months=36,
            include_consortium=False,
        )
        resp = service.simulate(req)
        assert len(resp.data_sources) >= 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. SMOKE TEST — TODOS OS COMPONENTES DA F3
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTodosComponentesF3:
    """Smoke tests: importa e executa minimamente cada módulo da F3.

    Garante que nenhum import quebra e que a interface básica funciona.
    """

    def test_calculadoras_npv_financing_investment(self):
        """NPV, PRICE e investment calculam sem crash para inputs básicos."""
        from app.architect.calculators import financing as fin
        from app.architect.calculators import investment as inv
        from app.architect.calculators import npv

        npv_val = npv.calculate_npv([-1000.0, 500.0, 500.0, 500.0], discount_rate=0.01)
        assert npv_val != 0.0

        price = fin.calculate_price(principal=40_000.0, annual_rate=0.195, months=48)
        assert price.monthly_payment > 0

        pmt = inv.calculate_pmt_needed(target=50_000.0, annual_rate=0.1315, months=36)
        assert pmt > 0

    def test_calculadora_consortium_monte_carlo(self):
        """Consortium calculator retorna ConsortiumResult com campos obrigatórios.

        Assinatura: calculate_consortium_metrics(letter_value, months, admin_rate, ...)
        Resultado: ConsortiumResult com contemplation_probability (dict),
                   monthly_payment, total_cost, contemplation_month_expected.
        """
        from app.architect.calculators.consortium import calculate_consortium_metrics
        metrics = calculate_consortium_metrics(
            letter_value=50_000.0,
            months=72,
            admin_rate=0.17,
            reserve_fund_rate=0.02,
            bid_amount=0.0,  # sem lance para evitar edge-case probabilístico
        )
        # ConsortiumResult.contemplation_probability é um dict {"6m": 0.X, "12m": 0.X, ...}
        assert isinstance(metrics.contemplation_probability, dict)
        assert metrics.monthly_payment > 0
        assert metrics.total_cost > 0
        assert metrics.contemplation_month_expected >= 1

        # Probabilidades acumuladas devem estar entre 0 e 1
        for key, prob in metrics.contemplation_probability.items():
            assert 0.0 <= prob <= 1.0, f"Probabilidade {key}={prob} fora do range"

    def test_conectores_retornam_fallback_sem_http(self):
        """Conectores retornam taxas hardcoded (fallback) sem chamadas de rede."""
        from app.architect.connectors.bacen import BacenConnector
        from app.architect.connectors.anbima import AnbimaConnector
        from app.architect.connectors.market_rates import MarketRatesConnector

        assert BacenConnector().get_fallback_rates()["selic_annual"] > 0
        assert AnbimaConnector().get_fallback_rates()["cdi_annual"] > 0
        fb = MarketRatesConnector().get_fallback_rates()
        assert fb["cet_VEICULO_min"] > 0

    def test_validators_input_e_liquidez(self):
        """InputValidator e LiquidityValidator funcionam com inputs básicos.

        InputValidator.validate() retorna ValidationResult com .errors e .warnings.
        LiquidityValidator.calculate() retorna LiquidityResult com .impact e .is_sustainable.
        """
        from app.architect.validators.input_validator import InputValidator
        from app.architect.validators.liquidity_validator import LiquidityValidator

        req = SimulationRequest(
            user_id="smoke_test",
            target_amount=50_000.0,
            down_payment=10_000.0,
            max_monthly_budget=2_000.0,
            financing_months=48,
        )
        result = InputValidator.validate(req)
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)
        assert result.is_valid  # request válido não deve ter erros

        impacto = LiquidityValidator.calculate(monthly_payment=1_200.0, safe_to_spend=4_000.0)
        assert impacto.impact < 0         # comprometimento negativo (consome orçamento)
        assert impacto.is_sustainable     # 30% de comprometimento é sustentável

    def test_strategy_engine_retorna_resposta_completa(self):
        """StrategyEngine.simulate() retorna SimulationResponse com campos obrigatórios."""
        from app.architect.simulators.strategy_engine import StrategyEngine
        engine = StrategyEngine()
        req = SimulationRequest(
            user_id="smoke_engine",
            target_amount=50_000.0,
            down_payment=10_000.0,
            max_monthly_budget=2_000.0,
            financing_months=48,
        )
        rates = {
            "selic_annual": 0.1325,
            "cdi_annual": 0.1315,
            "best_cet_annual": 0.195,
            "consortium_admin_rate": 0.17,
            "consortium_months": 72.0,
            "consortium_reserve_fund_rate": 0.02,
        }
        resp = engine.simulate(req, market_rates=rates)
        assert isinstance(resp, SimulationResponse)
        assert resp.npv is not None

    def test_sensitivity_analyzer_analisa_4_variaveis(self, market_rates):
        """SensitivityAnalyzer.analyze() retorna report com exatamente 4 variáveis."""
        analyzer = SensitivityAnalyzer()
        req = SimulationRequest(
            user_id="smoke_sens",
            target_amount=50_000.0,
            down_payment=10_000.0,
            max_monthly_budget=2_000.0,
            financing_months=48,
        )
        baseline = _mock_response()
        report = analyzer.analyze(req, market_rates, baseline)

        assert len(report.variables) == 4
        variaveis = {v.variable for v in report.variables}
        assert variaveis == {"interest_rate", "months", "down_payment", "cdi_rate"}
        assert report.risk_profile in {"baixo", "moderado", "alto"}

    def test_simulation_cache_singleton_importavel(self):
        """simulation_cache (singleton) é importável e funcional."""
        assert simulation_cache is not None
        assert hasattr(simulation_cache, "get")
        assert hasattr(simulation_cache, "set")
        assert hasattr(simulation_cache, "stats")
        stats = simulation_cache.stats
        assert "l1_total" in stats and "l2_total" in stats


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. REGRESSÃO — BUGS CORRIGIDOS DOCUMENTADOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestRegressao:
    """Garante que bugs documentados em FUNCIONALIDADE_3.md não regridam.

    Cada teste corresponde a um fix listado em backend/FUNCIONALIDADE_3.md.
    O comentário do teste indica a data do fix e o sintoma original.
    """

    def test_cet_imovel_acima_da_selic(self):
        """Fix 19/02/2026 — market_rates.py (get_fallback_rates).

        Sintoma: CETs de IMOVEL retornavam 10,50% (abaixo da SELIC 13,25%),
        criando spread negativo impossível no mercado real.
        Fix: valores corrigidos para SELIC 13,25% + spread 150–300bps.
        Guard: cet_IMOVEL_min deve ser estritamente maior que a SELIC de referência.
        """
        from app.architect.connectors.market_rates import MarketRatesConnector
        fallback = MarketRatesConnector().get_fallback_rates()
        selic_referencia = 0.1325  # SELIC fev/2026 usada como baseline do fix
        assert fallback["cet_IMOVEL_min"] > selic_referencia, (
            f"Regressão: CET mínimo IMOVEL ({fallback['cet_IMOVEL_min']:.2%}) "
            f"voltou a ser menor ou igual à SELIC ({selic_referencia:.2%})"
        )
        # Garante também que o spread mínimo é de ao menos 100bps sobre a SELIC
        assert fallback["cet_IMOVEL_min"] >= selic_referencia + 0.01

    def test_market_rates_path_resolve_para_backend(self):
        """Fix 19/02/2026 — market_rates.py (linha _DATA_FILE).

        Sintoma: `parents[4]` resolvia para a raiz do monorepo em vez de backend/,
        fazendo o arquivo market_rates.json ser buscado no lugar errado.
        Fix: `parents[3]` aponta corretamente para backend/.
        Guard: _DATA_FILE deve conter 'backend' no path absoluto.
        """
        from app.architect.connectors import market_rates as mr_module
        data_file = mr_module._DATA_FILE
        assert "backend" in str(data_file), (
            f"Regressão: path {data_file} não contém 'backend' — "
            f"parents[] pode ter voltado para o índice errado"
        )

    def test_guards_taxa_menores_que_menos_1(self):
        """Fix histórico (Fase 1) — npv.py (calculate_npv / calculate_irr).

        Sintoma: `discount_rate = -1.0` produzia `(1 + r)^t = 0^t` causando
        ZeroDivisionError sem mensagem útil.
        Fix: guard `if discount_rate <= -1: raise ValueError(...)` no topo de
        todas as funções de cálculo. Uso de `<= -1` (não `< -1`) é intencional:
        rate = -1.0 é matematicamente inválido (divisão por zero no período 1).
        Guard: deve levantar ValueError descritivo, não ZeroDivisionError.
        """
        from app.architect.calculators.npv import calculate_npv
        with pytest.raises(ValueError, match="nao pode ser menor ou igual a"):
            calculate_npv([-1000, 500, 500], discount_rate=-1.0)

        # Pior caso: rate < -1 também rejeitado
        with pytest.raises(ValueError):
            calculate_npv([-1000, 500, 500], discount_rate=-1.1)

    def test_db_cast_varchar_sem_pytz(self):
        """Fix 19/02/2026 — architect_queries.py (queries de timestamp).

        Sintoma: DuckDB retornava colunas TIMESTAMPTZ como objetos Python datetime
        com timezone info; sem a lib `pytz` instalada, serialização explodava.
        Fix: `CAST(created_at AS VARCHAR)` nas queries — retorna string ISO 8601
        diretamente, eliminando a dependência de pytz em runtime.

        Escopo deste teste: verifica que o módulo importa e que as funções públicas
        são callable sem exigir pytz. Não testa o comportamento da query em si
        (isso está coberto em test_db.py com DuckDB :memory:).
        """
        try:
            from app.architect.queries import (
                save_simulation,
                get_simulation,
                get_user_simulations,
                get_user_metrics,
            )
        except ImportError as exc:
            if "pytz" in str(exc):
                pytest.fail(
                    f"Regressão: módulo architect_queries voltou a depender de pytz: {exc}"
                )
            raise  # ImportError de outra lib — não é regressão deste bug

        # Todas as funções públicas devem ser callable
        assert callable(save_simulation)
        assert callable(get_simulation)
        assert callable(get_user_simulations)
        assert callable(get_user_metrics)
