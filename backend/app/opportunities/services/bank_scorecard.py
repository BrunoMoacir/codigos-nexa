"""
app/opportunities/services/bank_scorecard.py

V2 (docs/OPP.md §8.2) — scorecard por banco: "de todos os bancos, qual
paga mais pelo meu perfil?", "meu banco atual está entre os piores?",
"vale abrir conta em outro banco só pela taxa?".

Agregação por instituição sobre o ranking do BankComparator — reaproveita
IRPFCalculator (via BankComparator.rank) para o retorno líquido de cada
produto; não recalcula IR aqui. O ajuste a risco aplica a penalidade de
issuer_risk sobre o retorno líquido anual.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.opportunities.calculators.issuer_risk import (
    issuer_tier,
    liquidity_bucket,
    risk_penalty,
)
from app.opportunities.models import (
    BankComparisonResponse,
    BankScorecardEntry,
    OpportunityItem,
)
from app.opportunities.services.bank_comparator import BankComparator

logger = logging.getLogger(__name__)

# Ganho mínimo (R$/ano líquido) para valer a sugestão de abrir conta em
# outro banco — abaixo disso a resposta não sugere movimentação.
_MIN_SWITCH_GAIN_BRL = 50.0


class BankScorecardService:
    """
    Ranking agregado por banco, com ajuste a risco por tier do emissor
    e cruzamento com o banco atual do usuário (pluggy_items.connector_name).
    """

    def __init__(self, comparator: BankComparator | None = None) -> None:
        self._comparator = comparator or BankComparator()

    def build(
        self,
        user_id: str,
        amount: float,
        holding_months: int,
        cdi_annual: float,
        selic_annual: float | None = None,
        disclaimer: str = "",
    ) -> BankComparisonResponse:
        ranked = self._comparator.rank(
            amount=amount,
            holding_months=holding_months,
            cdi_annual=cdi_annual,
            selic_annual=selic_annual,
        )
        user_banks = self._get_user_banks(user_id)

        scorecard = self._aggregate_by_bank(ranked, user_banks, amount, holding_months)
        scorecard.sort(key=lambda e: -e.best_risk_adjusted_brl)

        best_by_liquidity = self._best_by_liquidity(ranked)

        current = next((e for e in scorecard if e.is_user_current_bank), None)
        current_rank = scorecard.index(current) + 1 if current else None

        switch_gain = 0.0
        suggestion: Optional[str] = None
        if scorecard:
            best = scorecard[0]
            if current and best.bank_name != current.bank_name:
                switch_gain = round(best.best_net_return_brl - current.best_net_return_brl, 2)
            elif current is None:
                switch_gain = round(best.best_net_return_brl, 2)

            if not best.is_user_current_bank and switch_gain >= _MIN_SWITCH_GAIN_BRL:
                suggestion = (
                    f"Abrir conta no {best.bank_name} renderia cerca de "
                    f"R$ {switch_gain:,.2f}/ano a mais que "
                    + (f"o seu banco atual ({current.bank_name})" if current else "deixar o dinheiro parado")
                    + f" para R$ {amount:,.2f} em {holding_months} meses."
                )

        return BankComparisonResponse(
            user_id=user_id,
            amount=amount,
            holding_months=holding_months,
            cdi_annual_pct=round(cdi_annual * 100, 4),
            scorecard=scorecard,
            best_by_liquidity=best_by_liquidity,
            user_current_bank=current.bank_name if current else None,
            user_current_bank_rank=current_rank,
            switch_gain_brl=switch_gain,
            open_account_suggestion=suggestion,
            disclaimer=disclaimer,
            generated_at=datetime.now(timezone.utc),
        )

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _aggregate_by_bank(
        ranked: list[OpportunityItem],
        user_banks: set[str],
        amount: float,
        holding_months: int,
    ) -> list[BankScorecardEntry]:
        by_bank: dict[str, list[OpportunityItem]] = {}
        for item in ranked:
            by_bank.setdefault(item.bank_name, []).append(item)

        entries: list[BankScorecardEntry] = []
        for bank_name, items in by_bank.items():
            eligible = [i for i in items if i.eligible] or items
            best = max(eligible, key=lambda i: i.annual_gain_brl)
            tier = issuer_tier(bank_name) if bank_name != "Tesouro Direto" else 1
            # penalidade = risk_penalty p.p. a.a. sobre o principal, no período
            penalty_brl = amount * risk_penalty(tier) * (holding_months / 12)
            risk_adjusted = round(best.annual_gain_brl - penalty_brl, 2)

            entries.append(BankScorecardEntry(
                bank_name=bank_name,
                best_product_type=best.product_type,
                best_cdi_pct=best.cdi_pct,
                best_net_annual_rate_pct=best.annual_rate_net_pct,
                best_net_return_brl=best.annual_gain_brl,
                best_risk_adjusted_brl=risk_adjusted,
                risk_tier=tier,
                product_count=len(items),
                fgc_covered=any(i.fgc_covered for i in items),
                is_user_current_bank=BankScorecardService._matches_user_bank(
                    bank_name, user_banks
                ),
            ))
        return entries

    @staticmethod
    def _best_by_liquidity(ranked: list[OpportunityItem]) -> dict[str, str]:
        best: dict[str, str] = {}
        for item in ranked:
            if not item.eligible:
                continue
            bucket = liquidity_bucket(item.liquidity_days, item.liquidity)
            if bucket not in best:
                best[bucket] = item.bank_name
        return best

    @staticmethod
    def _matches_user_bank(bank_name: str, user_banks: set[str]) -> bool:
        """Match tolerante: connector_name do Pluggy raramente é idêntico ao
        bank_name do catálogo (ex: 'Nubank' vs 'Nu Pagamentos S.A.')."""
        _STOPWORDS = {"banco", "s.a.", "sa", "s/a", "de", "do", "da", "brasil"}

        def _tokens(name: str) -> list[str]:
            return [t for t in name.lower().split() if t not in _STOPWORDS and len(t) >= 2]

        bank_lower = bank_name.lower()
        bank_tokens = _tokens(bank_name)
        for connector in user_banks:
            c = connector.lower()
            if bank_lower in c or c in bank_lower:
                return True
            # tokens significativos com match exato ou por prefixo
            # (ex: "nu" de "Nu Pagamentos" é prefixo de "nubank")
            for ct in _tokens(connector):
                for bt in bank_tokens:
                    if ct == bt or bt.startswith(ct) or ct.startswith(bt):
                        return True
        return False

    @staticmethod
    def _get_user_banks(user_id: str) -> set[str]:
        """Bancos conectados do usuário via pluggy_items.connector_name.
        Falha silenciosamente → set() (nenhum banco marcado como atual)."""
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT DISTINCT connector_name FROM pluggy_items"
                        " WHERE user_id = :uid AND connector_name IS NOT NULL"
                    ),
                    {"uid": user_id},
                ).fetchall()
            return {r[0] for r in rows if r[0]}
        except Exception as exc:
            logger.warning("[BankScorecard] get_user_banks user=%s: %s", user_id, exc)
            return set()


__all__ = ["BankScorecardService"]
