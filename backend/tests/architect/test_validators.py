"""
tests/architect/test_validators.py - Testes dos validadores de input e liquidez

O QUE É TESTADO:
    InputValidator:
        - Regra 1: principal >= R$1.000
        - Regra 2: down_payment <= 90% do target
        - Regra 3: max_monthly_budget >= R$100 (se informado)
        - Regra 4: financing_months compatível com asset_type
        - Regra 5: target_amount mínimo por tipo de bem
        - Regra 6: flags contraditórios (warn apenas)
        - Regra 7: target_date vs financing_months (warn apenas)
        - Requests válidos não geram erros

    LiquidityValidator:
        - Níveis SAFE / WARNING / HIGH / CRITICAL
        - Hierarquia de referência (safe_to_spend > max_monthly_budget)
        - Sem referência → impact = 0.0
        - is_sustainable = False para CRITICAL

COMO RODAR:
    cd backend
    pytest tests/architect/test_validators.py -v
"""

import pytest
from datetime import date, timedelta

from app.architect.models import AssetType, SimulationRequest
from app.architect.validators.input_validator import InputValidator
from app.architect.validators.liquidity_validator import LiquidityValidator, RiskLevel


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: InputValidator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestInputValidator:
    """Testa as 7 regras de negócio do InputValidator."""

    def _req(self, **kwargs) -> SimulationRequest:
        """Helper: cria request base com overrides."""
        defaults = dict(
            user_id="u1",
            target_amount=30_000.0,
            down_payment=5_000.0,
            max_monthly_budget=1_500.0,
            asset_type=AssetType.VEICULO,
            financing_months=48,
            include_consortium=True,
            prefers_consortium=False,
        )
        defaults.update(kwargs)
        return SimulationRequest(**defaults)

    # ── Regra 1: principal mínimo ────────────────────────────────

    def test_principal_abaixo_do_minimo_gera_erro(self):
        """principal < R$1.000 deve gerar erro bloqueante."""
        req = self._req(target_amount=5_000.0, down_payment=4_200.0)  # principal = 800
        result = InputValidator.validate(req)
        assert not result.is_valid
        assert any(
            "principal" in e.lower()
            or "1.000" in e or "1,000" in e or "1000" in e
            or "financiar" in e.lower()
            or "baixo" in e.lower()
            for e in result.errors
        )

    def test_principal_exatamente_minimo_valido(self):
        """principal == R$1.000 deve ser aceito."""
        req = self._req(target_amount=5_000.0, down_payment=4_000.0)  # principal = 1000
        result = InputValidator.validate(req)
        # Não deve ter erro de principal mínimo
        erros_principal = [e for e in result.errors if "1000" in e or "1.000" in e]
        assert len(erros_principal) == 0

    # ── Regra 2: down_payment proporcional ───────────────────────

    def test_entrada_acima_de_90_percent_gera_erro(self):
        """down_payment > 90% do target deve gerar erro."""
        req = self._req(target_amount=10_000.0, down_payment=9_500.0)  # 95%
        result = InputValidator.validate(req)
        assert not result.is_valid
        assert any("90%" in e or "entrada" in e.lower() or "down_payment" in e.lower()
                   for e in result.errors)

    def test_entrada_exatamente_90_percent_valida(self):
        """down_payment == 90% do target deve ser aceito."""
        req = self._req(target_amount=10_000.0, down_payment=9_000.0)  # exatamente 90%
        result = InputValidator.validate(req)
        erros_prop = [e for e in result.errors if "90" in e]
        assert len(erros_prop) == 0

    def test_entrada_zero_valida(self):
        """down_payment = 0 deve ser aceito."""
        req = self._req(target_amount=30_000.0, down_payment=0.0)
        result = InputValidator.validate(req)
        # Sem erro de proporção
        assert all("90%" not in e for e in result.errors)

    # ── Regra 3: budget mínimo ───────────────────────────────────

    def test_budget_abaixo_de_100_gera_erro(self):
        """max_monthly_budget < R$100 deve gerar erro."""
        req = self._req(max_monthly_budget=50.0)
        result = InputValidator.validate(req)
        assert not result.is_valid
        assert any("100" in e or "budget" in e.lower() for e in result.errors)

    def test_budget_none_nao_gera_erro(self):
        """max_monthly_budget = None (não informado) não gera erro."""
        req = self._req(max_monthly_budget=None)
        result = InputValidator.validate(req)
        budget_erros = [e for e in result.errors if "budget" in e.lower() or "100" in e]
        assert len(budget_erros) == 0

    def test_budget_exatamente_100_valido(self):
        """max_monthly_budget >= R$100 deve ser aceito."""
        req = self._req(max_monthly_budget=100.0)
        result = InputValidator.validate(req)
        budget_erros = [e for e in result.errors if "100" in e and "budget" in e.lower()]
        assert len(budget_erros) == 0

    # ── Regra 4: prazo por tipo de bem ───────────────────────────

    def test_prazo_excessivo_para_viagem_gera_erro(self):
        """financing_months > 60 para VIAGEM deve gerar erro."""
        req = self._req(
            asset_type=AssetType.VIAGEM,
            target_amount=5_000.0,
            down_payment=0,
            financing_months=84,  # 7 anos para viagem
        )
        result = InputValidator.validate(req)
        assert not result.is_valid

    def test_prazo_valido_para_imovel(self):
        """420 meses para IMOVEL deve ser aceito."""
        req = self._req(
            asset_type=AssetType.IMOVEL,
            target_amount=500_000.0,
            down_payment=50_000.0,
            max_monthly_budget=5_000.0,
            financing_months=420,
        )
        result = InputValidator.validate(req)
        prazo_erros = [e for e in result.errors if "420" in e or "prazo" in e.lower()]
        assert len(prazo_erros) == 0

    # ── Regra 5: valor mínimo por bem ────────────────────────────

    def test_imovel_abaixo_do_minimo_gera_erro(self):
        """IMOVEL < R$50.000 deve gerar erro."""
        req = self._req(
            asset_type=AssetType.IMOVEL,
            target_amount=30_000.0,
            down_payment=5_000.0,
        )
        result = InputValidator.validate(req)
        assert not result.is_valid

    def test_veiculo_acima_do_minimo_valido(self):
        """VEICULO >= R$5.000 deve ser aceito."""
        req = self._req(asset_type=AssetType.VEICULO, target_amount=30_000.0)
        result = InputValidator.validate(req)
        minimo_erros = [e for e in result.errors if "mínimo" in e.lower() or "minimo" in e.lower()]
        assert len(minimo_erros) == 0

    # ── Regra 6: flags contraditórios (deve ser warning, não erro) ─

    def test_prefers_consortium_sem_include_consortium_gera_warning(self):
        """prefers_consortium=True + include_consortium=False → só warning."""
        req = self._req(prefers_consortium=True, include_consortium=False)
        result = InputValidator.validate(req)
        # Deve ser warning, não erro bloqueante
        assert result.is_valid  # não bloqueia
        assert len(result.warnings) > 0

    # ── Regra 7: target_date vs financing_months (warning) ───────

    def test_target_date_conflita_com_financing_months_gera_warning(self):
        """target_date implica 12 meses mas financing_months=84 → warning."""
        req = self._req(
            target_date=date.today() + timedelta(days=365),  # ~12 meses
            financing_months=84,
        )
        result = InputValidator.validate(req)
        assert result.is_valid  # não bloqueia
        assert len(result.warnings) > 0

    # ── Request completamente válido ─────────────────────────────

    def test_request_valido_sem_erros(self, base_request):
        """Request padrão válido não gera nenhum erro."""
        result = InputValidator.validate(base_request)
        assert result.is_valid
        assert len(result.errors) == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: LiquidityValidator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLiquidityValidator:
    """Testa os 4 níveis de risco e a hierarquia de referência."""

    def test_nivel_safe_abaixo_25_percent(self):
        """≤ 25% de comprometimento → SAFE e is_sustainable=True."""
        result = LiquidityValidator.calculate(
            monthly_payment=1_000.0,
            safe_to_spend=10_000.0,  # 10% → SAFE
        )
        assert result.risk_level == RiskLevel.SAFE
        assert result.is_sustainable is True
        assert result.impact < 0  # negativo por convenção

    def test_nivel_warning_entre_26_e_40(self):
        """26–40% de comprometimento → WARNING."""
        result = LiquidityValidator.calculate(
            monthly_payment=3_000.0,
            safe_to_spend=10_000.0,  # 30% → WARNING
        )
        assert result.risk_level == RiskLevel.WARNING
        assert result.is_sustainable is True

    def test_nivel_high_entre_41_e_70(self):
        """41–70% de comprometimento → HIGH."""
        result = LiquidityValidator.calculate(
            monthly_payment=5_000.0,
            safe_to_spend=10_000.0,  # 50% → HIGH
        )
        assert result.risk_level == RiskLevel.HIGH
        assert result.is_sustainable is True

    def test_nivel_critical_acima_70_percent(self):
        """Acima de 70% → CRITICAL e is_sustainable=False."""
        result = LiquidityValidator.calculate(
            monthly_payment=8_000.0,
            safe_to_spend=10_000.0,  # 80% → CRITICAL
        )
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.is_sustainable is False

    def test_impact_e_negativo_por_convencao(self):
        """liquidity_impact deve ser negativo (comprometimento de saldo)."""
        result = LiquidityValidator.calculate(
            monthly_payment=2_000.0,
            safe_to_spend=8_000.0,
        )
        assert result.impact < 0

    def test_impact_formula_correta(self):
        """impact = -(payment / safe_to_spend)."""
        result = LiquidityValidator.calculate(
            monthly_payment=2_000.0,
            safe_to_spend=8_000.0,
        )
        assert abs(result.impact - (-0.25)) < 0.001

    # ── Hierarquia de referência ─────────────────────────────────

    def test_prioridade_safe_to_spend_sobre_budget(self):
        """safe_to_spend prevalece sobre max_monthly_budget."""
        # Com safe_to_spend=8000 → 25% (SAFE)
        # Com max_monthly_budget=4000 → 50% (HIGH)
        result = LiquidityValidator.calculate(
            monthly_payment=2_000.0,
            safe_to_spend=8_000.0,
            max_monthly_budget=4_000.0,
        )
        assert result.risk_level == RiskLevel.SAFE
        assert result.reference_used == "safe_to_spend" or "f1" in result.reference_used.lower()

    def test_fallback_para_budget_quando_sem_safe(self):
        """Sem safe_to_spend, usa max_monthly_budget."""
        result = LiquidityValidator.calculate(
            monthly_payment=2_000.0,
            safe_to_spend=None,
            max_monthly_budget=8_000.0,  # 25% → SAFE
        )
        assert result.risk_level == RiskLevel.SAFE
        assert "budget" in result.reference_used.lower() or "max" in result.reference_used.lower()

    def test_sem_referencia_retorna_impact_zero(self):
        """Sem safe_to_spend nem budget, impact deve ser 0.0 com warning."""
        result = LiquidityValidator.calculate(
            monthly_payment=2_000.0,
            safe_to_spend=None,
            max_monthly_budget=None,
        )
        assert result.impact == 0.0
        assert len(result.warnings) > 0

    def test_critical_gera_warning_text(self):
        """Nível CRITICAL deve gerar texto de aviso."""
        result = LiquidityValidator.calculate(
            monthly_payment=9_000.0,
            safe_to_spend=10_000.0,
        )
        assert len(result.warnings) > 0
