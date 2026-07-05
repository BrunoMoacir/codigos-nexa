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
    IdleMoneyInput,
    Notification,
    NotificationContext,
    ProactiveNotifier,
    SavingsBelowCdiInput,
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

        # OPP4-D/E — poupança abaixo do CDI (personalizado quando há saldo
        # real; genérico caso contrário) e dinheiro parado (Etapa 6)
        ctx.savings_below_cdi = self._detect_savings_below_cdi(user_id)
        ctx.idle_money = self._detect_idle_money(user_id)

        if not ctx.fee_deltas and ctx.savings_below_cdi is None and ctx.idle_money is None:
            return []

        notifications = _notifier.generate(ctx)

        # Dedup por estado (mesmo pipeline do router): sem isso o engine
        # reentregaria o mesmo card a cada rodada de 6h — o TTL por tipo
        # (state_store._SEEN_TTL_DAYS) vale também para o canal proativo.
        notifications = self._filter_unseen(user_id, notifications)

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

    @staticmethod
    def _detect_savings_below_cdi(user_id: str | None = None):
        """OPP4-D/E — poupança vs. CDI. Com user_id, tenta a comparação
        personalizada (saldo real de poupança via account_balances); sem
        saldo, cai no genérico. Retorna input só quando severity >= MEDIUM
        (o gerador refiltra por segurança)."""
        try:
            from app.opportunities.services.savings_vs_cdi import get_savings_vs_cdi_service
            service = get_savings_vs_cdi_service()
            result = service.analyze_for_user(user_id) if user_id else service.analyze()
        except Exception as exc:
            logger.warning("[NotificationEngine] savings_vs_cdi: %s", exc)
            return None

        if result.status != "BELOW_CDI" or result.severity not in ("MEDIUM", "HIGH"):
            return None

        return SavingsBelowCdiInput(
            savings_annual_pct=result.savings_annual_pct,
            cdi_annual_pct=result.cdi_annual_pct,
            amount_reference_brl=result.amount_reference_brl,
            estimated_loss_annual_brl=result.estimated_loss_annual_brl,
            severity=result.severity,
            reason=result.reason,
            is_personalized=result.is_personalized,
            savings_balance_brl=result.savings_balance_brl,
        )

    @staticmethod
    def _detect_idle_money(user_id: str):
        """OPP Etapa 6 — dinheiro parado, apenas quando a detecção está
        CONFIRMED pelo threshold OPP1-C.

        Pré-filtro barato: consulta o snapshot mais recente (persistido pelo
        opportunity_scan diário) e só roda a análise completa quando ele
        indica saldo ocioso relevante — sem isso, cada rodada de 6h refaria
        transações + profiler + ranking para todos os usuários."""
        if not NotificationEngine._has_recent_idle_snapshot(user_id):
            return None

        try:
            from app.opportunities.services.opportunity_engine import OpportunityEngine

            result = OpportunityEngine().analyze(
                user_id=user_id, holding_months=12, persist_snapshot=False
            )
        except Exception as exc:
            logger.warning("[NotificationEngine] idle_money user=%s: %s", user_id, exc)
            return None

        if result.idle_detection_status != "CONFIRMED" or result.top_opportunity is None:
            return None

        top = result.top_opportunity
        return IdleMoneyInput(
            idle_amount=result.idle_amount,
            monthly_loss=result.monthly_loss_in_checking,
            top_opportunity=f"{top.bank_name} {top.product_type} {top.cdi_pct:.0f}% CDI",
            top_gain_monthly_brl=top.monthly_gain_brl,
        )

    @staticmethod
    def _has_recent_idle_snapshot(user_id: str, min_idle_brl: float = 500.0) -> bool:
        """True quando o snapshot mais recente (últimos 2 dias) do usuário
        registra saldo ocioso acima do threshold de confirmação OPP1-C.
        Falha fechada (False): sem snapshot, não há como estar CONFIRMED."""
        try:
            from datetime import datetime, timedelta, timezone

            from app.core.database import SessionLocal
            from sqlalchemy import text

            cutoff = datetime.now(timezone.utc) - timedelta(days=2)
            with SessionLocal() as db:
                row = db.execute(
                    text(
                        "SELECT idle_amount FROM opportunity_snapshots"
                        " WHERE user_id = :uid AND captured_at >= :cutoff"
                        " ORDER BY captured_at DESC LIMIT 1"
                    ),
                    {"uid": user_id, "cutoff": cutoff},
                ).fetchone()
            return bool(row and row[0] is not None and float(row[0]) >= min_idle_brl)
        except Exception as exc:
            logger.warning("[NotificationEngine] idle_snapshot user=%s: %s", user_id, exc)
            return False

    # ── Entrega ───────────────────────────────────────────────────────

    @staticmethod
    def _filter_unseen(user_id: str, notifications: list[Notification]) -> list[Notification]:
        """Remove notificações já entregues dentro do TTL por tipo e marca as
        restantes como vistas. Falha aberta: se o state store estiver
        indisponível, entrega tudo (comportamento anterior do engine)."""
        if not notifications:
            return notifications
        try:
            from app.notifications.state_store import NotificationStateStore

            store = NotificationStateStore()
            unseen = store.filter_unseen(user_id, notifications)
            store.mark_shown(user_id, unseen)
            return unseen
        except Exception as exc:
            logger.warning("[NotificationEngine] state_store indisponível: %s", exc)
            return notifications

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
