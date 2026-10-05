"""
app/jobs/daily_digest.py — Job diário 07h00 (R1.c)

Compila os eventos do dia anterior para cada usuário ativo e envia via
delivery_service (email ou in_app conforme user_settings).

Fluxo por usuário:
  1. Verificar user_settings.notification_frequency não é "off"
  2. Verificar daily_digest_log — pular se já enviado hoje (idempotência)
  3. Coletar eventos digestíveis (score, tarifas, oportunidades, prazos
     fiscais R2.c, desafios concluídos R2.b, alertas)
  4. Pular se não há nenhum evento (sem transações novas)
  5. Formatar HTML do digest
  6. Entregar via delivery_service.deliver()
  7. Registrar em daily_digest_log (ON CONFLICT DO NOTHING)
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.jobs._base import get_active_user_ids, job_guard
from app.core.formatacao import brl

logger = logging.getLogger(__name__)


# ── Estruturas internas ──────────────────────────────────────────────

@dataclass
class DigestEvent:
    category: str    # "score" | "tarifa" | "oportunidade" | "alerta"
    title: str
    detail: str


@dataclass
class DigestPayload:
    user_id: str
    digest_date: date
    events: list[DigestEvent] = field(default_factory=list)

    @property
    def events_qty(self) -> int:
        return len(self.events)


# ── Job principal ────────────────────────────────────────────────────

@job_guard("daily_digest")
async def run_daily_digest() -> None:
    user_ids = get_active_user_ids()
    today = date.today()
    logger.info("[daily_digest] Iniciando digest para %d usuários — data=%s", len(user_ids), today)

    sent_count = 0
    skip_count = 0

    for user_id in user_ids:
        try:
            if not _wants_daily_digest(user_id):
                skip_count += 1
                continue

            if _already_sent_today(user_id, today):
                logger.debug("[daily_digest] Já enviado hoje para user=%s", user_id)
                skip_count += 1
                continue

            payload = _collect_events(user_id, today)

            if not payload.events:
                logger.debug("[daily_digest] Sem eventos para user=%s — digest omitido", user_id)
                skip_count += 1
                continue

            subject, html_body = _format_html(payload)

            from app.core.notifications.delivery_service import deliver
            nid = str(uuid.uuid4())
            results = deliver(
                user_id=user_id,
                subject=subject,
                html_body=html_body,
                notification_type="daily_digest",
                notification_id=nid,
            )

            success = any(r.success for r in results)
            sent_at = datetime.now(timezone.utc) if success else None
            _log_digest(user_id, today, payload.events_qty, sent_at)
            sent_count += 1

        except Exception as exc:
            logger.warning("[daily_digest] user=%s erro: %s", user_id, exc)

    logger.info(
        "[daily_digest] Concluído: %d enviados, %d pulados de %d usuários",
        sent_count, skip_count, len(user_ids),
    )


# ── Coleta de eventos ────────────────────────────────────────────────

def _collect_events(user_id: str, today: date) -> DigestPayload:
    payload = DigestPayload(user_id=user_id, digest_date=today)

    payload.events.extend(_collect_score_event(user_id))
    payload.events.extend(_collect_tarifa_events(user_id, today))
    payload.events.extend(_collect_negotiation_events(user_id, today))
    payload.events.extend(_collect_fiscal_deadline_events(user_id))
    payload.events.extend(_collect_challenge_events(user_id))
    payload.events.extend(_collect_alert_summary(user_id, today))

    return payload


def _collect_score_event(user_id: str) -> list[DigestEvent]:
    """Inclui o score atual se existir histórico."""
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT health_score, date FROM health_score_history"
                    " WHERE user_id = :uid ORDER BY date DESC LIMIT 1"
                ),
                {"uid": user_id},
            ).fetchone()

        if row:
            score, score_date = row
            label = "ÓTIMO" if score >= 80 else ("BOM" if score >= 60 else "ATENÇÃO")
            return [DigestEvent(
                category="score",
                title=f"Score financeiro: {score}/100 ({label})",
                detail=f"Atualizado em {score_date}.",
            )]
    except Exception as exc:
        logger.debug("[daily_digest] _collect_score_event user=%s: %s", user_id, exc)
    return []


def _collect_tarifa_events(user_id: str, today: date) -> list[DigestEvent]:
    """
    Tarifas do mês atual que aumentaram mais de 10% vs. mês anterior.
    Reutiliza a mesma query do NotificationEngine para consistência.
    """
    current_month = today.strftime("%Y-%m")
    prev_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            rows = db.execute(
                text("""
                    SELECT curr.bank_name, curr.fee_type, prev.amount, curr.amount
                    FROM bank_fee_history curr
                    JOIN bank_fee_history prev
                        ON  prev.user_id   = curr.user_id
                        AND prev.bank_name = curr.bank_name
                        AND prev.fee_type  = curr.fee_type
                        AND prev.month     = :prev_month
                    WHERE curr.user_id = :uid
                      AND curr.month   = :curr_month
                      AND curr.amount  > prev.amount * 1.10
                """),
                {"uid": user_id, "curr_month": current_month, "prev_month": prev_month},
            ).fetchall()

        events = []
        for bank_name, fee_type, old_amt, new_amt in rows:
            delta_pct = round((float(new_amt) - float(old_amt)) / float(old_amt) * 100, 1)
            events.append(DigestEvent(
                category="tarifa",
                title=f"Tarifa aumentou: {fee_type} no {bank_name}",
                detail=f"De {brl(float(old_amt))} para {brl(float(new_amt))} (+{delta_pct}%). "
                       "Você pode contestar com base na Resolução BACEN 3.919/2010.",
            ))
        return events
    except Exception as exc:
        logger.debug("[daily_digest] _collect_tarifa_events user=%s: %s", user_id, exc)
    return []


def _collect_negotiation_events(user_id: str, today: date) -> list[DigestEvent]:
    """Oportunidades de negociação geradas nos últimos 7 dias."""
    cutoff = today - timedelta(days=7)
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            rows = db.execute(
                text(
                    "SELECT bank_name, trigger_type, potential_gain FROM negotiation_history"
                    " WHERE user_id = :uid AND generated_at >= :cutoff"
                    " ORDER BY potential_gain DESC LIMIT 3"
                ),
                {"uid": user_id, "cutoff": datetime.combine(cutoff, datetime.min.time())},
            ).fetchall()

        events = []
        for bank_name, trigger_type, gain in rows:
            gain_str = f"{brl(float(gain))}" if gain else "valor a confirmar"
            events.append(DigestEvent(
                category="oportunidade",
                title=f"Oportunidade em {bank_name}: {trigger_type}",
                detail=f"Potencial de economia de {gain_str}. Acesse o Negociador para o script.",
            ))
        return events
    except Exception as exc:
        logger.debug("[daily_digest] _collect_negotiation_events user=%s: %s", user_id, exc)
    return []


def _collect_fiscal_deadline_events(user_id: str) -> list[DigestEvent]:
    """
    R2.c — obrigações fiscais com prazo em até 7 dias (máx. 2).
    Reutiliza o SeasonalityService (mesma fonte do card FISCAL_SEASON).
    """
    try:
        from app.seasonality.service import get_seasonality_service

        response = get_seasonality_service().get_events(user_id)
        urgent = [
            e for e in response.events
            if e.is_obligation and e.days_until_deadline <= 7
        ]
        return [
            DigestEvent(
                category="prazo",
                title=f"{e.name} — faltam {e.days_until_deadline} dia(s)",
                detail=e.action_hint,
            )
            for e in urgent[:2]
        ]
    except Exception as exc:
        logger.debug("[daily_digest] _collect_fiscal_deadline_events user=%s: %s", user_id, exc)
    return []


def _collect_challenge_events(user_id: str) -> list[DigestEvent]:
    """R2.b — desafios concluídos nas últimas 24h (lidos da tabela; o
    fechamento/atualização é feito pelo health_score_snapshot às 04h)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            rows = db.execute(
                text(
                    "SELECT title, month FROM user_challenges"
                    " WHERE user_id = :uid AND status = 'COMPLETED'"
                    " AND completed_at >= :cutoff"
                ),
                {"uid": user_id, "cutoff": cutoff},
            ).fetchall()
        return [
            DigestEvent(
                category="desafio",
                title=f"Desafio concluído: {title}",
                detail=f"Referente a {month}. Veja o badge e o próximo desafio no Health Score.",
            )
            for title, month in rows
        ]
    except Exception as exc:
        logger.debug("[daily_digest] _collect_challenge_events user=%s: %s", user_id, exc)
    return []


def _collect_alert_summary(user_id: str, today: date) -> list[DigestEvent]:
    """Conta alertas entregues nas últimas 24h (via notification_delivery_log)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT COUNT(*) FROM notification_delivery_log"
                    " WHERE user_id = :uid AND status = 'sent' AND sent_at >= :cutoff"
                ),
                {"uid": user_id, "cutoff": cutoff},
            ).fetchone()

        count = row[0] if row else 0
        if count > 0:
            return [DigestEvent(
                category="alerta",
                title=f"{count} alerta(s) enviado(s) nas últimas 24h",
                detail="Abra o app para ver os detalhes completos.",
            )]
    except Exception as exc:
        logger.debug("[daily_digest] _collect_alert_summary user=%s: %s", user_id, exc)
    return []


# ── Formatação HTML ───────────────────────────────────────────────────

def _format_html(payload: DigestPayload) -> tuple[str, str]:
    subject = f"Nexa — Seu resumo financeiro de {payload.digest_date.strftime('%d/%m/%Y')}"

    rows_html = ""
    for ev in payload.events:
        icon = {
            "score": "📊", "tarifa": "⚠️", "oportunidade": "💡",
            "alerta": "🔔", "prazo": "📅", "desafio": "🏅",
        }.get(ev.category, "•")
        rows_html += (
            f"<tr>"
            f"<td style='padding:8px;vertical-align:top'>{icon}</td>"
            f"<td style='padding:8px'><strong>{ev.title}</strong><br/>"
            f"<span style='color:#555;font-size:13px'>{ev.detail}</span></td>"
            f"</tr>"
        )

    html_body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
  <h2 style="color:#1a1a2e">Seu resumo Nexa — {payload.digest_date.strftime('%d/%m/%Y')}</h2>
  <table style="width:100%;border-collapse:collapse">
    {rows_html}
  </table>
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee"/>
  <p style="font-size:11px;color:#999">
    Para ajustar a frequência dos seus alertas, acesse Configurações no app Nexa.
  </p>
</div>
"""
    return subject, html_body


# ── Persistência ──────────────────────────────────────────────────────

def _wants_daily_digest(user_id: str) -> bool:
    """
    Verifica user_settings.notification_frequency.
    Retorna True se "daily" (padrão) ou "realtime". False se "weekly" ou "off".
    Fallback True quando a tabela ainda não existe.
    """
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT notification_frequency, subscription_status"
                    " FROM user_settings WHERE user_id = :uid"
                ),
                {"uid": user_id},
            ).fetchone()

        if row:
            freq, status = row
            if status == "paused" or status == "cancelled":
                return False
            return freq in ("daily", "realtime", None)
        return True  # sem configuração → envia
    except Exception:
        return True


def _already_sent_today(user_id: str, today: date) -> bool:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT 1 FROM daily_digest_log"
                    " WHERE user_id = :uid AND date = :dt LIMIT 1"
                ),
                {"uid": user_id, "dt": today},
            ).fetchone()
        return row is not None
    except Exception as exc:
        logger.debug("[daily_digest] _already_sent_today user=%s: %s", user_id, exc)
        return False  # na dúvida, tenta enviar


def _log_digest(user_id: str, digest_date: date, events_qty: int, sent_at: datetime | None) -> None:
    """
    Registra o digest em daily_digest_log.
    ON CONFLICT DO NOTHING garante idempotência caso o job rode duas vezes.
    """
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            db.execute(
                text(
                    "INSERT INTO daily_digest_log (id, user_id, date, events_qty, sent_at)"
                    " VALUES (:id, :uid, :dt, :qty, :sent_at)"
                    " ON CONFLICT ON CONSTRAINT uq_daily_digest_log DO NOTHING"
                ),
                {
                    "id":      str(uuid.uuid4()),
                    "uid":     user_id,
                    "dt":      digest_date,
                    "qty":     events_qty,
                    "sent_at": sent_at,
                },
            )
            db.commit()
    except Exception as exc:
        logger.warning("[daily_digest] _log_digest user=%s: %s", user_id, exc)
