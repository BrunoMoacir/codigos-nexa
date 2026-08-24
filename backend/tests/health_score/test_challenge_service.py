"""
Testes do ChallengeService (R2.b) — geração, progresso e fechamento.

Sem banco: os makers e _update_progress recebem listas de transações
sintéticas; persistência e score são monkeypatchados.
"""

from datetime import date, datetime, timezone

import pytest

from app.health_score.challenge_service import Challenge, ChallengeService

_svc = ChallengeService()
_USER = "user_test"
_MONTH = "2026-07"
_TODAY = date(2026, 7, 15)


def _tx(d: date, amount: float, description: str = "", category: str = "") -> dict:
    return {"date": d, "amount": amount, "description": description, "category": category}


def _fee_txns() -> list[dict]:
    """Tarifas nos 3 meses anteriores a julho/2026."""
    return [
        _tx(date(2026, 4, 10), -29.9, "TARIFA MANUTENCAO CONTA"),
        _tx(date(2026, 5, 10), -29.9, "TARIFA MANUTENCAO CONTA"),
        _tx(date(2026, 6, 10), -29.9, "TARIFA MANUTENCAO CONTA"),
    ]


# ── Geração ──────────────────────────────────────────────────────────

class TestMakers:
    def test_sem_tarifas_elegivel_quando_pagou_tarifa(self):
        ch = _svc._make_sem_tarifas(_USER, _MONTH, _TODAY, _fee_txns())
        assert ch is not None
        assert ch.challenge_type == "SEM_TARIFAS"
        assert ch.metadata["baseline_fees_3m_brl"] == pytest.approx(89.7)
        assert ch.status == "ACTIVE"

    def test_sem_tarifas_inelegivel_sem_historico_de_tarifa(self):
        txns = [_tx(date(2026, 5, 10), -80.0, "RESTAURANTE X")]
        assert _svc._make_sem_tarifas(_USER, _MONTH, _TODAY, txns) is None

    def test_reduzir_categoria_pega_top_discricionaria(self):
        txns = [
            # 3 meses de delivery pesado (discricionário)
            _tx(date(2026, 4, 5), -400.0, "IFOOD", "Delivery"),
            _tx(date(2026, 5, 5), -500.0, "IFOOD", "Delivery"),
            _tx(date(2026, 6, 5), -600.0, "IFOOD", "Delivery"),
            # aluguel maior, mas não-discricionário → ignorado
            _tx(date(2026, 5, 1), -2000.0, "ALUGUEL", "Moradia"),
        ]
        ch = _svc._make_reduzir_categoria(_USER, _MONTH, _TODAY, txns)
        assert ch is not None
        assert ch.metadata["category"] == "Delivery"
        # média 500/mês → alvo 85% = 425
        assert ch.target_value == pytest.approx(425.0)

    def test_reduzir_categoria_ignora_gasto_baixo(self):
        txns = [_tx(date(2026, 5, 5), -100.0, "CINEMA", "Lazer")]
        assert _svc._make_reduzir_categoria(_USER, _MONTH, _TODAY, txns) is None

    def test_guardar_valor_usa_mediana_da_renda(self):
        txns = [
            _tx(date(2026, 4, 1), 5000.0, "SALARIO"),
            _tx(date(2026, 5, 1), 5000.0, "SALARIO"),
            _tx(date(2026, 6, 1), 7000.0, "SALARIO + BONUS"),
        ]
        ch = _svc._make_guardar_valor(_USER, _MONTH, _TODAY, txns)
        assert ch is not None
        assert ch.target_value == pytest.approx(500.0)   # 10% da mediana 5000

    def test_guardar_valor_precisa_de_2_meses_de_renda(self):
        txns = [_tx(date(2026, 6, 1), 5000.0, "SALARIO")]
        assert _svc._make_guardar_valor(_USER, _MONTH, _TODAY, txns) is None

    def test_subir_score_usa_baseline(self, monkeypatch):
        monkeypatch.setattr(ChallengeService, "_latest_score", staticmethod(lambda uid: 62))
        ch = _svc._make_subir_score(_USER, _MONTH, _TODAY, [])
        assert ch is not None
        assert ch.target_value == 65.0
        assert ch.metadata["baseline_score"] == 62

    def test_subir_score_inelegivel_sem_historico(self, monkeypatch):
        monkeypatch.setattr(ChallengeService, "_latest_score", staticmethod(lambda uid: None))
        assert _svc._make_subir_score(_USER, _MONTH, _TODAY, []) is None

    def test_subir_score_inelegivel_com_score_100(self, monkeypatch):
        monkeypatch.setattr(ChallengeService, "_latest_score", staticmethod(lambda uid: 100))
        assert _svc._make_subir_score(_USER, _MONTH, _TODAY, []) is None


# ── Progresso ────────────────────────────────────────────────────────

def _challenge(ctype: str, target: float, metadata: dict | None = None) -> Challenge:
    return Challenge(
        id="c1", user_id=_USER, challenge_type=ctype, month=_MONTH,
        title="t", target_label="l", target_value=target,
        progress_value=0.0, pct_progress=0.0, status="ACTIVE",
        metadata=metadata or {},
    )


class TestProgresso:
    _start, _end = date(2026, 7, 1), date(2026, 7, 31)

    def test_sem_tarifas_falha_na_primeira_tarifa(self):
        ch = _challenge("SEM_TARIFAS", 0.0)
        txns = [_tx(date(2026, 7, 10), -29.9, "TARIFA MANUTENCAO CONTA")]
        _svc._update_progress(ch, txns, self._start, _TODAY, 48.4, closing=False)
        assert ch.status == "FAILED"

    def test_sem_tarifas_progride_com_o_mes(self):
        ch = _challenge("SEM_TARIFAS", 0.0)
        _svc._update_progress(ch, [], self._start, _TODAY, 48.4, closing=False)
        assert ch.status == "ACTIVE"
        assert ch.pct_progress == pytest.approx(48.4)

    def test_sem_tarifas_completa_no_fechamento(self):
        """
        Conta ATIVA e sem tarifas no mês — a vitória de verdade.

        A versão anterior deste teste passava lista VAZIA de transações e
        afirmava COMPLETED, que era exatamente o defeito: sem dado,
        `_detect_fees` devolve lista vazia, `total = 0` e o desafio fechava
        como vitória. Quem desconectasse o banco ganhava. Ver
        `test_sem_dado_na_janela_nao_e_vitoria`.
        """
        ch = _challenge("SEM_TARIFAS", 0.0)
        txns = [
            _tx(date(2026, 7, 5), 5_000.0, "SALARIO EMPRESA"),
            _tx(date(2026, 7, 12), -320.0, "SUPERMERCADO", "Mercado"),
            _tx(date(2026, 7, 20), -89.9, "IFOOD", "Delivery"),
        ]
        _svc._update_progress(ch, txns, self._start, self._end, 100.0, closing=True)
        assert ch.status == "COMPLETED"
        assert ch.pct_progress == 100.0
        assert ch.completed_at is not None

    @pytest.mark.parametrize("ctype,meta", [
        ("SEM_TARIFAS", None),
        ("REDUZIR_CATEGORIA", {"category": "Delivery"}),
        ("GUARDAR_VALOR", None),
        ("SUBIR_SCORE", {"baseline": 50}),
    ])
    def test_sem_dado_na_janela_nao_e_vitoria(self, ctype, meta):
        """
        Fechamento sem NENHUMA transação: nem COMPLETED nem FAILED.

        Os desafios que mediam AUSÊNCIA de coisa ruim (SEM_TARIFAS,
        REDUZIR_CATEGORIA) completavam com dado faltando — dois dos quatro do
        mês entregues a quem desconectou o banco, e badge é a moeda de
        retenção da feature. Os que mediam PRESENÇA de coisa boa falhavam,
        punindo por algo fora do controle do usuário.
        """
        ch = _challenge(ctype, 100.0, meta)
        _svc._update_progress(ch, [], self._start, self._end, 100.0, closing=True)
        assert ch.status == "SEM_DADOS"
        assert ch.completed_at is None

    def test_sem_dados_nao_gera_card_de_conclusao(self):
        """
        `SEM_DADOS` não pode virar recompensa: o notifier só emite card para
        COMPLETED (e progresso para ACTIVE).
        """
        ch = _challenge("SEM_TARIFAS", 0.0)
        _svc._update_progress(ch, [], self._start, self._end, 100.0, closing=True)
        assert ch.status not in ("COMPLETED", "ACTIVE")

    def test_reduzir_categoria_falha_ao_estourar_teto(self):
        ch = _challenge("REDUZIR_CATEGORIA", 425.0, {"category": "Delivery"})
        txns = [_tx(date(2026, 7, 8), -500.0, "IFOOD", "Delivery")]
        _svc._update_progress(ch, txns, self._start, _TODAY, 48.4, closing=False)
        assert ch.status == "FAILED"

    def test_reduzir_categoria_completa_dentro_do_teto(self):
        ch = _challenge("REDUZIR_CATEGORIA", 425.0, {"category": "Delivery"})
        txns = [_tx(date(2026, 7, 8), -300.0, "IFOOD", "Delivery")]
        _svc._update_progress(ch, txns, self._start, self._end, 100.0, closing=True)
        assert ch.status == "COMPLETED"
        assert ch.progress_value == pytest.approx(300.0)

    def test_guardar_valor_completa_ao_atingir_alvo_mesmo_no_meio_do_mes(self):
        ch = _challenge("GUARDAR_VALOR", 500.0)
        txns = [
            _tx(date(2026, 7, 1), 5000.0, "SALARIO"),
            _tx(date(2026, 7, 10), -4400.0, "GASTOS", "Outros"),
        ]
        _svc._update_progress(ch, txns, self._start, _TODAY, 48.4, closing=False)
        assert ch.status == "COMPLETED"
        assert ch.progress_value == pytest.approx(600.0)

    def test_guardar_valor_progresso_parcial(self):
        ch = _challenge("GUARDAR_VALOR", 500.0)
        txns = [
            _tx(date(2026, 7, 1), 5000.0, "SALARIO"),
            _tx(date(2026, 7, 10), -4750.0, "GASTOS", "Outros"),
        ]
        _svc._update_progress(ch, txns, self._start, _TODAY, 48.4, closing=False)
        assert ch.status == "ACTIVE"
        assert ch.pct_progress == pytest.approx(50.0)

    def test_guardar_valor_falha_no_fechamento_sem_atingir(self):
        ch = _challenge("GUARDAR_VALOR", 500.0)
        txns = [_tx(date(2026, 7, 1), 100.0, "PIX RECEBIDO")]
        _svc._update_progress(ch, txns, self._start, self._end, 100.0, closing=True)
        assert ch.status == "FAILED"

    def test_subir_score_completa_ao_atingir(self, monkeypatch):
        monkeypatch.setattr(ChallengeService, "_latest_score", staticmethod(lambda uid: 66))
        ch = _challenge("SUBIR_SCORE", 65.0, {"baseline_score": 62})
        _svc._update_progress(ch, [], self._start, _TODAY, 48.4, closing=False)
        assert ch.status == "COMPLETED"

    def test_subir_score_progresso_proporcional(self, monkeypatch):
        monkeypatch.setattr(ChallengeService, "_latest_score", staticmethod(lambda uid: 64))
        ch = _challenge("SUBIR_SCORE", 65.0, {"baseline_score": 62})
        _svc._update_progress(ch, [], self._start, _TODAY, 48.4, closing=False)
        assert ch.status == "ACTIVE"
        assert ch.pct_progress == pytest.approx(66.7, abs=0.1)


# ── Streak de badges ─────────────────────────────────────────────────

class TestStreak:
    def test_tres_meses_consecutivos(self):
        assert ChallengeService._has_streak(["2026-05", "2026-06", "2026-07"], 3) is True

    def test_meses_com_buraco_nao_contam(self):
        assert ChallengeService._has_streak(["2026-04", "2026-06", "2026-07"], 3) is False

    def test_virada_de_ano(self):
        assert ChallengeService._has_streak(["2025-11", "2025-12", "2026-01"], 3) is True

    def test_menos_meses_que_o_necessario(self):
        assert ChallengeService._has_streak(["2026-07"], 3) is False


# ── Feed inputs ──────────────────────────────────────────────────────

class TestFeedInputs:
    def test_mapeia_completed_e_active_quente(self, monkeypatch):
        completed = _challenge("SEM_TARIFAS", 0.0)
        completed.status = "COMPLETED"
        completed.pct_progress = 100.0
        quase = _challenge("GUARDAR_VALOR", 500.0)
        quase.pct_progress = 80.0
        falhou = _challenge("SUBIR_SCORE", 65.0)
        falhou.status = "FAILED"

        monkeypatch.setattr(
            ChallengeService, "sync", lambda self, uid, today=None: [completed, quase, falhou]
        )
        monkeypatch.setattr(
            ChallengeService, "_load", lambda self, uid, month: []
        )
        inputs = _svc.get_feed_inputs(_USER, today=_TODAY)

        by_type = {i.challenge_type: i for i in inputs}
        assert by_type["SEM_TARIFAS"].status == "COMPLETED"
        assert by_type["GUARDAR_VALOR"].pct_progress == 80.0
        assert "SUBIR_SCORE" not in by_type   # FAILED não vai para o feed

    def test_inclui_fechamento_recente_do_mes_anterior(self, monkeypatch):
        fechado = _challenge("SEM_TARIFAS", 0.0)
        fechado.month = "2026-06"
        fechado.status = "COMPLETED"
        fechado.completed_at = datetime.now(timezone.utc)

        monkeypatch.setattr(ChallengeService, "sync", lambda self, uid, today=None: [])
        monkeypatch.setattr(
            ChallengeService, "_load",
            lambda self, uid, month: [fechado] if month == "2026-06" else [],
        )
        inputs = _svc.get_feed_inputs(_USER, today=_TODAY)
        assert len(inputs) == 1
        assert inputs[0].month == "2026-06"
