"""
Testes do PostPurchaseAnalyzer (R1.a) — análise retroativa de compras.

O PurchaseAdvisor é substituído por um fake determinístico; o pré-filtro
SQL é monkeypatchado com candidatos sintéticos.
"""

from datetime import date

import pytest

from app.purchase.models import PaymentMethod, PaymentOption
from app.purchase.post_purchase import PostPurchaseAnalyzer, _Candidate

_USER = "user_test"


def _option(method: PaymentMethod, net_cost: float, label: str = "") -> PaymentOption:
    return PaymentOption(
        method=method,
        label=label or method.value,
        total_cost=net_cost,
        net_cost=net_cost,
        net_cost_real=net_cost,
    )


class _FakeResult:
    def __init__(self, options):
        self.options = options


class _FakeAdvisor:
    """PurchaseAdvisor fake: cartão à vista sempre R$30 mais barato que PIX."""

    def analyze(self, request):
        return _FakeResult([
            _option(PaymentMethod.PIX_AVISTA, request.amount, "PIX à vista"),
            _option(PaymentMethod.CARTAO_AVISTA, request.amount - 30.0, "Cartão Top à vista"),
        ])


def _candidate(
    paid_method: str = "PIX_AVISTA",
    paid_label: str = "PIX à vista",
    amount: float = 1500.0,
    tx_id: str = "tx1",
) -> _Candidate:
    return _Candidate(
        transaction_id=tx_id,
        tx_date=date(2026, 7, 5),
        amount=amount,
        description="COMPRA MAGALU",
        category="Eletrônicos",
        paid_method=paid_method,
        paid_label=paid_label,
    )


@pytest.fixture
def analyzer(monkeypatch) -> PostPurchaseAnalyzer:
    import app.purchase.purchase_advisor as advisor_module

    monkeypatch.setattr(advisor_module, "PurchaseAdvisor", _FakeAdvisor)
    return PostPurchaseAnalyzer()


# ── Inferência de meio de pagamento ──────────────────────────────────

class TestInferencia:
    def test_pix_na_descricao(self):
        method, label = PostPurchaseAnalyzer._infer_paid_method("PIX QR MAGALU")
        assert method == "PIX_AVISTA"

    def test_cartao_na_descricao(self):
        method, _ = PostPurchaseAnalyzer._infer_paid_method("COMPRA CARTAO CREDITO LOJA")
        assert method == "CARTAO_AVISTA"

    def test_debito_sem_marcador_equivale_a_pix(self):
        method, label = PostPurchaseAnalyzer._infer_paid_method("COMPRA LOJA XYZ")
        assert method == "DEBITO_AVISTA"
        assert "débito" in label

    def test_merchant_limpo(self):
        m = PostPurchaseAnalyzer._merchant_from_description("COMPRA CARTAO 1234 MAGALU SP")
        assert "MAGALU" in m
        assert "1234" not in m


# ── Detecção fim-a-fim (advisor fake) ────────────────────────────────

class TestDetect:
    def test_pix_quando_cartao_era_melhor_gera_followup(self, analyzer, monkeypatch):
        monkeypatch.setattr(
            PostPurchaseAnalyzer, "_fetch_candidates",
            lambda self, uid, today: [_candidate("PIX_AVISTA")],
        )
        followups = analyzer.detect(_USER)
        assert len(followups) == 1
        f = followups[0]
        assert f.potential_savings_brl == pytest.approx(30.0)
        assert f.best_method_label == "Cartão Top à vista"
        assert f.paid_method_label == "PIX à vista"
        assert f.transaction_id == "tx1"

    def test_pagou_na_melhor_opcao_nao_gera_followup(self, analyzer, monkeypatch):
        monkeypatch.setattr(
            PostPurchaseAnalyzer, "_fetch_candidates",
            lambda self, uid, today: [
                _candidate("CARTAO_AVISTA", "cartão de crédito à vista")
            ],
        )
        assert analyzer.detect(_USER) == []

    def test_debito_comparado_como_pix(self, analyzer, monkeypatch):
        monkeypatch.setattr(
            PostPurchaseAnalyzer, "_fetch_candidates",
            lambda self, uid, today: [
                _candidate("DEBITO_AVISTA", "débito/PIX à vista")
            ],
        )
        followups = analyzer.detect(_USER)
        assert len(followups) == 1
        assert followups[0].paid_method_label == "débito/PIX à vista"

    def test_economia_pequena_e_descartada(self, monkeypatch):
        import app.purchase.purchase_advisor as advisor_module

        class _TinyAdvisor:
            def analyze(self, request):
                return _FakeResult([
                    _option(PaymentMethod.PIX_AVISTA, request.amount),
                    _option(PaymentMethod.CARTAO_AVISTA, request.amount - 5.0),
                ])

        monkeypatch.setattr(advisor_module, "PurchaseAdvisor", _TinyAdvisor)
        monkeypatch.setattr(
            PostPurchaseAnalyzer, "_fetch_candidates",
            lambda self, uid, today: [_candidate()],
        )
        assert PostPurchaseAnalyzer().detect(_USER) == []

    def test_maximo_3_candidatos_analisados(self, analyzer, monkeypatch):
        calls: list[str] = []
        original = PostPurchaseAnalyzer._analyze_candidate

        def _spy(self, uid, cand):
            calls.append(cand.transaction_id)
            return original(self, uid, cand)

        monkeypatch.setattr(PostPurchaseAnalyzer, "_analyze_candidate", _spy)
        monkeypatch.setattr(
            PostPurchaseAnalyzer, "_fetch_candidates",
            lambda self, uid, today: [
                _candidate(tx_id=f"tx{i}") for i in range(6)
            ],
        )
        analyzer.detect(_USER)
        assert len(calls) == 3

    def test_advisor_quebrado_falha_aberto(self, monkeypatch):
        import app.purchase.purchase_advisor as advisor_module

        class _BrokenAdvisor:
            def analyze(self, request):
                raise RuntimeError("pipeline indisponível")

        monkeypatch.setattr(advisor_module, "PurchaseAdvisor", _BrokenAdvisor)
        monkeypatch.setattr(
            PostPurchaseAnalyzer, "_fetch_candidates",
            lambda self, uid, today: [_candidate()],
        )
        assert PostPurchaseAnalyzer().detect(_USER) == []
