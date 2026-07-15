"""
app/health_score/badge_service.py — BadgeService (MX.1 gamificação)

Avalia e persiste badges de gamificação na tabela user_badges.
Chamado após o cálculo do health score (router ou job).
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_VERDE_THRESHOLD = 70


@dataclass
class Badge:
    badge_type: str
    earned_at: datetime
    metadata: dict[str, Any] | None = None


class BadgeService:
    """
    Avalia badges conquistados a cada ciclo de health score.
    Retorna apenas badges recém conquistados (novos desde o último ciclo).

    Badge types suportados:
      PRIMEIRO_INSIGHT   — primeiro snapshot de score persistido
      3_MESES_VERDE      — score >= 70 por 3 meses consecutivos
      6_MESES_VERDE      — score >= 70 por 6 meses consecutivos
      NEGOCIADOR         — ao menos 1 negociação em negotiation_history
      ECONOMIZOU_100     — potencial de economia acumulado >= R$ 100
      ECONOMIZOU_500     — potencial de economia acumulado >= R$ 500
      ECONOMIZOU_1000    — potencial de economia acumulado >= R$ 1.000
      ECONOMIZOU_5000    — potencial de economia acumulado >= R$ 5.000
      DEFENSOR           — ao menos 1 finding de defesa confirmado
      PORTABILIDADE      — ao menos 1 caso de portabilidade submetido
      VIRAL_SHARE        — ao menos 1 compartilhamento em viral_share_log
      SCORE_RECORD       — health score atingiu 90 ou mais em qualquer momento
    """

    def evaluate_badges(
        self,
        user_id: str,
        current_score: int,
        history: list[dict],
    ) -> list[Badge]:
        """
        Avalia e persiste badges novos. Idempotente — ON CONFLICT DO NOTHING.

        Args:
            user_id:       ID do usuário.
            current_score: Score calculado neste ciclo.
            history:       health_score_history ordenado ASC (chaves: date, health_score).

        Returns:
            Badges recém conquistados (vazio se nenhum novo).
        """
        existing = self._get_existing_badges(user_id)
        now = datetime.now(timezone.utc)
        candidates: list[Badge] = []

        # 1. Primeiro snapshot
        if "PRIMEIRO_INSIGHT" not in existing and len(history) >= 1:
            candidates.append(Badge(badge_type="PRIMEIRO_INSIGHT", earned_at=now))

        # 2. Score verde por N meses consecutivos
        if "3_MESES_VERDE" not in existing and self._consecutive_verde(history, 3):
            candidates.append(Badge(badge_type="3_MESES_VERDE", earned_at=now))

        if "6_MESES_VERDE" not in existing and self._consecutive_verde(history, 6):
            candidates.append(Badge(badge_type="6_MESES_VERDE", earned_at=now))

        # 3. Ao menos uma negociação gerada
        if "NEGOCIADOR" not in existing and self._has_negotiations(user_id):
            candidates.append(Badge(badge_type="NEGOCIADOR", earned_at=now))

        # 4. Marcos de economia (soma de potential_gain)
        total_gain = self._total_potential_gain(user_id)
        for threshold, badge_type in [
            (5000.0, "ECONOMIZOU_5000"),
            (1000.0, "ECONOMIZOU_1000"),
            (500.0, "ECONOMIZOU_500"),
            (100.0, "ECONOMIZOU_100"),
        ]:
            if badge_type not in existing and total_gain >= threshold:
                candidates.append(Badge(
                    badge_type=badge_type,
                    earned_at=now,
                    metadata={"total_gain_brl": round(total_gain, 2)},
                ))

        # 5. Score recorde >= 90
        if "SCORE_RECORD" not in existing and current_score >= 90:
            candidates.append(Badge(
                badge_type="SCORE_RECORD",
                earned_at=now,
                metadata={"score": current_score},
            ))

        # 6. Defensor — ao menos 1 finding de defesa confirmado
        if "DEFENSOR" not in existing and self._has_defense_finding(user_id):
            candidates.append(Badge(badge_type="DEFENSOR", earned_at=now))

        # 7. Portabilidade — caso submetido
        if "PORTABILIDADE" not in existing and self._has_portability_case(user_id):
            candidates.append(Badge(badge_type="PORTABILIDADE", earned_at=now))

        # 8. Viral share — ao menos 1 compartilhamento registrado
        if "VIRAL_SHARE" not in existing and self._has_viral_share(user_id):
            candidates.append(Badge(badge_type="VIRAL_SHARE", earned_at=now))

        if candidates:
            self._persist_badges(user_id, candidates)

        return candidates

    # ── Helpers privados ──────────────────────────────────────────────

    @staticmethod
    def _get_existing_badges(user_id: str) -> set[str]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text("SELECT badge_type FROM user_badges WHERE user_id = :uid"),
                    {"uid": user_id},
                ).fetchall()
            return {r[0] for r in rows}
        except Exception as exc:
            logger.warning("[BadgeService] _get_existing_badges user=%s: %s", user_id, exc)
            return set()

    @staticmethod
    def _consecutive_verde(history: list[dict], months: int) -> bool:
        if len(history) < months:
            return False
        return all(h["health_score"] >= _VERDE_THRESHOLD for h in history[-months:])

    @staticmethod
    def _has_negotiations(user_id: str) -> bool:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                row = db.execute(
                    text("SELECT 1 FROM negotiation_history WHERE user_id = :uid LIMIT 1"),
                    {"uid": user_id},
                ).fetchone()
            return row is not None
        except Exception as exc:
            logger.warning("[BadgeService] _has_negotiations user=%s: %s", user_id, exc)
            return False

    @staticmethod
    def _total_potential_gain(user_id: str) -> float:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                row = db.execute(
                    text(
                        "SELECT COALESCE(SUM(potential_gain), 0)"
                        " FROM negotiation_history WHERE user_id = :uid"
                    ),
                    {"uid": user_id},
                ).fetchone()
            return float(row[0]) if row else 0.0
        except Exception as exc:
            logger.warning("[BadgeService] _total_potential_gain user=%s: %s", user_id, exc)
            return 0.0

    @staticmethod
    def _has_defense_finding(user_id: str) -> bool:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                row = db.execute(
                    text(
                        "SELECT 1 FROM defense_findings "
                        "WHERE user_id = :uid AND status = 'confirmed' LIMIT 1"
                    ),
                    {"uid": user_id},
                ).fetchone()
            return row is not None
        except Exception as exc:
            logger.warning("[BadgeService] _has_defense_finding user=%s: %s", user_id, exc)
            return False

    @staticmethod
    def _has_portability_case(user_id: str) -> bool:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                row = db.execute(
                    text(
                        "SELECT 1 FROM portability_cases "
                        "WHERE user_id = :uid AND status = 'submitted' LIMIT 1"
                    ),
                    {"uid": user_id},
                ).fetchone()
            return row is not None
        except Exception as exc:
            logger.warning("[BadgeService] _has_portability_case user=%s: %s", user_id, exc)
            return False

    @staticmethod
    def _has_viral_share(user_id: str) -> bool:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                row = db.execute(
                    text(
                        "SELECT 1 FROM viral_share_log "
                        "WHERE user_id = :uid AND revoked_at IS NULL LIMIT 1"
                    ),
                    {"uid": user_id},
                ).fetchone()
            return row is not None
        except Exception as exc:
            logger.warning("[BadgeService] _has_viral_share user=%s: %s", user_id, exc)
            return False

    @staticmethod
    def _persist_badges(user_id: str, badges: list[Badge]) -> None:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                for badge in badges:
                    db.execute(
                        text(
                            "INSERT INTO user_badges (id, user_id, badge_type, earned_at, metadata)"
                            " VALUES (:id, :uid, :bt, :ea, :meta)"
                            " ON CONFLICT ON CONSTRAINT uq_user_badges DO NOTHING"
                        ),
                        {
                            "id":   str(uuid.uuid4()),
                            "uid":  user_id,
                            "bt":   badge.badge_type,
                            "ea":   badge.earned_at,
                            "meta": json.dumps(badge.metadata) if badge.metadata else None,
                        },
                    )
                db.commit()
            logger.info("[BadgeService] %d badge(s) persistido(s) user=%s", len(badges), user_id)
        except Exception as exc:
            logger.warning("[BadgeService] _persist_badges user=%s: %s", user_id, exc)


__all__ = ["Badge", "BadgeService"]
