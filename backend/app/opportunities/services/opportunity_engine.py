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

        # 1. Dinheiro parado
        idle = self._detector.detect(user_id)

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

        return OpportunitiesResponse(
            user_id=user_id,
            idle_amount=idle.idle_amount,
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
    def _get_cdi_annual() -> float:
        try:
            from app.architect.connectors.anbima import AnbimaConnector
            return AnbimaConnector().get_cdi()
        except Exception as exc:
            logger.debug("[OpportunityEngine] CDI fallback: %s", exc)
            return _DEFAULT_CDI_ANNUAL

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
                "Seus gastos estão próximos ou acima da renda nos últimos 3 meses — "
                "não há saldo ocioso identificado. Reduza despesas variáveis para "
                "criar margem de investimento."
            )

        if top is None:
            return (
                f"Você tem aproximadamente R$ {idle_amount:,.2f} parado por mês, "
                f"perdendo R$ {monthly_loss:,.2f}/mês em rendimento. "
                "Conecte mais dados para ver recomendações personalizadas."
            )

        liquidity_label = (
            "com liquidez diária" if top.liquidity_days <= 1
            else f"com prazo de {top.liquidity} — planeje não precisar desse valor"
        )

        return (
            f"Você tem aproximadamente R$ {idle_amount:,.2f} parado por mês, "
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
