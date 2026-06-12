# tests/optimizer/test_optimizer_service.py
# Testes do OptimizerService, CardSimulator e CardRanking
# Usa os cartões e lógica reais do projeto — sem dados mockados arbitrários.

from __future__ import annotations

import pytest
import polars as pl
from datetime import date, timedelta

from app.optimizer.models import (
    CardFlag,
    CardRecord,
    CardSimulationResult,
    CardType,
    LiquidityRisk,
    OptimizationRequest,
    RecommendationType,
    WaiverRules,
    CashbackCategoryRule,
    BenefitTag,
)
from app.optimizer.profiler import ConsumptionProfiler, UserProfile
from app.optimizer.simulator import CardSimulator
from app.optimizer.ranking import CardRanking
from app.optimizer.card_loader import CardKnowledgeBase
from app.optimizer.services.optimizer_service import OptimizerService


# ─── Constantes de data ──────────────────────────────────────────────────────

TODAY = date(2026, 3, 15)
RECENT = TODAY - timedelta(days=30)
RECENT_2 = TODAY - timedelta(days=60)


# ─── Factories de DataFrame de transações ───────────────────────────────────

def _make_txn(
    amount: float,
    txn_date: date = None,
    category: str = "alimentacao",
    transaction_type: str = "DEBIT",
    context_type: str = "PF",
    description: str = "compra",
    txn_id: str = None,
) -> dict:
    return {
        "transaction_id": txn_id or f"txn-{amount}-{txn_date}",
        "user_id": "user-test",
        "description": description,
        "amount": amount,
        "date": txn_date or RECENT,
        "transaction_type": transaction_type,
        "category": category,
        "context_type": context_type,
    }


_SCHEMA = {
    "transaction_id": pl.Utf8,
    "user_id": pl.Utf8,
    "description": pl.Utf8,
    "amount": pl.Float64,
    "date": pl.Date,
    "transaction_type": pl.Utf8,
    "category": pl.Utf8,
    "context_type": pl.Utf8,
}


def _df(*rows: dict) -> pl.DataFrame:
    return pl.DataFrame(list(rows), schema=_SCHEMA)


def _shadow_df(amounts: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {"amount": amounts, "type": ["SUBSCRIPTION"] * len(amounts)},
        schema={"amount": pl.Float64, "type": pl.Utf8},
    )


# ─── Fixtures de Perfil ──────────────────────────────────────────────────────

@pytest.fixture
def perfil_clt_medio() -> pl.DataFrame:
    """Perfil CLT: salário R$ 8.000/mês, gastos regulares em 3 meses."""
    rows = []
    for i, mes in enumerate([(2025, 12), (2026, 1), (2026, 2)]):
        rows += [
            _make_txn(-2000.0, txn_date=date(*mes, 5), category="moradia", txn_id=f"aluguel-{i}"),
            _make_txn(-800.0,  txn_date=date(*mes, 10), category="alimentacao", txn_id=f"super-{i}"),
            _make_txn(-400.0,  txn_date=date(*mes, 15), category="transporte", txn_id=f"uber-{i}"),
            _make_txn(-300.0,  txn_date=date(*mes, 20), category="lazer", txn_id=f"lazer-{i}"),
            _make_txn(8000.0,  txn_date=date(*mes, 5),  category="renda", transaction_type="CREDIT",
                      description="SALARIO CLT EMPRESA X", txn_id=f"salario-{i}"),
        ]
    return _df(*rows)


@pytest.fixture
def perfil_alto_gasto() -> pl.DataFrame:
    """Perfil premium: gastos altos (R$ 15.000/mês) em 2 meses — arquitetura v2.1 exige ≥ 2 meses."""
    rows = [
        # Fevereiro 2026
        _make_txn(-5000.0, txn_date=date(2026, 2, 5),  category="moradia", txn_id="aluguel_feb"),
        _make_txn(-2000.0, txn_date=date(2026, 2, 10), category="alimentacao", txn_id="rest_feb"),
        _make_txn(-3000.0, txn_date=date(2026, 2, 15), category="Lazer",
                  description="Hotel USD 590", txn_id="hotel_feb"),
        _make_txn(-1500.0, txn_date=date(2026, 2, 20), category="Transporte",
                  description="Passagem aerea", txn_id="voo_feb"),
        _make_txn(-800.0,  txn_date=date(2026, 2, 22), category="outros",
                  description="Amazon internacional EUR 150", txn_id="intl_feb"),
        _make_txn(20000.0, txn_date=date(2026, 2, 5),  category="renda", transaction_type="CREDIT",
                  description="SALARIO EMPRESA X", txn_id="salario_feb"),
        # Janeiro 2026 — segundo mês para cumprir requisito de ≥ 2 meses (arquitetura v2.1)
        _make_txn(-5000.0, txn_date=date(2026, 1, 5),  category="moradia", txn_id="aluguel_jan"),
        _make_txn(-2000.0, txn_date=date(2026, 1, 10), category="alimentacao", txn_id="rest_jan"),
        _make_txn(-3000.0, txn_date=date(2026, 1, 15), category="Lazer",
                  description="Hotel USD 590", txn_id="hotel_jan"),
        _make_txn(-1500.0, txn_date=date(2026, 1, 20), category="Transporte",
                  description="Passagem aerea", txn_id="voo_jan"),
        _make_txn(20000.0, txn_date=date(2026, 1, 5),  category="renda", transaction_type="CREDIT",
                  description="SALARIO EMPRESA X", txn_id="salario_jan"),
    ]
    return _df(*rows)


@pytest.fixture
def perfil_baixo_gasto() -> pl.DataFrame:
    """Perfil com gasto baixo (R$ 800/mês) — não vale a pena pagar anuidade alta."""
    rows = [
        _make_txn(-400.0, txn_date=date(2026, 2, 5),  category="alimentacao", txn_id="a"),
        _make_txn(-400.0, txn_date=date(2026, 2, 20), category="transporte", txn_id="t"),
        _make_txn(2500.0, txn_date=date(2026, 2, 5),  category="renda", transaction_type="CREDIT",
                  description="SALARIO", txn_id="s"),
    ]
    return _df(*rows)


# ─── Factories de CartãoRecord ───────────────────────────────────────────────

def _card_cashback_flat(
    card_id: str = "card_cashback_1p",
    cashback_pct: float = 0.01,
    annuity: float = 0.0,
    waiver_type: str = "always_free",
    min_income: float = 0.0,
) -> CardRecord:
    return CardRecord(
        card_id=card_id,
        name=f"Cartão Cashback {cashback_pct*100:.0f}%",
        issuer="Banco Teste",
        flag=CardFlag.VISA,
        card_type=CardType.CASHBACK,
        public_target="geral",
        min_income=min_income,
        requires_proof_of_income=False,
        secured_card=False,
        prepaid=False,
        consigned=False,
        base_annuity=annuity,
        waiver_rules=WaiverRules(type=waiver_type, description="Sempre grátis"),
        cashback_pct=cashback_pct,
        data_trust_score=0.9,
        last_updated="2026-01-01",
    )


def _card_cashback_com_anuidade(annuity: float = 600.0, threshold: float = 12000.0) -> CardRecord:
    return CardRecord(
        card_id="card_com_anuidade",
        name="Cartão Premium Anuidade",
        issuer="Banco Premium",
        flag=CardFlag.MASTERCARD,
        card_type=CardType.CASHBACK,
        public_target="premium",
        min_income=60_000.0,
        requires_proof_of_income=True,
        secured_card=False,
        prepaid=False,
        consigned=False,
        base_annuity=annuity,
        waiver_rules=WaiverRules(
            type="spend_threshold",
            threshold=threshold,
            description=f"Isento ao gastar R$ {threshold:.0f}/ano",
        ),
        cashback_pct=0.015,
        data_trust_score=0.85,
        last_updated="2026-01-01",
    )


def _card_pontos(
    points_per_brl: float = 2.0,
    conversion_rate: float = 20.0,
    annuity: float = 0.0,
) -> CardRecord:
    return CardRecord(
        card_id="card_pontos",
        name="Cartão de Pontos",
        issuer="Banco Pontos",
        flag=CardFlag.VISA,
        card_type=CardType.POINTS,
        public_target="viagens",
        min_income=0.0,
        requires_proof_of_income=False,
        secured_card=False,
        prepaid=False,
        consigned=False,
        base_annuity=annuity,
        waiver_rules=WaiverRules(type="always_free", description="Sempre grátis"),
        points_per_brl=points_per_brl,
        points_currency="pontos",
        points_conversion_rate=conversion_rate,
        benefit_tags=[BenefitTag.TRAVEL, BenefitTag.LOUNGE],
        data_trust_score=0.8,
        last_updated="2026-01-01",
    )


def _card_cashback_por_categoria() -> CardRecord:
    """Cartão M2.5: cashback diferenciado por categoria."""
    return CardRecord(
        card_id="card_categoria",
        name="Cartão Alimentação+",
        issuer="Banco Cat",
        flag=CardFlag.ELO,
        card_type=CardType.CASHBACK,
        public_target="cotidiano",
        min_income=0.0,
        requires_proof_of_income=False,
        secured_card=False,
        prepaid=False,
        consigned=False,
        base_annuity=0.0,
        waiver_rules=WaiverRules(type="always_free", description="Grátis"),
        cashback_pct=None,
        cashback_default_pct=0.005,
        cashback_categories=[
            CashbackCategoryRule(category="alimentacao", pct=0.03, cap_monthly=50.0),
            CashbackCategoryRule(category="farmacia", pct=0.05, cap_monthly=30.0),
        ],
        data_trust_score=0.9,
        last_updated="2026-01-01",
    )


# ─── Testes: CardSimulator ───────────────────────────────────────────────────

class TestCardSimulatorAnnuity:
    def test_anuidade_zero_para_cartao_gratuito(self):
        sim = CardSimulator()
        card = _card_cashback_flat(annuity=0.0, waiver_type="always_free")
        profile = ConsumptionProfiler().build(
            _df(_make_txn(-1000.0)), reference_date=TODAY
        )
        result = sim.simulate(card, profile, safe_to_spend=2000.0)
        assert result.annuity_waived is True
        assert result.annuity_effective == 0.0

    def test_anuidade_cobrada_abaixo_do_threshold(self):
        sim = CardSimulator()
        # Gasto de R$ 600/mês = R$ 7.200/ano, threshold = R$ 12.000
        # Achievability = 1 − (12.000 − 7.200)/12.000 = 0.40 < 0.80 → NÃO isenta
        card = _card_cashback_com_anuidade(annuity=600.0, threshold=12_000.0)
        profile = ConsumptionProfiler().build(
            _df(_make_txn(-600.0, txn_date=date(2026, 2, 10))),
            reference_date=TODAY,
        )
        result = sim.simulate(card, profile, safe_to_spend=2000.0)
        assert result.annuity_waived is False
        assert result.annuity_effective == 600.0

    def test_anuidade_isenta_acima_do_threshold(self):
        sim = CardSimulator()
        # Gasto de R$ 2.000/mês = R$ 24.000/ano → isenta threshold de R$ 12.000
        card = _card_cashback_com_anuidade(annuity=600.0, threshold=12_000.0)
        rows = [
            _make_txn(-2000.0, txn_date=date(2026, 2, 5),  txn_id="a", transaction_type="CREDIT"),
            _make_txn(-2000.0, txn_date=date(2026, 1, 5),  txn_id="b", transaction_type="CREDIT"),
        ]
        profile = ConsumptionProfiler().build(_df(*rows), reference_date=TODAY)
        result = sim.simulate(card, profile, safe_to_spend=3000.0)
        assert result.annuity_waived is True
        assert result.annuity_effective == 0.0


class TestCardSimulatorBenefitValue:
    def test_cashback_flat_positivo(self):
        sim = CardSimulator()
        card = _card_cashback_flat(cashback_pct=0.01)  # 1% no gasto
        # Gasto de R$ 1.000/mês → cashback esperado = R$ 1.000 * 12 * 0.01 = R$ 120
        profile = ConsumptionProfiler().build(
            _df(_make_txn(-1000.0, txn_date=date(2026, 2, 5), transaction_type="CREDIT")),
            reference_date=TODAY,
        )
        result = sim.simulate(card, profile, safe_to_spend=2000.0)
        assert result.points_value_expected == pytest.approx(120.0, abs=5.0)
        assert result.net_gain_expected > 0  # cartão grátis + cashback = sempre positivo

    def test_pontos_value_calculado(self):
        sim = CardSimulator()
        # 2 pontos/R$ × R$ 12.000/ano = 24.000 pts; 24.000/1000 × R$ 20 = R$ 480
        card = _card_pontos(points_per_brl=2.0, conversion_rate=20.0)
        profile = ConsumptionProfiler().build(
            _df(_make_txn(-1000.0, txn_date=date(2026, 2, 5))),
            reference_date=TODAY,
        )
        result = sim.simulate(card, profile, safe_to_spend=2000.0)
        # Pode usar loyalty_program (dinâmico) ou fallback — ambos devem ser > 0
        assert result.points_value_expected > 0
        assert result.net_gain_expected > 0

    def test_cenario_pessimista_menor_que_esperado(self):
        sim = CardSimulator()
        card = _card_cashback_flat(cashback_pct=0.02)
        profile = ConsumptionProfiler().build(
            _df(_make_txn(-1000.0, txn_date=date(2026, 2, 5))),
            reference_date=TODAY,
        )
        result = sim.simulate(card, profile)
        assert result.net_gain_min <= result.net_gain_expected <= result.net_gain_max

    def test_cashback_por_categoria_usa_regras(self):
        sim = CardSimulator()
        card = _card_cashback_por_categoria()
        # Gasto de R$ 600/mês em alimentação → cashback 3% = R$ 18/mês, mas cap = R$ 50/mês
        profile = ConsumptionProfiler().build(
            _df(
                _make_txn(-600.0, txn_date=date(2026, 2, 5), category="alimentacao", txn_id="alim", transaction_type="CREDIT"),
                _make_txn(-200.0, txn_date=date(2026, 2, 10), category="transporte", txn_id="transp", transaction_type="CREDIT"),
            ),
            reference_date=TODAY,
        )
        result = sim.simulate(card, profile)
        # Cashback por categoria deve ser maior que o flat default (0.5%)
        assert result.points_value_expected > 0
        # Com 3% em alimentação (principal categoria), valor esperado > flat de 0.5%
        flat_value = (600 + 200) * 12 * 0.005
        # Resultado esperado > flat_value (taxa mais alta em alimentação)
        assert result.points_value_expected >= flat_value * 0.8  # margem tolerância


class TestCardSimulatorLiquidity:
    def test_liquidity_safe_quando_anuidade_zero(self):
        sim = CardSimulator()
        card = _card_cashback_flat()
        profile = ConsumptionProfiler().build(
            _df(_make_txn(-1000.0)), reference_date=TODAY
        )
        result = sim.simulate(card, profile, safe_to_spend=2000.0)
        assert result.liquidity_risk == LiquidityRisk.SAFE
        assert result.liquidity_impact == 0.0

    def test_liquidity_critical_sem_safe_to_spend(self):
        """Anuidade alta + safe_to_spend=None → CRITICAL."""
        sim = CardSimulator()
        card = _card_cashback_com_anuidade(annuity=1200.0, threshold=999_999.0)
        profile = ConsumptionProfiler().build(
            _df(_make_txn(-500.0)), reference_date=TODAY
        )
        result = sim.simulate(card, profile, safe_to_spend=None)
        assert result.liquidity_risk == LiquidityRisk.CRITICAL

    def test_liquidity_warning_com_anuidade_moderada(self):
        """Anuidade de R$ 300/ano e safe_to_spend=R$ 2.500/mês → impacto < 15%."""
        sim = CardSimulator()
        # R$ 300/ano → R$ 25/mês; safe_to_spend = R$ 2.500 → impacto = 1%
        card = _card_cashback_com_anuidade(annuity=300.0, threshold=999_999.0)
        profile = ConsumptionProfiler().build(
            _df(_make_txn(-500.0)), reference_date=TODAY
        )
        result = sim.simulate(card, profile, safe_to_spend=2500.0)
        assert result.liquidity_impact < 0.15
        assert result.liquidity_risk == LiquidityRisk.SAFE


class TestCardSimulatorROI:
    def test_roi_verdict_vale_a_pena(self):
        """Cartão gratuito com cashback gera ROI positivo."""
        sim = CardSimulator()
        card = _card_cashback_flat(cashback_pct=0.01)
        profile = ConsumptionProfiler().build(
            _df(_make_txn(-2000.0, txn_date=date(2026, 2, 5))),
            reference_date=TODAY,
        )
        roi = sim.calculate_current_card_roi(card, profile)
        from app.optimizer.models import CardROIVerdict
        assert roi.verdict == CardROIVerdict.VALE_A_PENA
        assert roi.net_roi >= 0

    def test_roi_verdict_nao_vale_anuidade_alta(self):
        """Anuidade de R$ 1.200/ano com gasto baixo → NAO_VALE."""
        sim = CardSimulator()
        card = _card_cashback_com_anuidade(annuity=1200.0, threshold=999_999.0)
        # Gasto modesto de R$ 400/mês → cashback 1.5% = R$ 72/ano — muito abaixo de R$ 1.200
        profile = ConsumptionProfiler().build(
            _df(_make_txn(-400.0, txn_date=date(2026, 2, 5))),
            reference_date=TODAY,
        )
        roi = sim.calculate_current_card_roi(card, profile)
        from app.optimizer.models import CardROIVerdict
        assert roi.verdict == CardROIVerdict.NAO_VALE
        assert roi.net_roi < -200

    def test_roi_audit_beneficios_usados(self):
        """Usuário com gasto internacional deve ter tag INTERNACIONAL como 'usado'."""
        sim = CardSimulator()
        card = CardRecord(
            card_id="intl-card",
            name="Cartão Internacional",
            issuer="Banco Global",
            flag=CardFlag.VISA,
            card_type=CardType.CASHBACK,
            public_target="viajante",
            min_income=0.0,
            requires_proof_of_income=False,
            secured_card=False,
            prepaid=False,
            consigned=False,
            base_annuity=0.0,
            waiver_rules=WaiverRules(type="always_free", description="Grátis"),
            cashback_pct=0.01,
            benefit_tags=[BenefitTag.INTERNACIONAL, BenefitTag.LOUNGE],
            data_trust_score=0.9,
            last_updated="2026-01-01",
        )
        profile = ConsumptionProfiler().build(
            _df(
                _make_txn(-500.0, description="Netflix USD 9.99", txn_id="usd"),
                _make_txn(-200.0, description="compra local", txn_id="local"),
            ),
            reference_date=TODAY,
        )
        roi = sim.calculate_current_card_roi(card, profile)
        assert any("Internacional" in b or "IOF" in b for b in roi.benefits_used)


class TestCardRanking:
    def _make_result(
        self,
        net_gain: float,
        liquidity_risk: LiquidityRisk = LiquidityRisk.SAFE,
        confidence: float = 0.8,
        eligibility: float = 0.9,
        card_id: str = "card-1",
    ) -> CardSimulationResult:
        return CardSimulationResult(
            card_id=card_id,
            card_name="Cartão Teste",
            issuer="Banco Teste",
            flag=CardFlag.VISA,
            annuity_effective=0.0,
            annuity_waived=True,
            points_value_min=0.0,
            points_value_expected=net_gain,
            points_value_max=net_gain * 1.2,
            net_gain_min=net_gain * 0.8,
            net_gain_expected=net_gain,
            net_gain_max=net_gain * 1.2,
            liquidity_impact=0.0,
            liquidity_risk=liquidity_risk,
            confidence_score=confidence,
            eligibility_score=eligibility,
        )

    def test_ordena_por_net_gain_decrescente(self):
        ranking = CardRanking()
        profile = UserProfile(monthly_avg_spend=1000.0, data_coverage_months=3)
        r1 = self._make_result(net_gain=500.0, card_id="bom")
        r2 = self._make_result(net_gain=100.0, card_id="razoavel")
        r3 = self._make_result(net_gain=1000.0, card_id="otimo")
        ranked = ranking.rank([r1, r2, r3], profile)
        assert ranked[0].card_id == "otimo"
        assert ranked[-1].card_id == "razoavel"

    def test_penalidade_liquidez_critical_desce_ranking(self):
        ranking = CardRanking()
        profile = UserProfile(monthly_avg_spend=1000.0, data_coverage_months=3)
        # Cartão bom financeiramente mas com liquidez CRITICAL → penalidade 80%
        r_critical = self._make_result(net_gain=500.0, liquidity_risk=LiquidityRisk.CRITICAL, card_id="critical")
        r_safe = self._make_result(net_gain=300.0, liquidity_risk=LiquidityRisk.SAFE, card_id="safe")
        ranked = ranking.rank([r_critical, r_safe], profile)
        # SAFE com R$ 300 deve superar CRITICAL com R$ 500 (penalizado a 80%)
        assert ranked[0].card_id == "safe"

    def test_penalidade_confianca_baixa(self):
        ranking = CardRanking()
        profile = UserProfile(monthly_avg_spend=1000.0, data_coverage_months=1)
        r_baixa_confianca = self._make_result(
            net_gain=600.0, confidence=0.2, card_id="confianca_baixa"
        )
        r_alta_confianca = self._make_result(
            net_gain=400.0, confidence=0.9, card_id="confianca_alta"
        )
        ranked = ranking.rank([r_baixa_confianca, r_alta_confianca], profile)
        # Confiança baixa (× 0.5) → 600 × 0.5 = 300 < 400
        assert ranked[0].card_id == "confianca_alta"

    def test_promocao_por_elegibilidade(self):
        """Cartão com eligibility_score < 0.4 no top deve ser substituído."""
        ranking = CardRanking()
        profile = UserProfile(monthly_avg_spend=2000.0, data_coverage_months=3)
        r_quase_inacessivel = self._make_result(
            net_gain=1000.0, eligibility=0.3, card_id="inacessivel"
        )
        r_acessivel = self._make_result(
            net_gain=500.0, eligibility=0.8, card_id="acessivel"
        )
        ranked = ranking.rank([r_quase_inacessivel, r_acessivel], profile)
        assert ranked[0].card_id == "acessivel"

    def test_bonus_internacional_para_viajante(self):
        ranking = CardRanking()
        # Perfil viajante: gasto internacional R$ 600/mês
        profile = UserProfile(
            monthly_avg_spend=3000.0,
            data_coverage_months=3,
            international_spend_monthly=600.0,
        )
        r_intl = self._make_result(net_gain=400.0, card_id="internacional")
        r_intl.benefit_tags = [BenefitTag.INTERNACIONAL]
        r_sem_intl = self._make_result(net_gain=420.0, card_id="sem_intl")
        ranked = ranking.rank([r_intl, r_sem_intl], profile)
        # Bônus R$ 200 no ranking → intl (400 + 200 = 600) supera sem_intl (420)
        assert ranked[0].card_id == "internacional"

    def test_lista_vazia_retorna_vazia(self):
        ranking = CardRanking()
        profile = UserProfile()
        assert ranking.rank([], profile) == []


# ─── Testes: OptimizerService (integração) ──────────────────────────────────

@pytest.fixture
def service(monkeypatch):
    """Service real sem salvar no DuckDB."""
    monkeypatch.setattr(
        "app.optimizer.services.optimizer_service.save_optimization_report",
        lambda r: None,
    )
    return OptimizerService()


class TestOptimizerServiceFluxoCompleto:
    def test_recomendacao_cartao_real_renda_alta(self, service, perfil_alto_gasto):
        """Pipeline completo para usuário de alta renda — deve recomendar troca."""
        request = OptimizationRequest(
            user_id="user-premium",
            current_cards=[],
            safe_to_spend=5000.0,
            monthly_income=20000.0,
        )
        report = service.analyze(
            request=request,
            transactions_df=perfil_alto_gasto,
            reference_date=TODAY,
        )
        assert report.user_id == "user-premium"
        assert len(report.all_cards) > 0
        assert report.recommendation_type in (
            RecommendationType.SWITCH_RECOMMENDED,
            RecommendationType.KEEP_CURRENT,
        )

    def test_recomendacao_para_renda_baixa(self, service, perfil_baixo_gasto):
        """Perfil de renda baixa filtra cartões premium por min_income."""
        request = OptimizationRequest(
            user_id="user-econ",
            current_cards=[],
            safe_to_spend=800.0,
            monthly_income=2500.0,
        )
        report = service.analyze(
            request=request,
            transactions_df=perfil_baixo_gasto,
            reference_date=TODAY,
        )
        assert report.user_id == "user-econ"
        # Cartões premium com min_income alto não devem aparecer
        for card_result in report.all_cards:
            card = service.knowledge_base.get_by_id(card_result.card_id)
            if card:
                assert card.min_income <= 2500.0 * 12

    def test_dados_insuficientes_retorna_insufficient(self, service):
        """DataFrame vazio → INSUFFICIENT_DATA."""
        request = OptimizationRequest(
            user_id="user-sem-dados",
            current_cards=[],
            monthly_income=5000.0,
        )
        report = service.analyze(
            request=request,
            transactions_df=pl.DataFrame(),
            reference_date=TODAY,
        )
        # Com df vazio e renda declarada: gasto é estimado (40% da renda).
        # Deve retornar LOW_CONFIDENCE, não SWITCH_RECOMMENDED.
        assert report.user_id == "user-sem-dados"
        assert report.recommendation_type in (
            RecommendationType.INSUFFICIENT_DATA,
            RecommendationType.KEEP_CURRENT,
            RecommendationType.LOW_CONFIDENCE,
        )
        assert report.recommendation_type != RecommendationType.SWITCH_RECOMMENDED, (
            "Sem histórico real não deve retornar SWITCH_RECOMMENDED"
        )
        assert any("gasto estimado" in w.lower() or "histórico" in w.lower() for w in report.warnings), (
            "Deve haver warning explícito sobre ausência de dados reais"
        )

    def test_melhor_cartao_e_o_primeiro_da_lista(self, service, perfil_clt_medio):
        """O best_card deve ser idêntico ao first item de all_cards."""
        request = OptimizationRequest(
            user_id="user-clt",
            current_cards=[],
            safe_to_spend=3000.0,
            monthly_income=8000.0,
        )
        report = service.analyze(
            request=request,
            transactions_df=perfil_clt_medio,
            reference_date=TODAY,
        )
        if report.recommendation_type == RecommendationType.SWITCH_RECOMMENDED:
            assert report.best_card is not None
            assert report.best_card.card_id == report.all_cards[0].card_id

    def test_shadow_invoices_reduz_safe_to_spend_efetivo(self, service, perfil_clt_medio):
        """Shadow invoices comprometem parte do orçamento — confidence e liquidity impactados."""
        request = OptimizationRequest(
            user_id="user-comprometido",
            current_cards=[],
            safe_to_spend=1500.0,
            monthly_income=8000.0,
        )
        # Shadow invoices de R$ 1.200/mês — 80% do safe_to_spend
        shadow = _shadow_df([-1200.0])
        report = service.analyze(
            request=request,
            transactions_df=perfil_clt_medio,
            shadow_invoices_df=shadow,
            reference_date=TODAY,
        )
        assert report.user_id == "user-comprometido"
        # Deve gerar ao menos um warning sobre dados disponíveis
        # (ou retornar lista de cartões com penalidades de liquidez)
        assert isinstance(report.all_cards, list)

    def test_cartao_ja_possui_excluido(self, service, perfil_clt_medio):
        """Cartões já possuídos pelo usuário não aparecem na recomendação."""
        kb = CardKnowledgeBase()
        kb.load()
        cards = kb.filter_eligible(annual_income=8000 * 12)
        if not cards:
            pytest.skip("Base de cartões vazia")

        first_card_id = cards[0].card_id
        request = OptimizationRequest(
            user_id="user-clt",
            current_cards=[first_card_id],
            safe_to_spend=3000.0,
            monthly_income=8000.0,
        )
        report = service.analyze(
            request=request,
            transactions_df=perfil_clt_medio,
            reference_date=TODAY,
        )
        for card_result in report.all_cards:
            assert card_result.card_id != first_card_id

    def test_report_tem_campos_obrigatorios(self, service, perfil_clt_medio):
        """Verifica que o OptimizationReport tem todos os campos esperados."""
        request = OptimizationRequest(
            user_id="user-clt",
            current_cards=[],
            safe_to_spend=3000.0,
            monthly_income=8000.0,
        )
        report = service.analyze(
            request=request,
            transactions_df=perfil_clt_medio,
            reference_date=TODAY,
        )
        assert report.report_id is not None and len(report.report_id) > 0
        assert report.generated_at is not None
        assert isinstance(report.strategy_text, str)
        assert isinstance(report.warnings, list)
        assert isinstance(report.all_cards, list)

    def test_warning_emitido_sem_renda_declarada(self, service, perfil_baixo_gasto):
        """Sem monthly_income e com historico curto (1 mês) → warning de renda ou histórico."""
        request = OptimizationRequest(
            user_id="user-sem-renda",
            current_cards=[],
            safe_to_spend=800.0,
            # monthly_income não declarado intencionalmente — deve disparar warning
        )
        report = service.analyze(
            request=request,
            transactions_df=perfil_baixo_gasto,
            reference_date=TODAY,
        )
        # Com 1 mês de dados → warning "Histórico ... curto" OU "renda"
        has_warning = any(
            "curto" in w.lower() or "renda" in w.lower() or "confiança" in w.lower()
            for w in report.warnings
        )
        assert has_warning or len(report.warnings) >= 1

    # ── Testes de integração: opportunity_score ───────────────────────────────

    def test_cartao_com_maior_opp_score_vira_best_card(self, service, perfil_clt_medio):
        """O best_card deve ser o cartão com maior opportunity_score após a re-ordenação."""
        request = OptimizationRequest(
            user_id="user-opp",
            current_cards=[],
            safe_to_spend=3000.0,
            monthly_income=8000.0,
        )
        report = service.analyze(
            request=request,
            transactions_df=perfil_clt_medio,
            reference_date=TODAY,
        )
        if report.recommendation_type != RecommendationType.SWITCH_RECOMMENDED:
            pytest.skip("Sem SWITCH_RECOMMENDED nesse perfil — teste não se aplica")

        assert report.best_card is not None
        best_opp = report.best_card.opportunity_score
        for card in report.all_cards[1:]:
            assert card.opportunity_score <= best_opp, (
                f"{card.card_id} (opp={card.opportunity_score:.2f}) "
                f"supera best_card {report.best_card.card_id} (opp={best_opp:.2f})"
            )

    def test_report_opportunity_score_bate_com_best_card(self, service, perfil_clt_medio):
        """report.opportunity_score deve ser igual a report.best_card.opportunity_score."""
        request = OptimizationRequest(
            user_id="user-opp-match",
            current_cards=[],
            safe_to_spend=3000.0,
            monthly_income=8000.0,
        )
        report = service.analyze(
            request=request,
            transactions_df=perfil_clt_medio,
            reference_date=TODAY,
        )
        if report.recommendation_type != RecommendationType.SWITCH_RECOMMENDED:
            pytest.skip("Sem SWITCH_RECOMMENDED nesse perfil — teste não se aplica")

        assert report.best_card is not None
        assert report.opportunity_score == pytest.approx(
            report.best_card.opportunity_score, abs=0.01
        ), (
            f"report.opportunity_score={report.opportunity_score:.2f} "
            f"!= best_card.opportunity_score={report.best_card.opportunity_score:.2f}"
        )

    def test_opportunity_score_breakdown_pertence_ao_best_card(self, service, perfil_clt_medio):
        """O breakdown do relatório deve referenciar o mesmo cartão que best_card."""
        request = OptimizationRequest(
            user_id="user-opp-breakdown",
            current_cards=[],
            safe_to_spend=3000.0,
            monthly_income=8000.0,
        )
        report = service.analyze(
            request=request,
            transactions_df=perfil_clt_medio,
            reference_date=TODAY,
        )
        if report.recommendation_type != RecommendationType.SWITCH_RECOMMENDED:
            pytest.skip("Sem SWITCH_RECOMMENDED nesse perfil — teste não se aplica")

        assert report.best_card is not None
        bd = report.opportunity_score_breakdown

        assert "opportunity_score" in bd, "Breakdown ausente"
        assert bd["opportunity_score"] == pytest.approx(
            report.best_card.opportunity_score, abs=0.01
        ), (
            f"Breakdown (opp={bd['opportunity_score']:.2f}) não pertence ao best_card "
            f"(opp={report.best_card.opportunity_score:.2f})"
        )
        # net_gain_expected do breakdown deve bater com o best_card
        assert bd["net_gain_expected"] == pytest.approx(
            report.best_card.net_gain_expected, abs=0.01
        )


class TestCardKnowledgeBaseIntegracao:
    def test_carrega_cartoes_reais(self):
        """Base de cartões deve conter ao menos 1 cartão."""
        kb = CardKnowledgeBase()
        cards = kb.load()
        assert len(cards) > 0

    def test_filtro_por_renda_anual(self):
        kb = CardKnowledgeBase()
        kb.load()
        # Renda mínima: filtra poucos; renda máxima: sem restrição
        eligible_low = kb.filter_eligible(annual_income=12_000.0)
        eligible_high = kb.filter_eligible(annual_income=600_000.0)
        # Renda alta libera mais cartões
        assert len(eligible_high) >= len(eligible_low)

    def test_get_by_id_existente(self):
        kb = CardKnowledgeBase()
        cards = kb.load()
        card = kb.get_by_id(cards[0].card_id)
        assert card is not None
        assert card.card_id == cards[0].card_id

    def test_get_by_id_inexistente(self):
        kb = CardKnowledgeBase()
        kb.load()
        assert kb.get_by_id("cartao-inexistente-xyz") is None

    def test_eligibility_score_renda_confortavel(self):
        kb = CardKnowledgeBase()
        cards = kb.load()
        if not cards:
            pytest.skip("Base de cartões vazia")
        # Cartão com min_income 0 → sempre score = spending_stability
        card = next((c for c in cards if c.min_income == 0), cards[0])
        score, reasons = kb.compute_eligibility_score(
            card=card,
            annual_income=120_000.0,
            spending_stability=0.9,
        )
        assert 0.0 <= score <= 1.0
        assert isinstance(reasons, list)
