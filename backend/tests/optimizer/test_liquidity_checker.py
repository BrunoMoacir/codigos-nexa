# tests/optimizer/test_liquidity_checker.py
# Testes unitários para LiquidityChecker — thresholds v2.1
# Arquitetura: < 0.05 SAFE, < 0.10 WARNING, < 0.20 HIGH, ≥ 0.20 CRITICAL

import pytest
from app.optimizer.validators.liquidity_checker import LiquidityChecker
from app.optimizer.models import LiquidityRisk


@pytest.fixture
def checker():
    return LiquidityChecker()


class TestLiquidityCheckerBoundaries:
    def test_zero_impact_is_safe(self, checker):
        assert checker.check(0.0) == LiquidityRisk.SAFE

    def test_below_5_pct_is_safe(self, checker):
        assert checker.check(0.04) == LiquidityRisk.SAFE

    def test_exactly_5_pct_is_warning(self, checker):
        # 0.05 não é < 0.05, cai em WARNING
        assert checker.check(0.05) == LiquidityRisk.WARNING

    def test_below_10_pct_is_warning(self, checker):
        assert checker.check(0.07) == LiquidityRisk.WARNING

    def test_exactly_10_pct_is_high(self, checker):
        # 0.10 não é < 0.10, cai em HIGH
        assert checker.check(0.10) == LiquidityRisk.HIGH

    def test_below_20_pct_is_high(self, checker):
        assert checker.check(0.15) == LiquidityRisk.HIGH

    def test_exactly_20_pct_is_critical(self, checker):
        # 0.20 não é < 0.20, cai em CRITICAL
        assert checker.check(0.20) == LiquidityRisk.CRITICAL

    def test_above_20_pct_is_critical(self, checker):
        assert checker.check(0.25) == LiquidityRisk.CRITICAL

    def test_50_pct_is_critical(self, checker):
        assert checker.check(0.50) == LiquidityRisk.CRITICAL

    def test_100_pct_is_critical(self, checker):
        assert checker.check(1.0) == LiquidityRisk.CRITICAL
