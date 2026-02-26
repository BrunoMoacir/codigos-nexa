# tests/optimizer/test_liquidity_checker.py
# Testes unitários para LiquidityChecker
# Passo 2.3 — Funcionalidade 2: Nexa Optimizer

import pytest
from app.optimizer.validators.liquidity_checker import LiquidityChecker
from app.optimizer.models import LiquidityRisk


@pytest.fixture
def checker():
    return LiquidityChecker()


class TestLiquidityCheckerBoundaries:
    def test_zero_impact_is_safe(self, checker):
        assert checker.check(0.0) == LiquidityRisk.SAFE

    def test_exactly_10_pct_is_safe(self, checker):
        assert checker.check(0.10) == LiquidityRisk.SAFE

    def test_just_above_10_pct_is_warning(self, checker):
        assert checker.check(0.11) == LiquidityRisk.WARNING

    def test_exactly_25_pct_is_warning(self, checker):
        assert checker.check(0.25) == LiquidityRisk.WARNING

    def test_just_above_25_pct_is_high(self, checker):
        assert checker.check(0.26) == LiquidityRisk.HIGH

    def test_exactly_50_pct_is_high(self, checker):
        assert checker.check(0.50) == LiquidityRisk.HIGH

    def test_just_above_50_pct_is_critical(self, checker):
        assert checker.check(0.51) == LiquidityRisk.CRITICAL

    def test_100_pct_is_critical(self, checker):
        assert checker.check(1.0) == LiquidityRisk.CRITICAL
