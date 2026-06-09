# tests/optimizer/test_life_events_detector.py
# Testes para LifeEventsDetector e EvidenceScore, incluindo evidência negativa.

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from app.optimizer.detectors.evidence_scorer import (
    EvidenceScore,
    compute_evidence_score,
    compute_negative_evidence,
    missing_signals_from_evidence,
)
from app.optimizer.detectors.life_events_detector import LifeEventsDetector

_MIN_CONFIDENCE = 0.40


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _txns(descriptions: list[str], amounts: list[float], days_ago: list[int]) -> pl.DataFrame:
    today = date.today()
    return pl.DataFrame({
        "description": descriptions,
        "amount": [-abs(a) for a in amounts],
        "date": [today - timedelta(days=d) for d in days_ago],
    })


def _empty() -> pl.DataFrame:
    return pl.DataFrame({"description": [], "amount": [], "date": []}).cast(
        {"amount": pl.Float64, "date": pl.Date}
    )


# ─── compute_negative_evidence ───────────────────────────────────────────────

class TestComputeNegativeEvidence:

    def test_sinal_completamente_isolado(self):
        # 1 txn, 1 merchant, 1 mês → penalidade máxima
        assert compute_negative_evidence(1, 1, 1) == 1.0

    def test_dois_txns_mesmo_merchant(self):
        # 2 txns (1 ponto), 1 merchant, 1 mês → penalidade parcial
        assert compute_negative_evidence(2, 1, 1) == 0.5

    def test_dois_merchants(self):
        # 1 txn, 2 merchants, 1 mês → penalidade parcial
        assert compute_negative_evidence(1, 2, 1) == 0.5

    def test_dois_meses(self):
        # 1 txn, 1 merchant, 2 meses → penalidade parcial
        assert compute_negative_evidence(1, 1, 2) == 0.5

    def test_dois_corroboradores(self):
        # 2 txns + 2 merchants → sem penalidade
        assert compute_negative_evidence(2, 2, 1) == 0.0

    def test_tres_corroboradores(self):
        # Todas as dimensões presentes → sem penalidade
        assert compute_negative_evidence(5, 3, 3) == 0.0

    def test_txn_alto_sem_merchant_diversity(self):
        # Muitas txns mas mesmo merchant e mesmo mês → 1 ponto → 0.5
        assert compute_negative_evidence(10, 1, 1) == 0.5

    def test_retorna_float_entre_0_e_1(self):
        for txn in range(1, 6):
            for merch in range(1, 4):
                for months in range(1, 4):
                    result = compute_negative_evidence(txn, merch, months)
                    assert 0.0 <= result <= 1.0


# ─── compute_evidence_score com penalidade negativa ──────────────────────────

class TestEvidenceScoreNegativePenalty:

    def _score(self, txn=1, merchants=1, months=1, spend=1100.0, hist=0.0,
               threshold=1000.0, quality=0.72,
               isolated_hard_gate=False) -> EvidenceScore:
        return compute_evidence_score(
            recent_spend=spend,
            txn_count=txn,
            merchant_count=merchants,
            months_with_signal=months,
            historical_spend=hist,
            spend_threshold=threshold,
            history_baseline=200.0,
            quality=quality,
            isolated_hard_gate=isolated_hard_gate,
        )

    def test_buffet_isolado_abaixo_do_threshold_sem_hard_gate(self):
        # quality=0.72 < 0.85 → penalty_cap=20%; composite abaixo do threshold
        ev = self._score(txn=1, merchants=1, months=1, spend=1100.0, quality=0.72)
        assert ev.negative_evidence == 1.0
        assert ev.composite < _MIN_CONFIDENCE

    def test_buffet_isolado_com_hard_gate_retorna_zero(self):
        # isolated_hard_gate=True + neg=1.0 → composite=0 independente do valor
        ev = self._score(txn=1, merchants=1, months=1, spend=5000.0, quality=0.55,
                         isolated_hard_gate=True)
        assert ev.negative_evidence == 1.0
        assert ev.composite == 0.0

    def test_hard_gate_nao_bloqueia_quando_ha_corroboracao(self):
        # Hard gate só bloqueia neg==1.0 (totalmente isolado); com 1 corroborador passa
        ev = self._score(txn=2, merchants=1, months=1, spend=1500.0, quality=0.55,
                         isolated_hard_gate=True)
        assert ev.negative_evidence == 0.5
        assert ev.composite > 0.0

    def test_quality_alta_tem_penalidade_menor(self):
        # quality=0.85 → cap=15% vs quality=0.55 → cap=20%, mesmo input
        ev_high = self._score(txn=1, merchants=1, months=1, spend=1100.0, quality=0.85)
        ev_low  = self._score(txn=1, merchants=1, months=1, spend=1100.0, quality=0.55)
        assert ev_high.composite > ev_low.composite

    def test_quality_alta_isolada_passa_threshold(self):
        # PAMPERS/FACULDADE (quality=0.85) em txn única deve passar (penalty_cap=15%)
        ev = self._score(txn=1, merchants=1, months=1, spend=600.0,
                         threshold=300.0, quality=0.85)
        assert ev.composite >= _MIN_CONFIDENCE

    def test_composite_nunca_excede_1(self):
        ev = self._score(txn=10, merchants=5, months=6, spend=50_000.0)
        assert ev.composite <= 1.0

    def test_penalidade_reduz_composite(self):
        ev_isolado    = self._score(txn=1, merchants=1, months=1)
        ev_corroborado = self._score(txn=3, merchants=3, months=2)
        assert ev_isolado.composite < ev_corroborado.composite

    def test_negative_evidence_exposto_em_as_signals_quando_presente(self):
        ev = self._score(txn=1, merchants=1, months=1)
        assert any("ev_negative" in s for s in ev.as_signals())

    def test_negative_evidence_ausente_em_as_signals_quando_zero(self):
        ev = self._score(txn=5, merchants=3, months=3)
        assert not any("ev_negative" in s for s in ev.as_signals())

    def test_penalidade_parcial_com_1_corroborador(self):
        ev = self._score(txn=2, merchants=1, months=1)
        assert ev.negative_evidence == 0.5
        assert ev.composite < self._score(txn=2, merchants=2, months=1).composite


# ─── missing_signals_from_evidence ───────────────────────────────────────────

class TestMissingSignals:

    def test_sinal_isolado_adiciona_missing(self):
        ev = compute_evidence_score(
            recent_spend=1100.0, txn_count=1, merchant_count=1,
            months_with_signal=1, historical_spend=0.0,
            spend_threshold=1000.0, history_baseline=200.0, quality=0.72,
        )
        missing = missing_signals_from_evidence(ev)
        assert "sinal_isolado_sem_corroboracao" in missing

    def test_corroborado_nao_adiciona_missing_isolado(self):
        ev = compute_evidence_score(
            recent_spend=4000.0, txn_count=5, merchant_count=3,
            months_with_signal=2, historical_spend=0.0,
            spend_threshold=1000.0, history_baseline=200.0, quality=0.72,
        )
        missing = missing_signals_from_evidence(ev)
        assert "sinal_isolado_sem_corroboracao" not in missing


# ─── LifeEventsDetector integração com evidência negativa ────────────────────

class TestLifeEventsDetectorNegativeEvidence:

    def _detector(self) -> LifeEventsDetector:
        return LifeEventsDetector()

    # ── Wedding: soft keywords (hard gate) ────────────────────────────────────

    def test_buffet_unico_nao_detecta_casamento(self):
        recent = _txns(["BUFFET DO CARDAPIO"], [1200.0], [10])
        events = self._detector().detect_all(recent, _empty(), 5000.0, 5000.0)
        assert not any(e.event == "wedding" for e in events)

    def test_buffet_alto_valor_nao_detecta_casamento(self):
        # BUFFET sozinho nunca dispara wedding, mesmo com valor muito alto (hard gate)
        recent = _txns(["BUFFET JANTAR CORPORATIVO"], [5000.0], [10])
        events = self._detector().detect_all(recent, _empty(), 5000.0, 5000.0)
        assert not any(e.event == "wedding" for e in events)

    def test_buffet_com_segundo_merchant_detecta_casamento(self):
        # BUFFET + DECORACAO FESTA = 2 merchants → 1 corroborador → hard gate não aplica
        recent = _txns(["BUFFET DO CARDAPIO", "DECORACAO FESTA EVENTOS"],
                       [1500.0, 800.0], [10, 5])
        events = self._detector().detect_all(recent, _empty(), 5000.0, 5000.0)
        assert any(e.event == "wedding" for e in events)

    # ── Wedding: anchor keywords (pode detectar isolado) ──────────────────────

    def test_cerimonial_isolado_detecta_casamento(self):
        # CERIMONIAL é keyword âncora (quality=0.90) — detecta com confiança média
        recent = _txns(["CERIMONIAL EVENTOS"], [3000.0], [10])
        events = self._detector().detect_all(recent, _empty(), 5000.0, 5000.0)
        wedding = next((e for e in events if e.event == "wedding"), None)
        assert wedding is not None
        assert wedding.confidence >= _MIN_CONFIDENCE
        assert "wedding_anchor=sim" in wedding.supporting_signals

    def test_noivas_isolado_detecta_casamento(self):
        # NOIVAS é keyword âncora
        recent = _txns(["LOJA NOIVAS ESPECIAL"], [2000.0], [10])
        events = self._detector().detect_all(recent, _empty(), 5000.0, 5000.0)
        assert any(e.event == "wedding" for e in events)

    def test_cerimonial_mais_buffet_mais_fotografo_detecta_casamento(self):
        # Multi-sinal com âncora → alta confiança
        recent = _txns(
            ["CERIMONIAL EVENTOS", "BUFFET DO CARDAPIO", "FOTOGRAFO CASAMENTO"],
            [2000.0, 1500.0, 1200.0],
            [45, 20, 5],
        )
        events = self._detector().detect_all(recent, _empty(), 5000.0, 5000.0)
        wedding = next((e for e in events if e.event == "wedding"), None)
        assert wedding is not None
        assert wedding.confidence >= _MIN_CONFIDENCE

    def test_wedding_anchor_registrado_em_supporting_signals(self):
        # Quando anchor detectado, supporting_signals deve indicar wedding_anchor=sim
        recent = _txns(["CERIMONIAL EVENTOS", "DECORACAO FESTA"], [2000.0, 800.0], [10, 5])
        events = self._detector().detect_all(recent, _empty(), 5000.0, 5000.0)
        wedding = next((e for e in events if e.event == "wedding"), None)
        assert wedding is not None
        assert "wedding_anchor=sim" in wedding.supporting_signals

    def test_buffet_sem_anchor_registrado_em_supporting_signals(self):
        # Dois gastos com soft keywords devem indicar wedding_anchor=nao
        recent = _txns(["BUFFET EVENTOS", "DECORACAO FESTA JARDIM"], [1500.0, 800.0], [10, 5])
        events = self._detector().detect_all(recent, _empty(), 5000.0, 5000.0)
        wedding = next((e for e in events if e.event == "wedding"), None)
        assert wedding is not None
        assert "wedding_anchor=nao" in wedding.supporting_signals

    # ── Baby: keyword específica detecta isolada ──────────────────────────────

    def test_fralda_unica_abaixo_spend_gate_nao_detecta(self):
        # R$80 < spend_gate=200 → rejeitado no gate, não por negative evidence
        recent = _txns(["FRALDA PAMPERS"], [80.0], [5])
        events = self._detector().detect_all(recent, _empty(), 3000.0, 3000.0)
        assert not any(e.event == "new_baby" for e in events)

    def test_multiplas_compras_bebe_detecta_evento(self):
        recent = _txns(
            ["FRALDA PAMPERS", "HUGGIES BEBE", "JOHNSON BABY SHAMPOO", "CHICCO BABYFOOD"],
            [120.0, 90.0, 60.0, 80.0],
            [50, 30, 15, 3],
        )
        events = self._detector().detect_all(recent, _empty(), 3000.0, 3000.0)
        baby = next((e for e in events if e.event == "new_baby"), None)
        assert baby is not None
        assert baby.confidence >= _MIN_CONFIDENCE

    # ── Missing signals ───────────────────────────────────────────────────────

    def test_sinal_isolado_registrado_em_missing_signals(self):
        # CERIMONIAL × 2 no mesmo mês → neg=0.5 → "sinal_isolado_sem_corroboracao"
        recent = _txns(
            ["CERIMONIAL EVENTOS", "CERIMONIAL EVENTOS"],
            [3000.0, 2000.0],
            [3, 5],  # ambos em junho
        )
        events = self._detector().detect_all(recent, _empty(), 5000.0, 5000.0)
        wedding = next((e for e in events if e.event == "wedding"), None)
        assert wedding is not None
        assert "sinal_isolado_sem_corroboracao" in wedding.missing_signals
