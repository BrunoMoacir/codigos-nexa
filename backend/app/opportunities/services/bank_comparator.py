"""
app/opportunities/services/bank_comparator.py

Compara CDB/LCI/LCA de múltiplos bancos (e Tesouro SELIC) para um dado
montante e prazo. Ranqueia por annual_rate_net_pct (após IR) — não pela
taxa bruta.

Catálogo (ordem de preferência):
  1. app/opportunities/data/product_catalog.json — cache normalizado
     alimentado pelo job de refresh do Open Finance (V2, docs/OPP.md §4)
  2. backend/data/bank_products.json — catálogo curado (fallback)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.opportunities.models import OpportunityItem
from app.opportunities.services.switch_steps import build_switch_steps

logger = logging.getLogger(__name__)

_CURATED_CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "bank_products.json"
_LIVE_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "product_catalog.json"

# Ticket OPP1-B/seção 5.4 do plano (docs/OPP1_DINHEIRO_PARADO_PLANO.md): para
# perfis financeiramente frágeis, produtos sem liquidez diária não devem
# aparecer acima de produtos com liquidez diária, mesmo com taxa líquida maior.
_FRAGILE_FSS_LEVELS = {"ALERTA", "CRITICO"}

# OPP.3 — produto sintético de Tesouro Selic incluído no ranking quando
# selic_annual é conhecida. Tesouro tem garantia soberana (não FGC).
_TESOURO_MIN_AMOUNT = 150.0
_TESOURO_LIQUIDITY_DAYS = 1


class BankComparator:
    """
    Carrega o catálogo de produtos bancários e calcula o ranking
    de rentabilidade líquida para um montante e prazo informados.

    Uso:
        comparator = BankComparator()
        ranking = comparator.rank(amount=10_000, holding_months=12, cdi_annual=0.1465)
    """

    # Revalidação do catálogo: além do mtime (detecta o arquivo novo gravado
    # pelo job product_catalog_refresh sem reiniciar o processo), um TTL de
    # segurança força re-stat/reload periódico mesmo se o mtime não mudar.
    _CATALOG_TTL_SECONDS = 15 * 60

    def __init__(self) -> None:
        self._catalog: list[dict] = []
        self._catalog_path: Path | None = None
        self._catalog_mtime: float = 0.0
        self._catalog_loaded_at: float = 0.0
        self._refresh_catalog()

    def _refresh_catalog(self) -> None:
        """Recarrega o catálogo quando o arquivo em uso mudou (mtime), quando
        o arquivo preferencial passou a existir/deixou de existir, ou quando o
        TTL expirou. Instâncias singleton (router) passam a enxergar o catálogo
        novo do job diário sem restart — correção do gap de invalidação."""
        import time

        now = time.monotonic()
        if self._catalog and (now - self._catalog_loaded_at) < self._CATALOG_TTL_SECONDS:
            return

        path = next((p for p in (_LIVE_CATALOG_PATH, _CURATED_CATALOG_PATH) if p.exists()), None)
        try:
            mtime = path.stat().st_mtime if path else 0.0
        except OSError:
            mtime = 0.0

        if self._catalog and path == self._catalog_path and mtime == self._catalog_mtime:
            self._catalog_loaded_at = now  # nada mudou — só renova o TTL
            return

        self._catalog = self._load_catalog()
        self._catalog_path = path
        self._catalog_mtime = mtime
        self._catalog_loaded_at = now

    def rank(
        self,
        amount: float,
        holding_months: int,
        cdi_annual: float,   # decimal, ex: 0.1465 para 14.65%
        fss_level: str | None = None,
        selic_annual: float | None = None,
    ) -> list[OpportunityItem]:
        """
        Retorna todos os produtos ranqueados por taxa líquida anual.

        Produtos com min_amount > amount são marcados como eligible=False
        mas ainda aparecem no resultado (informação útil para o usuário).

        fss_level: quando "ALERTA" ou "CRITICO" (perfil financeiramente
        frágil — ConsumptionProfiler), produtos sem liquidez diária são
        rebaixados abaixo de produtos com liquidez diária, mesmo que
        rendam mais líquido — ver plano OPP.1, seção 5.4.

        selic_annual: quando informada (decimal), inclui Tesouro SELIC no
        ranking (OPP.3) — IR regressivo + custódia B3 via IRPFCalculator.
        """
        from app.fiscal.ir_pf_calculator import IRPFCalculator

        self._refresh_catalog()
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

        if selic_annual is not None and selic_annual > 0:
            try:
                tesouro = self._evaluate_tesouro_selic(
                    amount=amount,
                    holding_months=holding_months,
                    cdi_annual=cdi_annual,
                    selic_annual=selic_annual,
                    ir_calc=ir_calc,
                )
                results.append((tesouro.annual_rate_net_pct, tesouro))
            except Exception as exc:
                logger.debug("[BankComparator] tesouro selic: %s", exc)

        prioritize_daily_liquidity = fss_level in _FRAGILE_FSS_LEVELS

        def _sort_key(entry: tuple[float, OpportunityItem]):
            net_rate, item = entry
            if prioritize_daily_liquidity:
                return (not item.eligible, item.liquidity_days > 1, -net_rate)
            return (not item.eligible, -net_rate)

        # Ordena por taxa líquida descrescente; eligible primeiro (e, para
        # perfis frágeis, liquidez diária primeiro dentro de cada grupo)
        results.sort(key=_sort_key)

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
        ptype: str = product["product_type"]
        cdi_pct: float = product["cdi_pct"]

        annual_gross_pct = round(cdi_pct / 100 * cdi_annual * 100, 4)

        is_exempt = ptype in ("LCI", "LCA")
        eligible = amount >= product["min_amount"]
        fgc_covered = bool(product.get("fgc_covered", True))

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
            index=product.get("index", "CDI"),
            fgc_covered=fgc_covered,
            steps=build_switch_steps(
                bank_name=product["bank_name"],
                product_type=ptype,
                liquidity_days=product["liquidity_days"],
                min_amount=product["min_amount"],
                is_exempt=is_exempt,
                fgc_covered=fgc_covered,
                amount=amount,
            ),
        )

    def _evaluate_tesouro_selic(
        self,
        amount: float,
        holding_months: int,
        cdi_annual: float,
        selic_annual: float,
        ir_calc,
    ) -> OpportunityItem:
        """OPP.3 — Tesouro Selic como item do ranking. cdi_pct é o
        equivalente em % do CDI (só para exibição comparável)."""
        ir_result = ir_calc.calc_ir_on_tesouro_selic(
            principal=amount,
            selic_annual=selic_annual,
            holding_months=holding_months,
        )

        net_annual_pct = ir_result.net_annual_rate_pct
        monthly_gain = round(amount * ((1 + net_annual_pct / 100) ** (1 / 12) - 1), 2)
        cdi_equivalent_pct = round(selic_annual / cdi_annual * 100, 2) if cdi_annual > 0 else 100.0

        return OpportunityItem(
            rank=0,
            bank_name="Tesouro Direto",
            product_type="TESOURO_SELIC",
            rating="Soberano",
            cdi_pct=cdi_equivalent_pct,
            annual_rate_gross_pct=round(selic_annual * 100, 4),
            annual_rate_net_pct=round(net_annual_pct, 4),
            ir_rate=ir_result.ir_rate,
            is_exempt=False,
            min_amount=_TESOURO_MIN_AMOUNT,
            liquidity="daily",
            liquidity_days=_TESOURO_LIQUIDITY_DAYS,
            monthly_gain_brl=monthly_gain,
            annual_gain_brl=round(ir_result.net_yield_brl, 2),
            eligible=amount >= _TESOURO_MIN_AMOUNT,
            index="SELIC",
            fgc_covered=False,  # garantia soberana (Tesouro Nacional), não FGC
            steps=build_switch_steps(
                bank_name="Tesouro Direto",
                product_type="TESOURO_SELIC",
                liquidity_days=_TESOURO_LIQUIDITY_DAYS,
                min_amount=_TESOURO_MIN_AMOUNT,
                is_exempt=False,
                fgc_covered=False,
                amount=amount,
            ),
        )

    @staticmethod
    def _load_catalog() -> list[dict]:
        for path, label in ((_LIVE_CATALOG_PATH, "live"), (_CURATED_CATALOG_PATH, "curated")):
            try:
                if not path.exists():
                    continue
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                products = data.get("products", [])
                if products:
                    logger.debug("[BankComparator] catálogo %s: %d produtos", label, len(products))
                    return products
            except Exception as exc:
                logger.error("[BankComparator] falha ao carregar catálogo %s: %s", label, exc)
        return []

    @staticmethod
    def catalog_metadata() -> dict:
        """Metadados do catálogo em uso (para GET /opportunities/products)."""
        for path, source in ((_LIVE_CATALOG_PATH, "open_finance"), (_CURATED_CATALOG_PATH, "curated")):
            try:
                if not path.exists():
                    continue
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("products"):
                    return {
                        "updated_at": data.get("updated_at", "unknown"),
                        "source": data.get("source", source),
                        "products": data["products"],
                    }
            except Exception as exc:
                logger.error("[BankComparator] catalog_metadata %s: %s", source, exc)
        return {"updated_at": "unknown", "source": "curated", "products": []}
