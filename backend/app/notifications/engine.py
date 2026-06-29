"""
app/notifications/engine.py — NotificationEngine (MX.3 proativo)

Responsabilidade:
  Geração e entrega de notificações proativas sem necessidade de request HTTP.
  Chamado pelo scheduler (notification_scheduler.py a cada 6h).

Diferença do router:
  - O router GET /notifications/{user_id} é reativo (usuário abriu o app).
  - O engine é proativo: roda em background e entrega via canal configurado
    (email / in_app) mesmo sem o usuário abrir o app.

Foco do engine:
  Cobre eventos que o usuário não veria sem abrir o app:
    • TARIFA_AUMENTO_UNILATERAL — detectado em bank_fee_history (D4)
  Outros tipos (burn rate, anomalias, etc.) continuam no router,
  onde o contexto completo do runner Pluggy está disponível.
"""

import logging
from datetime import date, timedelta

from app.notifications.notifier import (
    FeeDeltaInput,
    Notification,
    NotificationContext,
    ProactiveNotifier,
)

logger = logging.getLogger(__name__)

_notifier = ProactiveNotifier()


class NotificationEngine:
    """
    Motor proativo de notificações — desacoplado do request HTTP.

    Usage (pelo scheduler):
        engine = NotificationEngine()
        await engine.run_for_all_users()
    """

    async def run_for_user(self, user_id: str) -> list[Notification]:
        """
        Gera e entrega notificações proativas para um usuário.

        Returns:
            Lista de notificações geradas (pode ser vazia).
        """
        ctx = NotificationContext()

        # Detecta tarifas aumentadas vs. mês anterior
        ctx.fee_deltas = self._detect_fee_deltas(user_id)

        if not ctx.fee_deltas:
            return []

        notifications = _notifier.generate(ctx)

        if notifications:
            self._deliver_all(user_id, notifications)

        return notifications

    async def run_for_all_users(self) -> dict[str, list[Notification]]:
        """
        Roda run_for_user para todos os usuários ativos.

        Returns:
            {user_id: [Notification, ...]} — apenas usuários com notificações.
        """
        from app.jobs._base import get_active_user_ids

        user_ids = get_active_user_ids()
        logger.info("[NotificationEngine] Iniciando para %d usuários", len(user_ids))

        results: dict[str, list[Notification]] = {}
        for user_id in user_ids:
            try:
                notes = await self.run_for_user(user_id)
                if notes:
                    results[user_id] = notes
            except Exception as exc:
                logger.warning("[NotificationEngine] user=%s erro: %s", user_id, exc)

        total = sum(len(v) for v in results.values())
        logger.info(
            "[NotificationEngine] Concluído: %d notificações para %d usuários",
            total, len(results),
        )
        return results

    # ── Detecção ──────────────────────────────────────────────────────

    @staticmethod
    def _detect_fee_deltas(user_id: str) -> list[FeeDeltaInput]:
        """
        Compara bank_fee_history do mês atual vs. mês anterior para o usuário.
        Retorna apenas tarifas que aumentaram (qualquer delta positivo;
        o threshold de 10% é aplicado no gerador).
        """
        today = date.today()
        current_month = today.strftime("%Y-%m")
        prev_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text("""
                        SELECT
                            curr.bank_name,
                            curr.fee_type,
                            prev.amount  AS old_amount,
                            curr.amount  AS new_amount
                        FROM bank_fee_history curr
                        JOIN bank_fee_history prev
                            ON  prev.user_id   = curr.user_id
                            AND prev.bank_name = curr.bank_name
                            AND prev.fee_type  = curr.fee_type
                            AND prev.month     = :prev_month
                        WHERE curr.user_id = :uid
                          AND curr.month   = :curr_month
                          AND curr.amount  > prev.amount
                    """),
                    {
                        "uid":        user_id,
                        "curr_month": current_month,
                        "prev_month": prev_month,
                    },
                ).fetchall()

            return [
                FeeDeltaInput(
                    bank_name=r[0],
                    fee_type=r[1],
                    old_amount=float(r[2]),
                    new_amount=float(r[3]),
                    delta_pct=round((float(r[3]) - float(r[2])) / float(r[2]), 4),
                )
                for r in rows
            ]

        except Exception as exc:
            logger.warning("[NotificationEngine] _detect_fee_deltas user=%s: %s", user_id, exc)
            return []

    # ── Entrega ───────────────────────────────────────────────────────

    @staticmethod
    def _deliver_all(user_id: str, notifications: list[Notification]) -> None:
        """Entrega cada notificação via delivery_service (email / in_app)."""
        try:
            from app.core.notifications.delivery_service import deliver

            for notif in notifications:
                html_body = (
                    f"<h2>{notif.title}</h2>"
                    f"<p>{notif.message}</p>"
                    + (f"<p><em>{notif.action_hint}</em></p>" if notif.action_hint else "")
                )
                deliver(
                    user_id=user_id,
                    subject=notif.title,
                    html_body=html_body,
                    notification_type=notif.type,
                    notification_id=notif.id,
                )
        except Exception as exc:
            logger.warning("[NotificationEngine] _deliver_all user=%s: %s", user_id, exc)


__all__ = ["NotificationEngine"]
