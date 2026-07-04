"""
app/opportunities/services/opportunity_engine.py

Orquestra IdleMoneyDetector + BankComparator e persiste snapshot.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.opportunities.models import OpportunitiesResponse, OpportunityItem
from app.opportunities.services.idle_money_detector import IdleMoneyDetector
from app.opportunities.services.bank_comparator import BankComparator

logger = logging.getLogger(__name__)

_DEFAULT_CDI_ANNUAL = 0.1465   # fallback quando ANBIMA estiver indisponível


class OpportunityEngine:
    """
    Análise completa de oportunidades de investimento para um usuário.

    Fluxo:
      1. IdleMoneyDetector → idle_amount
      2. AnbimaConnector   → cdi_annual
      3. BankComparator    → ranking por taxa líquida
      4. Persiste snapshot em opportunity_snapshots
    """

    def __init__(self) -> None:
        self._detector = IdleMoneyDetector()
        self._comparator = BankComparator()

    def analyze(
        self,
        user_id: str,
        holding_months: int = 12,
        persist_snapshot: bool = True,
    ) -> OpportunitiesResponse:
        now = datetime.now(timezone.utc)

        # 1. Dinheiro parado — busca as transações uma única vez e reaproveita
        #    o mesmo DataFrame para IdleMoneyDetector e ConsumptionProfiler
        #    (Ticket OPP1-B: sem query adicional).
        transactions_df = self._fetch_transactions(user_id)
        user_profile = self._build_user_profile(transactions_df)
        idle = self._detector.detect(
            user_id, transactions_df=transactions_df, user_profile=user_profile
        )

        # 2. CDI atual
        cdi_annual = self._get_cdi_annual()
        cdi_annual_pct = round(cdi_annual * 100, 4)

        # 3. Custo de deixar na conta corrente
        monthly_loss = round(idle.idle_amount * ((1 + cdi_annual) ** (1 / 12) - 1), 2)

        # 4. Ranking de produtos (usa idle_amount para calcular ganho; mínimo R$ 1)
        amount_for_rank = max(idle.idle_amount, 1.0)
        ranked = self._comparator.rank(
            amount=amount_for_rank,
            holding_months=holding_months,
            cdi_annual=cdi_annual,
        )

        top = next((p for p in ranked if p.eligible), None)

        recommendation = self._build_recommendation(
            idle_amount=idle.idle_amount,
            monthly_loss=monthly_loss,
            top=top,
            has_data=idle.has_sufficient_data,
        )

        # 5. Snapshot (falha silenciosamente)
        if persist_snapshot and idle.idle_amount > 0:
            self._persist_snapshot(
                user_id=user_id,
                idle_amount=idle.idle_amount,
                monthly_loss=monthly_loss,
                top_opportunity=f"{top.bank_name} {top.product_type} {top.cdi_pct:.0f}% CDI" if top else None,
                top_gain_brl=top.monthly_gain_brl if top else None,
                cdi_at_capture=round(cdi_annual, 4),
                now=now,
            )

        recommendation = self._append_reserve_note(recommendation, idle)

        return OpportunitiesResponse(
            user_id=user_id,
            idle_amount=idle.idle_amount,
            gross_idle_amount=idle.gross_idle_amount,
            emergency_reserve=idle.emergency_reserve,
            reserve_months_applied=idle.reserve_months_applied,
            avg_income_3m=idle.avg_income_3m,
            avg_expenses_3m=idle.avg_expenses_3m,
            monthly_loss_in_checking=monthly_loss,
            cdi_annual_pct=cdi_annual_pct,
            top_opportunity=top,
            opportunities=ranked,
            recommendation=recommendation,
            generated_at=now,
        )

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _fetch_transactions(user_id: str):
        try:
            from app.core.db.queries import get_transactions_for_user
            return get_transactions_for_user(user_id)
        except Exception as exc:
            logger.error("[OpportunityEngine] get_transactions user=%s: %s", user_id, exc)
            import polars as pl
            return pl.DataFrame()

    @staticmethod
    def _build_user_profile(transactions_df):
        """Constrói o UserProfile (fss_level) para a reserva de emergência —
        Ticket OPP1-B. Reaproveita o transactions_df já buscado; retorna None
        quando não há dados ou o profiler falha (reserva não é aplicada nesse caso)."""
        if transactions_df is None or transactions_df.is_empty():
            return None
        try:
            from app.optimizer.profiler import ConsumptionProfiler
            return ConsumptionProfiler().build(transactions_df)
        except Exception as exc:
            logger.debug("[OpportunityEngine] ConsumptionProfiler indisponível: %s", exc)
            return None

    @staticmethod
    def _get_cdi_annual() -> float:
        try:
            from app.architect.connectors.anbima import AnbimaConnector
            return AnbimaConnector().get_cdi()
        except Exception as exc:
            logger.debug("[OpportunityEngine] CDI fallback: %s", exc)
            return _DEFAULT_CDI_ANNUAL

    @staticmethod
    def _append_reserve_note(recommendation: str, idle) -> str:
        """Explica por que o valor sugerido é menor do que o usuário 'acha' que
        tem sobrando, quando parte do saldo foi protegida como reserva."""
        if idle.emergency_reserve <= 0:
            return recommendation
        return (
            f"{recommendation} "
            f"R$ {idle.emergency_reserve:,.2f} foram mantidos de fora como reserva "
            f"de emergência (equivalente a {idle.reserve_months_applied} meses de "
            "gastos) e não entram nessa recomendação."
        )

    @staticmethod
    def _build_recommendation(
        idle_amount: float,
        monthly_loss: float,
        top: Optional[OpportunityItem],
        has_data: bool,
    ) -> str:
        if not has_data:
            return (
                "Histórico de transações insuficiente para calcular dinheiro parado. "
                "Mantenha sua conta conectada por pelo menos 2 meses para receber "
                "recomendações personalizadas."
            )

        if idle_amount <= 0:
            return (
                "Não há saldo ocioso identificado além da sua reserva de segurança. "
                "Reduza despesas variáveis ou aumente a renda para criar margem de "
                "investimento."
            )

        if top is None:
            return (
                f"Você tem aproximadamente R$ {idle_amount:,.2f} parado na conta, "
                f"perdendo R$ {monthly_loss:,.2f}/mês em rendimento. "
                "Conecte mais dados para ver recomendações personalizadas."
            )

        liquidity_label = (
            "com liquidez diária" if top.liquidity_days <= 1
            else f"com prazo de {top.liquidity} — planeje não precisar desse valor"
        )

        return (
            f"Você tem aproximadamente R$ {idle_amount:,.2f} parado na conta, "
            f"perdendo R$ {monthly_loss:,.2f}/mês. "
            f"Melhor opção: {top.bank_name} {top.product_type} {top.cdi_pct:.0f}% CDI "
            f"({top.annual_rate_net_pct:.2f}% a.a. líquido), "
            f"{liquidity_label}. "
            f"Rendimento estimado: R$ {top.monthly_gain_brl:,.2f}/mês ou "
            f"R$ {top.annual_gain_brl:,.2f}/ano."
        )

    @staticmethod
    def _persist_snapshot(
        user_id: str,
        idle_amount: float,
        monthly_loss: float,
        top_opportunity: Optional[str],
        top_gain_brl: Optional[float],
        cdi_at_capture: float,
        now: datetime,
    ) -> None:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                db.execute(
                    text(
                        "INSERT INTO opportunity_snapshots"
                        "   (id, user_id, captured_at, idle_amount, monthly_loss,"
                        "    top_opportunity, top_gain_brl, cdi_at_capture)"
                        " VALUES (:id, :uid, :ts, :idle, :loss, :top, :gain, :cdi)"
                    ),
                    {
                        "id":   str(uuid.uuid4()),
                        "uid":  user_id,
                        "ts":   now,
                        "idle": idle_amount,
                        "loss": monthly_loss,
                        "top":  top_opportunity,
                        "gain": top_gain_brl,
                        "cdi":  cdi_at_capture,
                    },
                )
                db.commit()
        except Exception as exc:
            logger.warning("[OpportunityEngine] persist_snapshot user=%s: %s", user_id, exc)
