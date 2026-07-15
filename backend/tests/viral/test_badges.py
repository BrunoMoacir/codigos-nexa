"""
tests/viral/test_badges.py — BadgeService (incluindo badges V2)

COMO RODAR:
    cd backend
    pytest tests/viral/test_badges.py -v
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.health_score.badge_service import Badge, BadgeService


@pytest.fixture
def svc() -> BadgeService:
    return BadgeService()


def _history(scores: list[int]) -> list[dict]:
    return [{"health_score": s, "date": f"2026-0{i+1}-01"} for i, s in enumerate(scores)]


def _no_badges(user_id: str) -> set[str]:
    return set()


def _mock_db(side_effect=None, fetchone=None, fetchall=None):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    if fetchone is not None:
        ctx.execute.return_value.fetchone.return_value = fetchone
    if fetchall is not None:
        ctx.execute.return_value.fetchall.return_value = fetchall
    return ctx


class TestBadgesExistentes:
    def test_primeiro_insight_na_primeira_execucao(self, svc):
        with patch.object(svc.__class__, "_get_existing_badges", return_value=set()):
            with patch.object(svc.__class__, "_has_negotiations", return_value=False):
                with patch.object(svc.__class__, "_total_potential_gain", return_value=0.0):
                    with patch.object(svc.__class__, "_has_defense_finding", return_value=False):
                        with patch.object(svc.__class__, "_has_portability_case", return_value=False):
                            with patch.object(svc.__class__, "_has_viral_share", return_value=False):
                                with patch.object(svc.__class__, "_persist_badges", return_value=None):
                                    badges = svc.evaluate_badges("u1", 60, _history([60]))

        types = [b.badge_type for b in badges]
        assert "PRIMEIRO_INSIGHT" in types

    def test_sem_repetir_badges_existentes(self, svc):
        existing = {"PRIMEIRO_INSIGHT", "3_MESES_VERDE", "NEGOCIADOR"}
        with patch.object(svc.__class__, "_get_existing_badges", return_value=existing):
            with patch.object(svc.__class__, "_has_negotiations", return_value=True):
                with patch.object(svc.__class__, "_total_potential_gain", return_value=50.0):
                    with patch.object(svc.__class__, "_has_defense_finding", return_value=False):
                        with patch.object(svc.__class__, "_has_portability_case", return_value=False):
                            with patch.object(svc.__class__, "_has_viral_share", return_value=False):
                                with patch.object(svc.__class__, "_persist_badges", return_value=None):
                                    badges = svc.evaluate_badges("u1", 75, _history([75, 75, 75]))

        types = [b.badge_type for b in badges]
        assert "PRIMEIRO_INSIGHT" not in types
        assert "3_MESES_VERDE" not in types
        assert "NEGOCIADOR" not in types


class TestBadgesNovos:
    def _full_patch(self, svc, current_score=60, history=None, existing=None,
                    has_neg=False, gain=0.0, has_def=False, has_port=False, has_share=False):
        if history is None:
            history = _history([current_score])
        if existing is None:
            existing = set()
        with (
            patch.object(svc.__class__, "_get_existing_badges", return_value=existing),
            patch.object(svc.__class__, "_has_negotiations", return_value=has_neg),
            patch.object(svc.__class__, "_total_potential_gain", return_value=gain),
            patch.object(svc.__class__, "_has_defense_finding", return_value=has_def),
            patch.object(svc.__class__, "_has_portability_case", return_value=has_port),
            patch.object(svc.__class__, "_has_viral_share", return_value=has_share),
            patch.object(svc.__class__, "_persist_badges", return_value=None),
        ):
            return svc.evaluate_badges("u1", current_score, history)

    def test_economizou_5000(self, svc):
        badges = self._full_patch(svc, gain=5000.0)
        types = [b.badge_type for b in badges]
        assert "ECONOMIZOU_5000" in types

    def test_economizou_5000_nao_aparece_abaixo(self, svc):
        badges = self._full_patch(svc, gain=4999.99)
        types = [b.badge_type for b in badges]
        assert "ECONOMIZOU_5000" not in types

    def test_score_record_com_score_90(self, svc):
        badges = self._full_patch(svc, current_score=90)
        types = [b.badge_type for b in badges]
        assert "SCORE_RECORD" in types

    def test_score_record_nao_aparece_com_89(self, svc):
        badges = self._full_patch(svc, current_score=89)
        types = [b.badge_type for b in badges]
        assert "SCORE_RECORD" not in types

    def test_defensor_com_finding_confirmado(self, svc):
        badges = self._full_patch(svc, has_def=True)
        types = [b.badge_type for b in badges]
        assert "DEFENSOR" in types

    def test_defensor_sem_finding(self, svc):
        badges = self._full_patch(svc, has_def=False)
        types = [b.badge_type for b in badges]
        assert "DEFENSOR" not in types

    def test_portabilidade_com_caso_submetido(self, svc):
        badges = self._full_patch(svc, has_port=True)
        types = [b.badge_type for b in badges]
        assert "PORTABILIDADE" in types

    def test_viral_share_com_compartilhamento(self, svc):
        badges = self._full_patch(svc, has_share=True)
        types = [b.badge_type for b in badges]
        assert "VIRAL_SHARE" in types

    def test_viral_share_sem_compartilhamento(self, svc):
        badges = self._full_patch(svc, has_share=False)
        types = [b.badge_type for b in badges]
        assert "VIRAL_SHARE" not in types

    def test_db_offline_nao_propaga_excecao(self, svc):
        with patch("app.core.database.SessionLocal", side_effect=Exception("offline")):
            badges = svc.evaluate_badges("u1", 60, _history([60]))
        assert isinstance(badges, list)


class TestConsecutivoVerde:
    def test_3_meses_consecutivos(self, svc):
        assert svc._consecutive_verde(_history([70, 70, 70]), 3) is True

    def test_2_de_3_nao_e_suficiente(self, svc):
        assert svc._consecutive_verde(_history([60, 70, 70]), 3) is False

    def test_6_meses_ok(self, svc):
        assert svc._consecutive_verde(_history([70] * 6), 6) is True

    def test_interrompido_no_quarto_mes(self, svc):
        assert svc._consecutive_verde(_history([70, 70, 70, 65, 70, 70]), 6) is False

    def test_lista_menor_que_minimo_retorna_false(self, svc):
        assert svc._consecutive_verde(_history([70, 70]), 3) is False
