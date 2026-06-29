"""
app/opportunities/services/bank_comparator.py

Compara CDB/LCI/LCA de múltiplos bancos para um dado montante e prazo.
Ranqueia por annual_rate_net_pct (após IR) — não pela taxa bruta.
Catálogo em backend/data/bank_products.json (taxas em % do CDI).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.opportunities.models import OpportunityItem

logger = logging.getLogger(__name__)

_CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "bank_products.json"


class BankComparator:
    """
    Carrega o catálogo de produtos bancários e calcula o ranking
    de rentabilidade líquida para um montante e prazo informados.

    Uso:
        comparator = BankComparator()
        ranking = comparator.rank(amount=10_000, holding_months=12, cdi_annual=0.1465)
    """

    def __init__(self) -> None:
        self._catalog: list[dict] = self._load_catalog()

    def rank(
        self,
        amount: float,
        holding_months: int,
        cdi_annual: float,   # decimal, ex: 0.1465 para 14.65%
    ) -> list[OpportunityItem]:
        """
        Retorna todos os produtos ranqueados por taxa líquida anual.

        Produtos com min_amount > amount são marcados como eligible=False
        mas ainda aparecem no resultado (informação útil para o usuário).
        """
        from app.fiscal.ir_pf_calculator import IRPFCalculator

        ir_calc = IRPFCalculator()
        results: list[tuple[float, OpportunityItem]] = []

        for product in self._catalog:
            try:
                item = self._evaluate(
                    product=product,
                    amount=amount,
                    holding_months=holding_months,
                    cdi_annual=cdi_annual,
                    ir_calc=ir_calc,
                )
                results.append((item.annual_rate_net_pct, item))
            except Exception as exc:
                logger.debug("[BankComparator] produto %s/%s: %s",
                             product.get("bank_name"), product.get("product_type"), exc)

        # Ordena por taxa líquida descrescente; eligible primeiro
        results.sort(key=lambda t: (not t[1].eligible, -t[0]))

        return [
            OpportunityItem(**{**item.model_dump(), "rank": i + 1})
            for i, (_, item) in enumerate(results)
        ]

    # ── helpers ──────────────────────────────────────────────────────

    def _evaluate(
        self,
        product: dict,
        amount: float,
        holding_months: int,
        cdi_annual: float,
        ir_calc,
    ) -> OpportunityItem:
        from app.fiscal.ir_pf_calculator import InvestmentType

        ptype: str = product["product_type"]
        cdi_pct: float = product["cdi_pct"]

        annual_gross_pct = round(cdi_pct / 100 * cdi_annual * 100, 4)

        is_exempt = ptype in ("LCI", "LCA")
        eligible = amount >= product["min_amount"]

        if is_exempt:
            ir_result = ir_calc.calc_ir_on_lci_lca(
                principal=amount,
                annual_rate_pct=annual_gross_pct,
                holding_months=holding_months,
                investment_type=ptype,  # type: ignore[arg-type]
            )
        else:
            ir_result = ir_calc.calc_ir_on_cdb(
                principal=amount,
                annual_rate_pct=annual_gross_pct,
                holding_months=holding_months,
            )

        net_annual_pct = ir_result.net_annual_rate_pct
        monthly_gain = round(amount * ((1 + net_annual_pct / 100) ** (1 / 12) - 1), 2)
        annual_gain = round(ir_result.net_yield_brl, 2)

        return OpportunityItem(
            rank=0,  # assigned after sorting
            bank_name=product["bank_name"],
            product_type=ptype,
            rating=product.get("rating", "N/A"),
            cdi_pct=cdi_pct,
            annual_rate_gross_pct=annual_gross_pct,
            annual_rate_net_pct=round(net_annual_pct, 4),
            ir_rate=ir_result.ir_rate,
            is_exempt=is_exempt,
            min_amount=product["min_amount"],
            liquidity=product.get("liquidity", "N/A"),
            liquidity_days=product["liquidity_days"],
            monthly_gain_brl=monthly_gain,
            annual_gain_brl=annual_gain,
            eligible=eligible,
        )

    @staticmethod
    def _load_catalog() -> list[dict]:
        try:
            with open(_CATALOG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("products", [])
        except Exception as exc:
            logger.error("[BankComparator] falha ao carregar catálogo: %s", exc)
            return []
