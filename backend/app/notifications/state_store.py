"""
app/notifications/state_store.py — Estado Persistente de Notificações (MX.3)

Responsabilidades:
    1. Deduplicação por estado: mesma notificação lógica não reaparece
       antes do TTL por tipo expirar — evita que o usuário veja o mesmo
       alerta de burn rate todos os dias.

    2. Feedback loop: registra eventos shown / tapped / dismissed no DuckDB
       para calibração dos thresholds ao longo do tempo.

Storage: DuckDB (finance.duckdb) — tabelas notification_state e notification_events.

Fingerprint: hash MD5 estável de (user_id, type, campos-chave por tipo + janela temporal).
             Mesmo evento lógico em dias diferentes = mesmo fingerprint dentro da janela.

TTLs por tipo:
    BURN_RATE_HIGH        3 dias   — orçamento muda todo mês
    ANOMALY_DETECTED      7 dias   — anomalia recorrente = padrão novo
    SUBSCRIPTION_INCREASE 30 dias  — usuário já sabe, não precisa lembrar
    CARD_OPPORTUNITY      14 dias  — oportunidade persiste por 2 semanas
    WAIVER_ALERT          7 dias   — urgência muda ao longo do mês
    TRANSFER_PROMO        3 dias   — promoção é urgente
    SCORE_IMPROVED        30 dias  — um score por mês é suficiente
    GOAL_PROGRESS         30 dias  — marco atingido, não repetir
    SAFE_TO_SPEND_LOW     1 dia    — situação diária, pode mudar rapidamente
    LIFE_EVENT            30 dias  — evento de vida, não repeat dentro do mês
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from app.notifications.notifier import Notification

logger = logging.getLogger(__name__)


# ── TTL por tipo (dias) ───────────────────────────────────────────────────────
# CRITICAL nunca é suprimido por estado — valor não consultado para CRITICAL.

_SEEN_TTL_DAYS: dict[str, int] = {
    "BURN_RATE_HIGH":        3,
    "ANOMALY_DETECTED":      7,
    "SUBSCRIPTION_INCREASE": 30,
    "CARD_OPPORTUNITY":      14,
    "WAIVER_ALERT":          7,
    "TRANSFER_PROMO":        3,
    "SCORE_IMPROVED":        30,
    "GOAL_PROGRESS":         30,
    "SAFE_TO_SPEND_LOW":     1,
    "LIFE_EVENT":            30,
    "SAVINGS_BELOW_CDI":     30,  # OPP.4 — dado macro, um lembrete por mês basta
    "IDLE_MONEY_DETECTED":   14,  # OPP — oportunidade persiste; não martelar diariamente
    "FISCAL_SEASON":         10,  # R2.c — ~2-3 lembretes por janela fiscal
    "CHALLENGE_COMPLETED":   30,  # R2.b — conclusão é evento único no mês
    "CHALLENGE_PROGRESS":     7,  # R2.b — no máx. 1 empurrão por semana
    "PURCHASE_FOLLOWUP":     30,  # R1.a — cada compra gera no máx. 1 card
}


# ── Fingerprint ───────────────────────────────────────────────────────────────

def compute_fingerprint(user_id: str, n: Notification) -> str:
    """
    Hash estável que identifica a notificação logicamente.

    Campos usados por tipo:
      BURN_RATE_HIGH        → categoria + ano-mês
      ANOMALY_DETECTED      → merchant + bucket de valor (R$50)
      SUBSCRIPTION_INCREASE → merchant + ano-mês
      CARD_OPPORTUNITY      → card_name + bimestre
      WAIVER_ALERT          → card_name + ano-mês
      TRANSFER_PROMO        → programas + end_date
      SCORE_IMPROVED        → ano-mês
      GOAL_PROGRESS         → goal_id + milestone
      SAFE_TO_SPEND_LOW     → semana ISO do ano
      LIFE_EVENT            → event + ano-mês
    """
    today = date.today()
    m = n.metadata
    t = n.type

    if t == "BURN_RATE_HIGH":
        parts = [t, m.get("category", ""), f"{today.year}-{today.month}"]
    elif t == "ANOMALY_DETECTED":
        bucket = str(round(m.get("amount", 0) / 50) * 50)
        parts = [t, m.get("merchant", ""), bucket]
    elif t == "SUBSCRIPTION_INCREASE":
        parts = [t, m.get("merchant", ""), f"{today.year}-{today.month}"]
    elif t == "CARD_OPPORTUNITY":
        bimestre = (today.month - 1) // 2
        parts = [t, m.get("card_name", ""), f"{today.year}-B{bimestre}"]
    elif t == "WAIVER_ALERT":
        parts = [t, m.get("card_name", ""), f"{today.year}-{today.month}"]
    elif t == "TRANSFER_PROMO":
        parts = [t, m.get("from_program", ""), m.get("to_program", ""), m.get("end_date", "")]
    elif t == "SCORE_IMPROVED":
        parts = [t, f"{today.year}-{today.month}"]
    elif t == "GOAL_PROGRESS":
        parts = [t, m.get("goal_id", ""), str(m.get("milestone", 0))]
    elif t == "SAFE_TO_SPEND_LOW":
        parts = [t, str(today.isocalendar()[1])]   # semana ISO
    elif t == "LIFE_EVENT":
        parts = [t, m.get("event", ""), f"{today.year}-{today.month}"]
    elif t == "SAVINGS_BELOW_CDI":
        parts = [t, f"{today.year}-{today.month}"]
    elif t == "IDLE_MONEY_DETECTED":
        # bucket de R$500 — variação pequena do ocioso não é notificação nova
        bucket = str(round(m.get("idle_amount", 0) / 500) * 500)
        parts = [t, bucket, f"{today.year}-{today.month}"]
    elif t == "FISCAL_SEASON":
        # DAS é mensal (ano-mês); os demais eventos são anuais (ano)
        window = f"{today.year}-{today.month}" if m.get("event_code") == "DAS_MEI" else str(today.year)
        parts = [t, m.get("event_code", ""), window]
    elif t in ("CHALLENGE_COMPLETED", "CHALLENGE_PROGRESS"):
        parts = [t, m.get("challenge_type", ""), m.get("month", "")]
    elif t == "PURCHASE_FOLLOWUP":
        parts = [t, m.get("transaction_id", "")]
    else:
        parts = [t, n.message[:40]]

    raw = "|".join([user_id] + parts)
    return hashlib.md5(raw.encode()).hexdigest()[:16]


# ── Schema DDL ────────────────────────────────────────────────────────────────

_DDL_STATE = """
CREATE TABLE IF NOT EXISTS notification_state (
    fingerprint       TEXT    NOT NULL,
    user_id           TEXT    NOT NULL,
    notification_type TEXT    NOT NULL,
    first_seen_at     TIMESTAMP NOT NULL,
    last_seen_at      TIMESTAMP NOT NULL,
    seen_count        INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (fingerprint, user_id)
)
"""

_DDL_EVENTS = """
CREATE TABLE IF NOT EXISTS notification_events (
    id                TEXT    NOT NULL PRIMARY KEY,
    user_id           TEXT    NOT NULL,
    fingerprint       TEXT    NOT NULL,
    notification_type TEXT    NOT NULL,
    event_type        TEXT    NOT NULL,
    created_at        TIMESTAMP NOT NULL
)
"""


# ── Store ─────────────────────────────────────────────────────────────────────

class NotificationStateStore:
    """
    Persiste estado de notificações e eventos de interação no DuckDB.

    Todas as operações são fail-open: se o DuckDB não estiver disponível,
    o sistema continua funcionando sem deduplicação de estado.

    Uso no router:
        store = NotificationStateStore()
        unseen = store.filter_unseen(user_id, relevance_filtered)
        store.mark_shown(user_id, unseen)
        # fingerprints para o cliente usar em dismiss/tap:
        fps = store.annotate_fingerprints(user_id, unseen)
    """

    def _conn(self):
        from app.core.db.queries import get_connection
        return get_connection()

    def _init(self, con) -> None:
        con.execute(_DDL_STATE)
        con.execute(_DDL_EVENTS)

    # ── fingerprints ──────────────────────────────────────────────────

    def annotate_fingerprints(
        self, user_id: str, notifications: list[Notification]
    ) -> dict[str, str]:
        """Retorna {notification.id → fingerprint}."""
        return {n.id: compute_fingerprint(user_id, n) for n in notifications}

    # ── filtro de não-vistos ──────────────────────────────────────────

    def filter_unseen(
        self, user_id: str, notifications: list[Notification]
    ) -> list[Notification]:
        """
        Remove notificações cujo fingerprint foi visto dentro do TTL.
        CRITICAL nunca é suprimido.
        """
        if not notifications:
            return notifications

        try:
            con = self._conn()
            try:
                self._init(con)
                fps = {n.id: compute_fingerprint(user_id, n) for n in notifications}
                fp_list = list(fps.values())

                placeholders = ",".join("?" * len(fp_list))
                rows = con.execute(
                    f"SELECT fingerprint, last_seen_at FROM notification_state "
                    f"WHERE user_id = ? AND fingerprint IN ({placeholders})",
                    [user_id, *fp_list],
                ).fetchall()
                seen_map: dict[str, datetime] = {r[0]: r[1] for r in rows}
            finally:
                con.close()

            now = datetime.now(timezone.utc)
            result: list[Notification] = []
            suppressed = 0

            for n in notifications:
                if n.priority == "CRITICAL":
                    result.append(n)
                    continue

                fp = fps[n.id]
                last_seen = seen_map.get(fp)

                if last_seen is None:
                    result.append(n)
                    continue

                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)

                ttl = _SEEN_TTL_DAYS.get(n.type, 7)
                if now - last_seen > timedelta(days=ttl):
                    result.append(n)
                else:
                    suppressed += 1
                    logger.debug(
                        "state_store: suprimida type=%s fp=%s (vista há %.1fh)",
                        n.type, fp, (now - last_seen).total_seconds() / 3600,
                    )

            if suppressed:
                logger.info(
                    "NotificationStateStore | user=%s suprimidas=%d/%d",
                    user_id, suppressed, len(notifications),
                )
            return result

        except Exception as exc:
            logger.warning("NotificationStateStore.filter_unseen falhou: %s", exc)
            return notifications  # fail-open

    # ── marcar como mostrado ──────────────────────────────────────────

    def mark_shown(self, user_id: str, notifications: list[Notification]) -> None:
        """Upserta fingerprints na tabela de estado e insere eventos 'shown'."""
        if not notifications:
            return

        try:
            con = self._conn()
            try:
                self._init(con)
                now = datetime.now(timezone.utc)

                for n in notifications:
                    fp = compute_fingerprint(user_id, n)
                    existing = con.execute(
                        "SELECT seen_count FROM notification_state "
                        "WHERE fingerprint = ? AND user_id = ?",
                        [fp, user_id],
                    ).fetchone()

                    if existing:
                        con.execute(
                            "UPDATE notification_state "
                            "SET last_seen_at = ?, seen_count = seen_count + 1 "
                            "WHERE fingerprint = ? AND user_id = ?",
                            [now, fp, user_id],
                        )
                    else:
                        con.execute(
                            "INSERT INTO notification_state "
                            "(fingerprint, user_id, notification_type, "
                            " first_seen_at, last_seen_at, seen_count) "
                            "VALUES (?, ?, ?, ?, ?, 1)",
                            [fp, user_id, n.type, now, now],
                        )

                    con.execute(
                        "INSERT INTO notification_events "
                        "(id, user_id, fingerprint, notification_type, event_type, created_at) "
                        "VALUES (?, ?, ?, ?, 'shown', ?)",
                        [str(uuid.uuid4())[:8], user_id, fp, n.type, now],
                    )
            finally:
                con.close()

        except Exception as exc:
            logger.warning("NotificationStateStore.mark_shown falhou: %s", exc)

    # ── registrar evento de interação ─────────────────────────────────

    def log_event(
        self,
        user_id: str,
        fingerprint: str,
        notification_type: str,
        event_type: str,   # "tapped" | "dismissed"
    ) -> None:
        """Registra uma interação do usuário (tapped ou dismissed)."""
        if event_type not in {"tapped", "dismissed"}:
            logger.warning("log_event: event_type inválido '%s'", event_type)
            return

        try:
            con = self._conn()
            try:
                self._init(con)
                con.execute(
                    "INSERT INTO notification_events "
                    "(id, user_id, fingerprint, notification_type, event_type, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        str(uuid.uuid4())[:8],
                        user_id, fingerprint, notification_type,
                        event_type, datetime.now(timezone.utc),
                    ],
                )
            finally:
                con.close()
        except Exception as exc:
            logger.warning("NotificationStateStore.log_event falhou: %s", exc)

    # ── analytics ────────────────────────────────────────────────────

    def get_analytics_summary(self, user_id: str, days: int = 30) -> dict:
        """
        Retorna shown vs dismissed por tipo nos últimos N dias.

        Exemplo de saída:
            {
                "BURN_RATE_HIGH":   {"shown": 4, "dismissed": 3},
                "CARD_OPPORTUNITY": {"shown": 2, "tapped": 1},
            }

        Usado para calibrar thresholds: taxa de dismiss alta → threshold muito baixo.
        """
        try:
            con = self._conn()
            try:
                self._init(con)
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                rows = con.execute(
                    "SELECT notification_type, event_type, COUNT(*) "
                    "FROM notification_events "
                    "WHERE user_id = ? AND created_at >= ? "
                    "GROUP BY notification_type, event_type",
                    [user_id, cutoff],
                ).fetchall()
            finally:
                con.close()

            summary: dict[str, dict[str, int]] = {}
            for ntype, etype, cnt in rows:
                summary.setdefault(ntype, {})[etype] = cnt
            return summary

        except Exception as exc:
            logger.warning("NotificationStateStore.get_analytics_summary falhou: %s", exc)
            return {}
