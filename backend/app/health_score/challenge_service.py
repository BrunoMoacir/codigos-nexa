"""
app/health_score/challenge_service.py — ChallengeService (R2.b gamificação)

Desafios mensais personalizados do Health Score. Cada mês o serviço gera
até 3 desafios a partir dos dados reais do usuário, acompanha o progresso
com as transações do mês e, no fechamento, marca COMPLETED/FAILED e
premia badges.

Tipos de desafio:
  SEM_TARIFAS        — passar o mês sem pagar nenhuma tarifa bancária
                       (gerado quando o FeeDetector achou tarifa nos 3 meses
                       anteriores — o desafio ataca um custo real do usuário)
  REDUZIR_CATEGORIA  — gastar 15% menos que a média trimestral na categoria
                       variável em que o usuário mais gasta
  GUARDAR_VALOR      — terminar o mês com saldo positivo de pelo menos 10%
                       da renda mensal detectada
  SUBIR_SCORE        — subir o health score em 3 pontos vs. o último snapshot

Badges premiados (persistidos em user_badges, mesmo contrato do BadgeService):
  PRIMEIRO_DESAFIO   — primeiro desafio concluído
  DESAFIO_TRIPLO     — 3 desafios concluídos no total
  DESAFIO_STREAK_3   — ao menos 1 desafio concluído em 3 meses consecutivos

Semântica de progresso (pct_progress 0–100):
  SEM_TARIFAS        — % do mês decorrido sem tarifa; FAILED na 1ª tarifa
  REDUZIR_CATEGORIA  — % do mês decorrido dentro do teto; FAILED ao estourar
  GUARDAR_VALOR      — % do alvo já poupado; COMPLETED ao atingir (mesmo antes
                       do fim do mês)
  SUBIR_SCORE        — % dos pontos-alvo já ganhos; COMPLETED ao atingir

Storage: tabela user_challenges (migration a7c9e5f2b1d8), SQL portável
Postgres/SQLite via SessionLocal.
"""

from __future__ import annotations

import calendar as _calendar
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Máximo de desafios gerados por mês
_MAX_CHALLENGES_PER_MONTH = 3

# REDUZIR_CATEGORIA: corte pedido sobre a média trimestral e gasto mínimo
# para a categoria ser elegível (desafio de R$40/mês não motiva ninguém)
_CATEGORY_CUT_PCT = 0.15
_CATEGORY_MIN_MONTHLY_SPEND = 200.0

# GUARDAR_VALOR: fração da renda mensal e piso do alvo
_SAVE_TARGET_INCOME_PCT = 0.10
_SAVE_TARGET_FLOOR = 50.0

# SUBIR_SCORE: pontos a subir no mês
_SCORE_TARGET_DELTA = 3

# Categorias que não valem desafio de redução (fixas ou não-discricionárias)
_NON_DISCRETIONARY = {
    "moradia", "aluguel", "rent", "housing", "salario", "salário",
    "transferencia", "transferência", "transfer", "investimento",
    "investimentos", "impostos", "taxes", "saude", "saúde", "health",
    "educacao", "educação", "education", "tarifas", "fees", "outros",
    "other", "sem categoria", "uncategorized", "renda", "income",
}


@dataclass
class Challenge:
    """Um desafio mensal, como persistido em user_challenges."""
    id: str
    user_id: str
    challenge_type: str
    month: str                    # "YYYY-MM"
    title: str
    target_label: str
    target_value: float
    progress_value: float
    pct_progress: float
    status: str                   # ACTIVE | COMPLETED | FAILED
    metadata: dict
    completed_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id":             self.id,
            "challenge_type": self.challenge_type,
            "month":          self.month,
            "title":          self.title,
            "target_label":   self.target_label,
            "target_value":   round(self.target_value, 2),
            "progress_value": round(self.progress_value, 2),
            "pct_progress":   round(self.pct_progress, 1),
            "status":         self.status,
            "metadata":       self.metadata,
            "completed_at":   self.completed_at.isoformat() if self.completed_at else None,
        }


def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def _month_bounds(month: str) -> tuple[date, date]:
    year, mon = int(month[:4]), int(month[5:7])
    last_day = _calendar.monthrange(year, mon)[1]
    return date(year, mon, 1), date(year, mon, last_day)


def _prev_month_key(month: str) -> str:
    start, _ = _month_bounds(month)
    return _month_key(start - timedelta(days=1))


class ChallengeService:
    """Geração, acompanhamento e fechamento de desafios mensais."""

    # ══════════════════════════════════════════════════════════════
    # API pública
    # ══════════════════════════════════════════════════════════════

    def sync(self, user_id: str, today: date | None = None) -> list[Challenge]:
        """
        Ponto de entrada único (router, job e feed):
          1. Fecha desafios ACTIVE de meses anteriores (COMPLETED/FAILED).
          2. Garante que o mês corrente tem desafios gerados.
          3. Atualiza o progresso dos desafios ACTIVE do mês corrente.
          4. Premia badges de conclusão.

        Retorna os desafios do mês corrente (estado pós-atualização).
        """
        today = today or date.today()
        month = _month_key(today)

        try:
            self._close_past_months(user_id, month)
            self._ensure_month(user_id, month, today)
            challenges = self._evaluate_current(user_id, month, today)
            self._award_badges(user_id)
            return challenges
        except Exception as exc:
            logger.warning("[ChallengeService] sync user=%s: %s", user_id, exc)
            return self._load(user_id, month)

    def get_feed_inputs(self, user_id: str, today: date | None = None) -> list:
        """
        Inputs para o feed (ProactiveNotifier): desafios COMPLETED
        recentemente (mês corrente ou fechados há ≤7 dias) e ACTIVE com
        progresso ≥70%. A deduplicação por TTL fica no state_store.
        """
        from app.notifications.notifier import (
            _CHALLENGE_PROGRESS_MIN_PCT,
            ChallengeInput,
        )

        today = today or date.today()
        month = _month_key(today)
        current = self.sync(user_id, today)

        inputs: list[ChallengeInput] = []
        for ch in current:
            if ch.status not in ("COMPLETED", "ACTIVE"):
                continue
            if ch.status == "ACTIVE" and ch.pct_progress < _CHALLENGE_PROGRESS_MIN_PCT:
                continue   # longe demais do fim para virar card de empurrão
            inputs.append(ChallengeInput(
                challenge_id=ch.id,
                challenge_type=ch.challenge_type,
                title=ch.title,
                month=ch.month,
                status=ch.status,
                pct_progress=ch.pct_progress,
                target_label=ch.target_label,
                detail=self._progress_detail(ch),
            ))

        # Desafios do mês anterior fechados como COMPLETED nos últimos 7 dias
        # (fechamento acontece nos primeiros dias do mês seguinte)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        for ch in self._load(user_id, _prev_month_key(month)):
            if ch.status == "COMPLETED" and ch.completed_at and ch.completed_at >= cutoff:
                inputs.append(ChallengeInput(
                    challenge_id=ch.id,
                    challenge_type=ch.challenge_type,
                    title=ch.title,
                    month=ch.month,
                    status=ch.status,
                    pct_progress=ch.pct_progress,
                    target_label=ch.target_label,
                    detail=self._progress_detail(ch),
                ))

        return inputs

    def list_challenges(self, user_id: str, month: str) -> list[Challenge]:
        """Desafios persistidos de um mês (sem gerar/atualizar nada)."""
        return self._load(user_id, month)

    # ══════════════════════════════════════════════════════════════
    # Geração
    # ══════════════════════════════════════════════════════════════

    def _ensure_month(self, user_id: str, month: str, today: date) -> None:
        if self._load(user_id, month):
            return   # já gerados

        txns = self._fetch_transactions(user_id, months_back=4, today=today)
        candidates: list[Challenge] = []

        maker_order = (
            self._make_sem_tarifas,
            self._make_reduzir_categoria,
            self._make_guardar_valor,
            self._make_subir_score,
        )
        for maker in maker_order:
            try:
                ch = maker(user_id, month, today, txns)
            except Exception as exc:
                logger.debug("[ChallengeService] maker %s: %s", maker.__name__, exc)
                ch = None
            if ch is not None:
                candidates.append(ch)
            if len(candidates) >= _MAX_CHALLENGES_PER_MONTH:
                break

        if candidates:
            self._persist_new(candidates)
            logger.info(
                "[ChallengeService] %d desafio(s) gerado(s) user=%s month=%s: %s",
                len(candidates), user_id, month,
                [c.challenge_type for c in candidates],
            )

    def _make_sem_tarifas(self, user_id, month, today, txns) -> Challenge | None:
        """Elegível quando houve tarifa bancária nos 3 meses anteriores."""
        start_prev3 = (_month_bounds(month)[0] - timedelta(days=92)).replace(day=1)
        end_prev = _month_bounds(month)[0] - timedelta(days=1)
        fees = self._detect_fees(txns, start_prev3, end_prev)
        if not fees:
            return None

        total_3m = round(sum(f.amount for f in fees), 2)
        return Challenge(
            id=str(uuid.uuid4()),
            user_id=user_id,
            challenge_type="SEM_TARIFAS",
            month=month,
            title="Mês sem tarifas bancárias",
            target_label="0 tarifas no mês",
            target_value=0.0,
            progress_value=0.0,
            pct_progress=0.0,
            status="ACTIVE",
            metadata={
                "baseline_fees_3m_brl": total_3m,
                "baseline_fees_3m_qty": len(fees),
            },
        )

    def _make_reduzir_categoria(self, user_id, month, today, txns) -> Challenge | None:
        """Categoria variável com maior gasto médio nos 3 meses anteriores."""
        month_start = _month_bounds(month)[0]
        window_start = (month_start - timedelta(days=92)).replace(day=1)
        window_end = month_start - timedelta(days=1)

        by_category: dict[str, float] = {}
        months_seen: set[str] = set()
        for tx in txns:
            if not (window_start <= tx["date"] <= window_end) or tx["amount"] >= 0:
                continue
            months_seen.add(_month_key(tx["date"]))
            cat = (tx["category"] or "").strip()
            if not cat or cat.lower() in _NON_DISCRETIONARY:
                continue
            by_category[cat] = by_category.get(cat, 0.0) + abs(tx["amount"])

        if not by_category or not months_seen:
            return None

        top_cat, total = max(by_category.items(), key=lambda kv: kv[1])
        monthly_avg = total / len(months_seen)
        if monthly_avg < _CATEGORY_MIN_MONTHLY_SPEND:
            return None

        target = round(monthly_avg * (1 - _CATEGORY_CUT_PCT), 2)
        return Challenge(
            id=str(uuid.uuid4()),
            user_id=user_id,
            challenge_type="REDUZIR_CATEGORIA",
            month=month,
            title=f"Gastar 15% menos em {top_cat}",
            target_label=f"até R$ {target:,.0f} em {top_cat}",
            target_value=target,
            progress_value=0.0,
            pct_progress=0.0,
            status="ACTIVE",
            metadata={
                "category": top_cat,
                "monthly_avg_brl": round(monthly_avg, 2),
            },
        )

    def _make_guardar_valor(self, user_id, month, today, txns) -> Challenge | None:
        """Alvo = 10% da renda mensal mediana dos 3 meses anteriores."""
        month_start = _month_bounds(month)[0]
        window_start = (month_start - timedelta(days=92)).replace(day=1)
        window_end = month_start - timedelta(days=1)

        monthly_income: dict[str, float] = {}
        for tx in txns:
            if not (window_start <= tx["date"] <= window_end) or tx["amount"] <= 0:
                continue
            key = _month_key(tx["date"])
            monthly_income[key] = monthly_income.get(key, 0.0) + tx["amount"]

        if len(monthly_income) < 2:
            return None

        values = sorted(monthly_income.values())
        mid = len(values) // 2
        median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
        target = max(_SAVE_TARGET_FLOOR, round(median * _SAVE_TARGET_INCOME_PCT / 10) * 10)

        return Challenge(
            id=str(uuid.uuid4()),
            user_id=user_id,
            challenge_type="GUARDAR_VALOR",
            month=month,
            title=f"Guardar R$ {target:,.0f} no mês",
            target_label=f"R$ {target:,.0f} poupados",
            target_value=float(target),
            progress_value=0.0,
            pct_progress=0.0,
            status="ACTIVE",
            metadata={"monthly_income_median_brl": round(median, 2)},
        )

    def _make_subir_score(self, user_id, month, today, txns) -> Challenge | None:
        """Alvo = último score + 3 pontos (limitado a 100)."""
        baseline = self._latest_score(user_id)
        if baseline is None or baseline >= 100:
            return None

        target = min(100, baseline + _SCORE_TARGET_DELTA)
        return Challenge(
            id=str(uuid.uuid4()),
            user_id=user_id,
            challenge_type="SUBIR_SCORE",
            month=month,
            title=f"Subir o score para {target}",
            target_label=f"score {target} (hoje: {baseline})",
            target_value=float(target),
            progress_value=float(baseline),
            pct_progress=0.0,
            status="ACTIVE",
            metadata={"baseline_score": baseline},
        )

    # ══════════════════════════════════════════════════════════════
    # Progresso e fechamento
    # ══════════════════════════════════════════════════════════════

    def _evaluate_current(self, user_id: str, month: str, today: date) -> list[Challenge]:
        challenges = self._load(user_id, month)
        txns = self._fetch_transactions(user_id, months_back=1, today=today)
        start, end = _month_bounds(month)
        days_in_month = end.day
        elapsed_pct = min(100.0, today.day / days_in_month * 100)

        for ch in challenges:
            if ch.status != "ACTIVE":
                continue
            self._update_progress(ch, txns, start, min(today, end), elapsed_pct, closing=False)
            self._persist_update(ch)

        return challenges

    def _close_past_months(self, user_id: str, current_month: str) -> None:
        stale = self._load_active_before(user_id, current_month)
        if not stale:
            return

        for ch in stale:
            start, end = _month_bounds(ch.month)
            txns = self._fetch_transactions_range(
                user_id, start - timedelta(days=1), end + timedelta(days=1)
            )
            self._update_progress(ch, txns, start, end, elapsed_pct=100.0, closing=True)
            if ch.status == "ACTIVE":
                # fechamento decide: quem não completou, falhou
                ch.status = "FAILED"
            self._persist_update(ch)

        logger.info(
            "[ChallengeService] %d desafio(s) fechado(s) user=%s: %s",
            len(stale), user_id,
            [(c.challenge_type, c.month, c.status) for c in stale],
        )

    def _update_progress(
        self,
        ch: Challenge,
        txns: list[dict],
        start: date,
        end: date,
        elapsed_pct: float,
        closing: bool,
    ) -> None:
        """Atualiza progress/pct/status de um desafio ACTIVE in-place."""
        now = datetime.now(timezone.utc)

        if ch.challenge_type == "SEM_TARIFAS":
            fees = self._detect_fees(txns, start, end)
            total = round(sum(f.amount for f in fees), 2)
            ch.progress_value = total
            if total > 0:
                ch.status = "FAILED"
                ch.pct_progress = 0.0
            else:
                ch.pct_progress = round(elapsed_pct, 1)
                if closing:
                    ch.status, ch.completed_at = "COMPLETED", now
                    ch.pct_progress = 100.0

        elif ch.challenge_type == "REDUZIR_CATEGORIA":
            cat = ch.metadata.get("category", "")
            spent = sum(
                abs(t["amount"]) for t in txns
                if t["amount"] < 0 and start <= t["date"] <= end
                and (t["category"] or "").strip() == cat
            )
            ch.progress_value = round(spent, 2)
            if spent > ch.target_value:
                ch.status = "FAILED"
                ch.pct_progress = 0.0
            else:
                ch.pct_progress = round(elapsed_pct, 1)
                if closing:
                    ch.status, ch.completed_at = "COMPLETED", now
                    ch.pct_progress = 100.0

        elif ch.challenge_type == "GUARDAR_VALOR":
            inflow = sum(t["amount"] for t in txns if t["amount"] > 0 and start <= t["date"] <= end)
            outflow = sum(abs(t["amount"]) for t in txns if t["amount"] < 0 and start <= t["date"] <= end)
            saved = max(0.0, inflow - outflow)
            ch.progress_value = round(saved, 2)
            ch.pct_progress = round(min(100.0, saved / ch.target_value * 100), 1) if ch.target_value else 0.0
            if saved >= ch.target_value:
                ch.status, ch.completed_at = "COMPLETED", now
                ch.pct_progress = 100.0
            elif closing:
                ch.status = "FAILED"

        elif ch.challenge_type == "SUBIR_SCORE":
            current = self._latest_score(ch.user_id)
            baseline = float(ch.metadata.get("baseline_score", 0))
            if current is not None:
                ch.progress_value = float(current)
                gained = max(0.0, current - baseline)
                needed = max(1.0, ch.target_value - baseline)
                ch.pct_progress = round(min(100.0, gained / needed * 100), 1)
                if current >= ch.target_value:
                    ch.status, ch.completed_at = "COMPLETED", now
                    ch.pct_progress = 100.0
                elif closing:
                    ch.status = "FAILED"
            elif closing:
                ch.status = "FAILED"

    @staticmethod
    def _progress_detail(ch: Challenge) -> str:
        if ch.challenge_type == "SEM_TARIFAS":
            baseline = ch.metadata.get("baseline_fees_3m_brl", 0.0)
            if ch.status == "COMPLETED":
                return f"Nos 3 meses anteriores você tinha pago R$ {baseline:,.2f} em tarifas."
            return "Nenhuma tarifa bancária detectada até agora."
        if ch.challenge_type == "REDUZIR_CATEGORIA":
            return (
                f"Gasto atual: R$ {ch.progress_value:,.0f} "
                f"de um teto de R$ {ch.target_value:,.0f}."
            )
        if ch.challenge_type == "GUARDAR_VALOR":
            return f"Já guardados: R$ {ch.progress_value:,.0f} de R$ {ch.target_value:,.0f}."
        if ch.challenge_type == "SUBIR_SCORE":
            return f"Score atual: {ch.progress_value:.0f} — alvo: {ch.target_value:.0f}."
        return ""

    # ══════════════════════════════════════════════════════════════
    # Badges
    # ══════════════════════════════════════════════════════════════

    def _award_badges(self, user_id: str) -> None:
        """Premia badges de desafio. Idempotente (ON CONFLICT DO NOTHING)."""
        try:
            completed_months = self._completed_months(user_id)
            total_completed = sum(qty for qty in completed_months.values())
            if total_completed == 0:
                return

            new_badges: list[tuple[str, dict]] = []
            if total_completed >= 1:
                new_badges.append(("PRIMEIRO_DESAFIO", {}))
            if total_completed >= 3:
                new_badges.append(("DESAFIO_TRIPLO", {"total_completed": total_completed}))
            if self._has_streak(sorted(completed_months.keys()), 3):
                new_badges.append(("DESAFIO_STREAK_3", {}))

            self._persist_badges(user_id, new_badges)
        except Exception as exc:
            logger.warning("[ChallengeService] _award_badges user=%s: %s", user_id, exc)

    @staticmethod
    def _has_streak(months: list[str], needed: int) -> bool:
        """True se há `needed` meses consecutivos na lista ordenada."""
        if len(months) < needed:
            return False
        streak = 1
        for prev, curr in zip(months, months[1:]):
            streak = streak + 1 if _prev_month_key(curr) == prev else 1
            if streak >= needed:
                return True
        return False

    # ══════════════════════════════════════════════════════════════
    # Acesso a dados
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _fetch_transactions(user_id: str, months_back: int, today: date) -> list[dict]:
        start = (today.replace(day=1) - timedelta(days=31 * months_back)).replace(day=1)
        return ChallengeService._fetch_transactions_range(user_id, start, today)

    @staticmethod
    def _fetch_transactions_range(user_id: str, start: date, end: date) -> list[dict]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT date, amount, description, category"
                        " FROM transactions_clean"
                        " WHERE user_id = :uid AND date >= :start AND date <= :end"
                    ),
                    {"uid": user_id, "start": start, "end": end},
                ).fetchall()
            result = []
            for r in rows:
                tx_date = r[0]
                if isinstance(tx_date, str):
                    tx_date = date.fromisoformat(tx_date[:10])
                elif isinstance(tx_date, datetime):
                    tx_date = tx_date.date()
                result.append({
                    "date": tx_date,
                    "amount": float(r[1] or 0.0),
                    "description": r[2] or "",
                    "category": r[3] or "",
                })
            return result
        except Exception as exc:
            logger.warning("[ChallengeService] _fetch_transactions user=%s: %s", user_id, exc)
            return []

    @staticmethod
    def _detect_fees(txns: list[dict], start: date, end: date) -> list:
        """Reutiliza o FeeDetector do F5 sobre a janela pedida."""
        import polars as pl
        from app.costs.fee_detector import FeeDetector

        window = [t for t in txns if start <= t["date"] <= end]
        if not window:
            return []
        df = pl.DataFrame({
            "transaction_date": [t["date"] for t in window],
            "amount":           [t["amount"] for t in window],
            "description":      [t["description"] for t in window],
        })
        return FeeDetector().detect(df)

    @staticmethod
    def _latest_score(user_id: str) -> int | None:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                row = db.execute(
                    text(
                        "SELECT health_score FROM health_score_history"
                        " WHERE user_id = :uid ORDER BY date DESC LIMIT 1"
                    ),
                    {"uid": user_id},
                ).fetchone()
            return int(row[0]) if row else None
        except Exception as exc:
            logger.debug("[ChallengeService] _latest_score user=%s: %s", user_id, exc)
            return None

    def _load(self, user_id: str, month: str) -> list[Challenge]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT id, challenge_type, month, title, target_label,"
                        " target_value, progress_value, pct_progress, status,"
                        " metadata, completed_at"
                        " FROM user_challenges"
                        " WHERE user_id = :uid AND month = :month"
                        " ORDER BY challenge_type"
                    ),
                    {"uid": user_id, "month": month},
                ).fetchall()
            return [self._row_to_challenge(user_id, r) for r in rows]
        except Exception as exc:
            logger.warning("[ChallengeService] _load user=%s month=%s: %s", user_id, month, exc)
            return []

    def _load_active_before(self, user_id: str, current_month: str) -> list[Challenge]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT id, challenge_type, month, title, target_label,"
                        " target_value, progress_value, pct_progress, status,"
                        " metadata, completed_at"
                        " FROM user_challenges"
                        " WHERE user_id = :uid AND status = 'ACTIVE' AND month < :month"
                    ),
                    {"uid": user_id, "month": current_month},
                ).fetchall()
            return [self._row_to_challenge(user_id, r) for r in rows]
        except Exception as exc:
            logger.warning("[ChallengeService] _load_active_before user=%s: %s", user_id, exc)
            return []

    @staticmethod
    def _row_to_challenge(user_id: str, r) -> Challenge:
        completed_at = r[10]
        if isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)
        if completed_at is not None and completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        return Challenge(
            id=r[0],
            user_id=user_id,
            challenge_type=r[1],
            month=r[2],
            title=r[3],
            target_label=r[4] or "",
            target_value=float(r[5] or 0.0),
            progress_value=float(r[6] or 0.0),
            pct_progress=float(r[7] or 0.0),
            status=r[8],
            metadata=json.loads(r[9]) if r[9] else {},
            completed_at=completed_at,
        )

    @staticmethod
    def _persist_new(challenges: list[Challenge]) -> None:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            for ch in challenges:
                db.execute(
                    text(
                        "INSERT INTO user_challenges"
                        " (id, user_id, challenge_type, month, title, target_label,"
                        "  target_value, progress_value, pct_progress, status,"
                        "  metadata, created_at, updated_at)"
                        " VALUES (:id, :uid, :ct, :month, :title, :tl, :tv, :pv,"
                        "  :pct, :status, :meta, :now, :now)"
                        " ON CONFLICT (user_id, challenge_type, month) DO NOTHING"
                    ),
                    {
                        "id": ch.id, "uid": ch.user_id, "ct": ch.challenge_type,
                        "month": ch.month, "title": ch.title, "tl": ch.target_label,
                        "tv": ch.target_value, "pv": ch.progress_value,
                        "pct": ch.pct_progress, "status": ch.status,
                        "meta": json.dumps(ch.metadata), "now": now,
                    },
                )
            db.commit()

    @staticmethod
    def _persist_update(ch: Challenge) -> None:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                db.execute(
                    text(
                        "UPDATE user_challenges SET"
                        " progress_value = :pv, pct_progress = :pct,"
                        " status = :status, completed_at = :ca, updated_at = :now"
                        " WHERE id = :id"
                    ),
                    {
                        "pv": ch.progress_value, "pct": ch.pct_progress,
                        "status": ch.status, "ca": ch.completed_at,
                        "now": datetime.now(timezone.utc), "id": ch.id,
                    },
                )
                db.commit()
        except Exception as exc:
            logger.warning("[ChallengeService] _persist_update id=%s: %s", ch.id, exc)

    def _completed_months(self, user_id: str) -> dict[str, int]:
        """{month: qtde de desafios COMPLETED} para o usuário."""
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT month, COUNT(*) FROM user_challenges"
                        " WHERE user_id = :uid AND status = 'COMPLETED'"
                        " GROUP BY month"
                    ),
                    {"uid": user_id},
                ).fetchall()
            return {r[0]: int(r[1]) for r in rows}
        except Exception as exc:
            logger.debug("[ChallengeService] _completed_months user=%s: %s", user_id, exc)
            return {}

    @staticmethod
    def _persist_badges(user_id: str, badges: list[tuple[str, dict]]) -> None:
        if not badges:
            return
        from app.core.database import SessionLocal
        from sqlalchemy import text

        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            for badge_type, meta in badges:
                db.execute(
                    text(
                        "INSERT INTO user_badges (id, user_id, badge_type, earned_at, metadata)"
                        " VALUES (:id, :uid, :bt, :ea, :meta)"
                        " ON CONFLICT (user_id, badge_type) DO NOTHING"
                    ),
                    {
                        "id": str(uuid.uuid4()), "uid": user_id, "bt": badge_type,
                        "ea": now, "meta": json.dumps(meta) if meta else None,
                    },
                )
            db.commit()


_challenge_service: ChallengeService | None = None


def get_challenge_service() -> ChallengeService:
    global _challenge_service
    if _challenge_service is None:
        _challenge_service = ChallengeService()
    return _challenge_service


__all__ = ["Challenge", "ChallengeService", "get_challenge_service"]
