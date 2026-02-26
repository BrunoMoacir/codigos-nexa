# tests/optimizer/test_card_loader.py
# Testes unitários para CardKnowledgeBase (card_loader.py)
# Passo 2.1 — Funcionalidade 2: Nexa Optimizer

import json
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from app.optimizer.card_loader import CardKnowledgeBase
from app.optimizer.models import CardRecord, CardFlag, CardType


# ─── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_CARD_JSON = json.dumps([
    {
        "card_id": "nubank-roxinho",
        "name": "Nubank Standard",
        "issuer": "Nubank",
        "flag": "MASTERCARD",
        "card_type": "POINTS",
        "public_target": "geral",
        "min_income": 0,
        "requires_proof_of_income": False,
        "secured_card": False,
        "prepaid": False,
        "consigned": False,
        "base_annuity": 0.0,
        "waiver_rules": {"type": "always_free", "description": "Sem anuidade"},
        "cashback_pct": None,
        "cashback_cap": None,
        "cashback_categories": [],
        "points_per_brl": 1.0,
        "points_currency": "pontos",
        "points_conversion_rate": 10.0,
        "benefit_tags": [],
        "benefits_detail": ["Sem anuidade"],
        "revolving_interest_monthly": 0.1599,
        "installment_interest_monthly": None,
        "data_trust_score": 0.95,
        "request_link": "https://nubank.com.br",
        "last_updated": "2026-02-01",
    },
    {
        "card_id": "nubank-ultravioleta",
        "name": "Nubank Ultravioleta",
        "issuer": "Nubank",
        "flag": "MASTERCARD",
        "card_type": "POINTS",
        "public_target": "alta renda",
        "min_income": 200000,
        "requires_proof_of_income": False,
        "secured_card": False,
        "prepaid": False,
        "consigned": False,
        "base_annuity": 2856.00,
        "waiver_rules": {
            "type": "spend_threshold",
            "threshold": 200000,
            "description": "Anuidade isenta gastando R$ 200k/ano",
        },
        "cashback_pct": None,
        "cashback_cap": None,
        "cashback_categories": [],
        "points_per_brl": 2.0,
        "points_currency": "pontos",
        "points_conversion_rate": 16.0,
        "benefit_tags": ["TRAVEL", "LOUNGE", "PREMIUM"],
        "benefits_detail": ["Lounge", "Seguro viagem"],
        "revolving_interest_monthly": 0.1599,
        "installment_interest_monthly": 0.0299,
        "data_trust_score": 0.9,
        "request_link": "https://nubank.com.br/ultravioleta",
        "last_updated": "2026-02-01",
    },
    {
        "card_id": "card-consignado",
        "name": "Cartão Consignado",
        "issuer": "BancoCons",
        "flag": "VISA",
        "card_type": "CASHBACK",
        "public_target": "servidores",
        "min_income": 0,
        "requires_proof_of_income": True,
        "secured_card": False,
        "prepaid": False,
        "consigned": True,
        "base_annuity": 0.0,
        "waiver_rules": {"type": "always_free", "description": "Sem anuidade"},
        "cashback_pct": 0.01,
        "cashback_cap": None,
        "cashback_categories": [],
        "points_per_brl": None,
        "points_currency": "cashback",
        "points_conversion_rate": 0.0,
        "benefit_tags": [],
        "benefits_detail": [],
        "revolving_interest_monthly": 0.05,
        "installment_interest_monthly": None,
        "data_trust_score": 0.7,
        "request_link": None,
        "last_updated": "2026-02-01",
    },
])


@pytest.fixture
def kb(tmp_path: Path) -> CardKnowledgeBase:
    """CardKnowledgeBase apontado para JSON temporário com 3 cartões de amostra."""
    cards_file = tmp_path / "knowledge_cards.json"
    cards_file.write_text(SAMPLE_CARD_JSON, encoding="utf-8")
    return CardKnowledgeBase(cards_path=cards_file)


# ─── Testes de carregamento ─────────────────────────────────────────────────────

class TestLoad:
    def test_loads_all_cards(self, kb: CardKnowledgeBase):
        cards = kb.load()
        assert len(cards) == 3

    def test_returns_card_record_instances(self, kb: CardKnowledgeBase):
        cards = kb.load()
        for c in cards:
            assert isinstance(c, CardRecord)

    def test_card_fields_parsed_correctly(self, kb: CardKnowledgeBase):
        cards = kb.load()
        roxinho = next(c for c in cards if c.card_id == "nubank-roxinho")
        assert roxinho.name == "Nubank Standard"
        assert roxinho.flag == CardFlag.MASTERCARD
        assert roxinho.card_type == CardType.POINTS
        assert roxinho.base_annuity == 0.0
        assert roxinho.min_income == 0

    def test_load_returns_empty_on_missing_file(self, tmp_path: Path):
        kb_missing = CardKnowledgeBase(cards_path=tmp_path / "nao_existe.json")
        assert kb_missing.load() == []

    def test_get_by_id_found(self, kb: CardKnowledgeBase):
        kb.load()
        card = kb.get_by_id("nubank-ultravioleta")
        assert card is not None
        assert card.card_id == "nubank-ultravioleta"

    def test_get_by_id_not_found(self, kb: CardKnowledgeBase):
        kb.load()
        assert kb.get_by_id("cartao-inexistente") is None


# ─── Testes de filtro ──────────────────────────────────────────────────────────

class TestFilterEligible:
    def test_all_cards_eligible_for_high_income(self, kb: CardKnowledgeBase):
        kb.load()
        # R$ 300k anuais → todos os cartões convencionais passam
        eligible = kb.filter_eligible(annual_income=300_000, exclude_consigned=True)
        ids = {c.card_id for c in eligible}
        assert "nubank-roxinho" in ids
        assert "nubank-ultravioleta" in ids
        assert "card-consignado" not in ids  # consignado excluído

    def test_low_income_excludes_ultravioleta(self, kb: CardKnowledgeBase):
        kb.load()
        # R$ 50k anuais → ultravioleta (mín 200k) excluído
        eligible = kb.filter_eligible(annual_income=50_000)
        ids = {c.card_id for c in eligible}
        assert "nubank-ultravioleta" not in ids
        assert "nubank-roxinho" in ids

    def test_excludes_cards_user_already_has(self, kb: CardKnowledgeBase):
        kb.load()
        eligible = kb.filter_eligible(
            annual_income=300_000,
            current_card_ids=["nubank-roxinho"],
        )
        ids = {c.card_id for c in eligible}
        assert "nubank-roxinho" not in ids

    def test_consigned_excluded_by_default(self, kb: CardKnowledgeBase):
        kb.load()
        eligible = kb.filter_eligible(annual_income=100_000)
        ids = {c.card_id for c in eligible}
        assert "card-consignado" not in ids

    def test_consigned_included_when_flag_off(self, kb: CardKnowledgeBase):
        kb.load()
        eligible = kb.filter_eligible(annual_income=100_000, exclude_consigned=False)
        ids = {c.card_id for c in eligible}
        assert "card-consignado" in ids


# ─── Testes de eligibility_score ──────────────────────────────────────────────

class TestEligibilityScore:
    def test_high_income_ratio_gives_high_score(self, kb: CardKnowledgeBase):
        kb.load()
        card = kb.get_by_id("nubank-ultravioleta")
        score, reasons = kb.compute_eligibility_score(
            card=card,
            annual_income=500_000,  # 2.5x o mínimo (200k)
            spending_stability=1.0,
        )
        assert score >= 0.90
        assert any("estimada" in r or "acima" in r for r in reasons)

    def test_exact_income_limit_gives_lower_score(self, kb: CardKnowledgeBase):
        kb.load()
        card = kb.get_by_id("nubank-ultravioleta")
        score, reasons = kb.compute_eligibility_score(
            card=card,
            annual_income=200_000,
            spending_stability=1.0,
        )
        # income_ratio = 1.0 → factor 0.60
        assert score <= 0.65

    def test_existing_issuer_adds_bonus(self, kb: CardKnowledgeBase):
        kb.load()
        card = kb.get_by_id("nubank-roxinho")  # min_income=0, issuer=Nubank

        score_no_rel, _ = kb.compute_eligibility_score(
            card=card,
            annual_income=60_000,
            spending_stability=0.9,
            issuers_in_transactions=set(),
        )
        score_with_rel, reasons = kb.compute_eligibility_score(
            card=card,
            annual_income=60_000,
            spending_stability=0.9,
            issuers_in_transactions={"Nubank"},
        )
        assert score_with_rel > score_no_rel
        assert any("Nubank" in r for r in reasons)

    def test_score_never_exceeds_one(self, kb: CardKnowledgeBase):
        kb.load()
        card = kb.get_by_id("nubank-roxinho")  # min_income=0
        score, _ = kb.compute_eligibility_score(
            card=card,
            annual_income=999_999,
            spending_stability=1.0,
            issuers_in_transactions={"Nubank"},
        )
        assert score <= 1.0

    def test_zero_min_income_gives_max_factor(self, kb: CardKnowledgeBase):
        kb.load()
        card = kb.get_by_id("nubank-roxinho")
        score, _ = kb.compute_eligibility_score(
            card=card,
            annual_income=30_000,
            spending_stability=1.0,
        )
        # income_factor = 1.0 (sem renda mínima) × stability=1.0
        assert score == pytest.approx(1.0, abs=0.15)
