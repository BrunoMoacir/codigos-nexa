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
    ChallengeInput,
    FeeDeltaInput,
    FiscalSeasonInput,
    IdleMoneyInput,
    Notification,
    NotificationContext,
    ProactiveNotifier,
    PurchaseFollowupInput,
    SavingsBelowCdiInput,
    TransferPromoInput,
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

        # R2.c — eventos do calendário fiscal com janela ativa
        ctx.fiscal_events = self._detect_fiscal_events(user_id)

        # R2.b — desafios mensais concluídos ou perto de concluir
        ctx.challenges = self._detect_challenges(user_id)

        # R1.a — compras grandes recentes pagas de forma subótima
        ctx.purchase_followups = self._detect_purchase_followups(user_id)

        # R4.b — promoções de transferência de pontos relevantes p/ o usuário
        ctx.transfer_promos = self._detect_transfer_promos(user_id)

        if (
            not ctx.fee_deltas
            and ctx.savings_below_cdi is None
            and ctx.idle_money is None
            and not ctx.fiscal_events
            and not ctx.challenges
            and not ctx.purchase_followups
            and not ctx.transfer_promos
        ):
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
    def _detect_transfer_promos(user_id: str) -> list[TransferPromoInput]:
        """R4.b — promoções de transferência de pontos relevantes.

        Relevância exige duas coisas: (1) promoção ativa e com curadoria
        recente (staleness guard do tracker); (2) o usuário plausivelmente
        acumula no programa — detectado pelos EMISSORES presentes nas
        transações dele, mapeados para programas via base de 81 cartões.

        O saldo de pontos não é observável via Open Finance; a estimativa é
        conservadora: gasto médio mensal no crédito × 0,25 pt/R$ × 12 meses.
        O card diz explicitamente que é estimativa.
        """
        try:
            from app.optimizer.promotion_tracker import PromotionTracker

            tracker = PromotionTracker()
            active = tracker.get_active_promotions()
            if not active:
                return []  # pré-filtro barato: sem promoção, sem query

            monthly_spend, issuers = NotificationEngine._credit_spend_and_issuers(user_id)
            if monthly_spend <= 0 or not issuers:
                return []

            # Emissores do usuário → programas em que plausivelmente acumula
            from app.optimizer.card_loader import CardKnowledgeBase
            from app.opportunities.services.bank_names import banks_match

            programs: set[str] = set()
            for card in CardKnowledgeBase().load():
                if not card.loyalty_program:
                    continue
                if any(banks_match(card.issuer, issuer) for issuer in issuers):
                    programs.add(card.loyalty_program)
            if not programs:
                return []

            estimated_points = int(monthly_spend * 0.25 * 12)
            alerts = tracker.check_opportunities_by_program(
                {prog: estimated_points for prog in programs}
            )

            return [
                TransferPromoInput(
                    from_program=a.promotion.loyalty_program,
                    to_program=a.promotion.partner,
                    bonus_pct=a.promotion.bonus_pct / 100.0,
                    end_date=a.promotion.end_date.isoformat(),
                    user_points=a.estimated_points,
                )
                for a in alerts[:2]  # no máximo 2 promoções por rodada
            ]
        except Exception as exc:
            logger.warning("[NotificationEngine] transfer_promos user=%s: %s", user_id, exc)
            return []

    @staticmethod
    def _credit_spend_and_issuers(user_id: str) -> tuple[float, set[str]]:
        """Gasto médio mensal (90d, via transactions_clean) + instituições
        conectadas pelo usuário (pluggy_items.connector_name)."""
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                total = db.execute(
                    text(
                        "SELECT COALESCE(SUM(ABS(amount)), 0)"
                        " FROM transactions_clean"
                        " WHERE user_id = :uid AND amount < 0"
                        "   AND date >= CURRENT_DATE - INTERVAL '90 days'"
                    ),
                    {"uid": user_id},
                ).scalar() or 0.0
                issuer_rows = db.execute(
                    text(
                        "SELECT DISTINCT connector_name FROM pluggy_items"
                        " WHERE user_id = :uid AND connector_name IS NOT NULL"
                    ),
                    {"uid": user_id},
                ).fetchall()
        except Exception:
            return 0.0, set()

        issuers = {str(r[0]).strip() for r in issuer_rows if str(r[0] or "").strip()}
        return float(total) / 3.0, issuers

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

    @staticmethod
    def _detect_fiscal_events(user_id: str) -> list[FiscalSeasonInput]:
        """R2.c — eventos do calendário fiscal com janela ativa, já
        personalizados (MEI/CLT/valores) pelo SeasonalityService."""
        try:
            from app.seasonality.service import get_seasonality_service

            response = get_seasonality_service().get_events(user_id)
        except Exception as exc:
            logger.warning("[NotificationEngine] fiscal_events user=%s: %s", user_id, exc)
            return []

        return [
            FiscalSeasonInput(
                event_code=e.event_code,
                name=e.name,
                description=e.description,
                action_hint=e.action_hint,
                deadline=e.deadline.isoformat(),
                days_until_deadline=e.days_until_deadline,
                is_obligation=e.is_obligation,
                estimated_amount_brl=e.estimated_amount_brl,
                is_personalized=e.is_personalized,
            )
            for e in response.events
        ]

    @staticmethod
    def _detect_challenges(user_id: str) -> list[ChallengeInput]:
        """R2.b — desafios do mês corrente com progresso atualizado.
        O ChallengeService devolve apenas o que merece card (COMPLETED
        ou ACTIVE ≥70%); o gerador refiltra por segurança."""
        try:
            from app.health_score.challenge_service import get_challenge_service

            return get_challenge_service().get_feed_inputs(user_id)
        except Exception as exc:
            logger.warning("[NotificationEngine] challenges user=%s: %s", user_id, exc)
            return []

    @staticmethod
    def _detect_purchase_followups(user_id: str) -> list[PurchaseFollowupInput]:
        """R1.a — compras grandes dos últimos 14 dias pagas de forma
        subótima segundo o F7 (análise retroativa)."""
        try:
            from app.purchase.post_purchase import get_post_purchase_analyzer

            return get_post_purchase_analyzer().detect(user_id)
        except Exception as exc:
            logger.warning("[NotificationEngine] purchase_followups user=%s: %s", user_id, exc)
            return []

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
                    priority=notif.priority,   # WARNING/CRITICAL sobem para push (PWA)
                )
        except Exception as exc:
            logger.warning("[NotificationEngine] _deliver_all user=%s: %s", user_id, exc)


__all__ = ["NotificationEngine"]
