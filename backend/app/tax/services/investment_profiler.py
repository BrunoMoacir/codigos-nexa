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
from app.tax.parametros_fiscais import aliquota_de_ganho

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

        application_date = self._parse_date(inv.get("date") or inv.get("purchaseDate"))
        holding_months = self._calc_holding_months(
            inv.get("date") or inv.get("purchaseDate")
        )
        dias = (
            max((date.today() - application_date).days, 0)
            if application_date else max(holding_months, 1) * 30
        )

        estimated_ir = self._estimar_ir(
            calc=calc,
            product_type=product_type,
            is_exempt=is_exempt,
            amount=amount,
            unrealized_gain=unrealized_gain,
            annual_rate=annual_rate,
            holding_months=holding_months,
            dias=dias,
        )

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
            application_date=application_date,
            is_exempt=is_exempt,
            unrealized_gain=unrealized_gain,
            estimated_ir=round(estimated_ir, 2),
            has_come_cotas=has_come_cotas,
            due_date=due_date,
        )

    @staticmethod
    def _estimar_ir(
        *, calc, product_type: str, is_exempt: bool, amount: float,
        unrealized_gain: float, annual_rate: float, holding_months: int, dias: int,
    ) -> float:
        """
        IR devido se a posição fosse resgatada hoje.

        Duas correções sobre a versão anterior:

        1. **A base é o ganho real** (`current_balance − amount`), não um
           rendimento hipotético recalculado da taxa anual sobre o principal.
           Os dois só coincidem quando o saldo segue exatamente a taxa
           contratada.
        2. **A alíquota respeita a classe do ativo.** Tudo passava por
           `calc_ir_on_cdb`, ou seja, pela tabela regressiva de renda fixa:
           uma ação com 3 meses saía com 22,5% quando o devido é 15% linear,
           e um FII saía com a regressiva quando o devido é 20%.

        Quando a fonte não informa saldo (e `unrealized_gain` fica em zero),
        cai no rendimento projetado pela taxa — que é a melhor aproximação
        disponível, e só existe para renda fixa.
        """
        if is_exempt:
            return 0.0

        aliquota = aliquota_de_ganho(product_type, dias)

        if unrealized_gain > 0:
            return round(unrealized_gain * aliquota, 2)

        if unrealized_gain < 0 or annual_rate == 0:
            return 0.0

        try:
            ir_result = calc.calc_ir_on_cdb(
                principal=amount,
                annual_rate_pct=annual_rate,
                holding_months=max(holding_months, 1),
            )
            return round(ir_result.gross_yield_brl * aliquota, 2)
        except Exception:
            return 0.0

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[date]:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(str(date_str)[:10]).date()
        except Exception:
            return None

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
