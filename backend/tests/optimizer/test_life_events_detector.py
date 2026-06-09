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
               threshold=1000.0, quality=0.72) -> EvidenceScore:
        return compute_evidence_score(
            recent_spend=spend,
            txn_count=txn,
            merchant_count=merchants,
            months_with_signal=months,
            historical_spend=hist,
            spend_threshold=threshold,
            history_baseline=200.0,
            quality=quality,
        )

    def test_buffet_isolado_abaixo_do_threshold_de_confianca(self):
        # BUFFET único em merchant único não deve passar o gate de 0.40
        ev = self._score(txn=1, merchants=1, months=1, spend=1100.0)
        assert ev.negative_evidence == 1.0
        assert ev.composite < _MIN_CONFIDENCE

    def test_buffet_mais_decoracao_mais_fotografo_passa(self):
        # Três merchants distintos + 2 meses → neg=0.0, composite alto
        ev = self._score(txn=5, merchants=3, months=2, spend=4000.0)
        assert ev.negative_evidence == 0.0
        assert ev.composite >= _MIN_CONFIDENCE

    def test_penalidade_reduz_composite(self):
        # Mesmo input, negative_evidence=1.0 deve dar composite menor que sem penalidade
        ev_isolado = self._score(txn=1, merchants=1, months=1)
        ev_corroborado = self._score(txn=3, merchants=3, months=2)
        assert ev_isolado.composite < ev_corroborado.composite

    def test_composite_nunca_excede_1(self):
        ev = self._score(txn=10, merchants=5, months=6, spend=50_000.0)
        assert ev.composite <= 1.0

    def test_negative_evidence_exposto_em_as_signals_quando_presente(self):
        ev = self._score(txn=1, merchants=1, months=1)
        signals = ev.as_signals()
        assert any("ev_negative" in s for s in signals)

    def test_negative_evidence_ausente_em_as_signals_quando_zero(self):
        ev = self._score(txn=5, merchants=3, months=3)
        signals = ev.as_signals()
        assert not any("ev_negative" in s for s in signals)

    def test_penalidade_parcial_com_1_corroborador(self):
        # 2 txns = 1 corroborador → neg=0.5 → penalidade de 15%
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

    def test_buffet_unico_nao_detecta_casamento(self):
        # Um único gasto em BUFFET não deve gerar evento de casamento
        recent = _txns(["BUFFET DO CARDAPIO"], [1200.0], [10])
        history = _empty()
        events = self._detector().detect_all(recent, history, 5000.0, 5000.0)
        wedding_events = [e for e in events if e.event == "wedding"]
        assert len(wedding_events) == 0

    def test_cerimonial_mais_buffet_mais_fotografo_detecta_casamento(self):
        # Três merchants distintos em 2 meses devem detectar casamento
        recent = _txns(
            ["CERIMONIAL EVENTOS", "BUFFET DO CARDAPIO", "FOTOGRAFO CASAMENTO"],
            [2000.0, 1500.0, 1200.0],
            [45, 20, 5],
        )
        history = _empty()
        events = self._detector().detect_all(recent, history, 5000.0, 5000.0)
        wedding_events = [e for e in events if e.event == "wedding"]
        assert len(wedding_events) == 1
        assert wedding_events[0].confidence >= _MIN_CONFIDENCE

    def test_fralda_unica_nao_detecta_bebe(self):
        # Uma única compra de fralda não deve disparar new_baby
        recent = _txns(["FRALDA PAMPERS"], [80.0], [5])
        history = _empty()
        events = self._detector().detect_all(recent, history, 3000.0, 3000.0)
        baby_events = [e for e in events if e.event == "new_baby"]
        assert len(baby_events) == 0

    def test_multiplas_compras_bebe_detecta_evento(self):
        # Várias compras de produtos de bebê em merchants distintos
        recent = _txns(
            ["FRALDA PAMPERS", "HUGGIES BEBE", "JOHNSON BABY SHAMPOO", "CHICCO BABYFOOD"],
            [120.0, 90.0, 60.0, 80.0],
            [50, 30, 15, 3],
        )
        history = _empty()
        events = self._detector().detect_all(recent, history, 3000.0, 3000.0)
        baby_events = [e for e in events if e.event == "new_baby"]
        assert len(baby_events) == 1
        assert baby_events[0].confidence >= _MIN_CONFIDENCE

    def test_sinal_isolado_registrado_em_missing_signals(self):
        # 2 txns no mesmo merchant, mesmo mês (ambos em junho) → 1 corroborador → neg=0.5
        # composite ainda passa o threshold mas missing_signals deve registrar o aviso
        recent = _txns(
            ["CERIMONIAL EVENTOS", "CERIMONIAL EVENTOS"],
            [3000.0, 2000.0],
            [3, 5],  # ambos em junho: neg=0.5 (2 txns, 1 merchant, 1 mês)
        )
        history = _empty()
        events = self._detector().detect_all(recent, history, 5000.0, 5000.0)
        wedding_events = [e for e in events if e.event == "wedding"]
        assert len(wedding_events) == 1
        assert "sinal_isolado_sem_corroboracao" in wedding_events[0].missing_signals
