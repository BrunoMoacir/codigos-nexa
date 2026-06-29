"""
app/tax/services/investment_profiler.py

Obtém posições de investimento da Pluggy (Open Finance) e as converte
em InvestmentPosition com IR estimado para cada posição.

Pluggy investment subtypes mapeados:
  FIXED_INCOME  → CDB, LCI, LCA, CRI, CRA, DEBENTURE, LF, TESOURO
  FUND          → FIXED_INCOME_FUND (come-cotas), MULTI_MARKET_FUND (come-cotas), STOCK_FUND
  EQUITY        → ACAO, FII, ETF
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from app.tax.models import InvestmentPosition

logger = logging.getLogger(__name__)

_EXEMPT_SUBTYPES = frozenset({"LCI", "LCA", "CRI", "CRA", "DEBENTURE_INCENTIVADA", "POUPANCA"})

# Come-cotas: IR antecipado em maio e novembro para esses tipos de fundo
_COME_COTAS_SUBTYPES = frozenset({
    "FIXED_INCOME_FUND", "MULTI_MARKET_FUND", "FUND",
    "FIXED_INCOME", "BALANCED",  # alguns conectores Pluggy usam esses nomes
})

# Mapeia subtype Pluggy → product_type Nexa
_SUBTYPE_MAP: dict[str, str] = {
    "CDB": "CDB",
    "LCI": "LCI",
    "LCA": "LCA",
    "CRI": "CRI",
    "CRA": "CRA",
    "DEBENTURE": "DEBENTURE",
    "DEBENTURE_INCENTIVADA": "DEBENTURE_INCENTIVADA",
    "LF": "LF",
    "LFT": "TESOURO",
    "LTN": "TESOURO",
    "NTN-B": "TESOURO",
    "NTN-F": "TESOURO",
    "TESOURO_SELIC": "TESOURO",
    "TESOURO_PREFIXADO": "TESOURO",
    "TESOURO_IPCA": "TESOURO",
    "FIXED_INCOME_FUND": "FUNDO_RF",
    "MULTI_MARKET_FUND": "FUNDO_MM",
    "STOCK_FUND": "FUNDO_ACOES",
    "FIA": "FUNDO_ACOES",
    "FII": "FII",
    "STOCK": "ACAO",
    "ETF": "ETF",
    "POUPANCA": "POUPANCA",
}


class InvestmentProfiler:
    """
    Mapeia carteira de investimentos via Pluggy para posições com IR calculado.
    """

    def get_portfolio(self, user_id: str) -> list[InvestmentPosition]:
        item_ids = self._get_user_item_ids(user_id)
        if not item_ids:
            logger.info("[InvestmentProfiler] user=%s sem item_ids Pluggy.", user_id)
            return []

        positions: list[InvestmentPosition] = []
        for item_id in item_ids:
            try:
                raw = self._fetch_investments(item_id)
                positions.extend(self._parse_investments(raw))
            except Exception as exc:
                logger.warning(
                    "[InvestmentProfiler] user=%s item=%s: %s", user_id, item_id, exc
                )

        return positions

    # ── helpers privados ──────────────────────────────────────────────

    def _get_user_item_ids(self, user_id: str) -> list[str]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text("SELECT item_id FROM pluggy_items WHERE user_id = :uid"),
                    {"uid": user_id},
                ).fetchall()
            return [r[0] for r in rows]
        except Exception as exc:
            logger.warning("[InvestmentProfiler] get_item_ids user=%s: %s", user_id, exc)
            return []

    def _fetch_investments(self, item_id: str) -> list[dict]:
        from app.core.integrations.pluggy import PluggyClient

        client = PluggyClient()
        resp = client.get_investments(item_id)
        return resp.get("results", [])

    def _parse_investments(self, results: list[dict]) -> list[InvestmentPosition]:
        from app.fiscal.ir_pf_calculator import IRPFCalculator

        calc = IRPFCalculator()
        positions: list[InvestmentPosition] = []

        for inv in results:
            try:
                positions.append(self._map_one(inv, calc))
            except Exception as exc:
                logger.debug("[InvestmentProfiler] skip investment %s: %s", inv.get("id"), exc)

        return positions

    def _map_one(self, inv: dict, calc) -> InvestmentPosition:
        subtype = (inv.get("subtype") or inv.get("type") or "UNKNOWN").upper()
        product_type = _SUBTYPE_MAP.get(subtype, subtype)
        is_exempt = subtype in _EXEMPT_SUBTYPES
        has_come_cotas = subtype in _COME_COTAS_SUBTYPES and not is_exempt

        amount = float(inv.get("amount") or inv.get("value") or 0)
        balance = float(inv.get("balance") or amount)
        unrealized_gain = round(balance - amount, 2)

        annual_rate = float(
            inv.get("fixedAnnualRate") or inv.get("annualRate") or inv.get("lastTwelveMonthsRate") or 0
        )

        holding_months = self._calc_holding_months(
            inv.get("date") or inv.get("purchaseDate")
        )

        if is_exempt or annual_rate == 0:
            estimated_ir = 0.0
        else:
            try:
                ir_result = calc.calc_ir_on_cdb(
                    principal=amount,
                    annual_rate_pct=annual_rate,
                    holding_months=max(holding_months, 1),
                )
                estimated_ir = ir_result.ir_brl
            except Exception:
                estimated_ir = 0.0

        due_date: Optional[date] = None
        if inv.get("dueDate"):
            try:
                due_date = datetime.fromisoformat(inv["dueDate"][:10]).date()
            except Exception:
                pass

        bank_name = (
            inv.get("issuerName") or inv.get("institutionName") or "Desconhecido"
        )
        product_name = inv.get("name") or f"{product_type} {bank_name}"

        return InvestmentPosition(
            bank_name=bank_name,
            product_name=product_name,
            product_type=product_type,
            amount=round(amount, 2),
            current_balance=round(balance, 2),
            annual_rate_pct=round(annual_rate, 4),
            holding_months=holding_months,
            is_exempt=is_exempt,
            unrealized_gain=unrealized_gain,
            estimated_ir=round(estimated_ir, 2),
            has_come_cotas=has_come_cotas,
            due_date=due_date,
        )

    @staticmethod
    def _calc_holding_months(date_str: Optional[str]) -> int:
        if not date_str:
            return 1
        try:
            purchase = datetime.fromisoformat(date_str[:10]).date()
            today = date.today()
            return max(1, (today.year - purchase.year) * 12 + today.month - purchase.month)
        except Exception:
            return 1
