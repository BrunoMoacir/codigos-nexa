"""
app/jobs/product_catalog_refresh.py — Job diário 02h30 (OPP V2, Etapa 3)

Atualiza o catálogo vivo de produtos de renda fixa via Open Finance Dados
Abertos e fontes suplementares explicitamente configuradas e persiste em
app/opportunities/data/product_catalog.json — o BankComparator prefere esse
arquivo quando existe (fallback: catálogo curado backend/data/bank_products.json).

O arquivo só é sobrescrito quando o fetch retorna ofertas vivas
("open_finance" ou "open_finance+supplemental"). O fallback curado nunca é
gravado como se fosse catálogo vivo.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.jobs._base import job_guard

logger = logging.getLogger(__name__)

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1] / "opportunities" / "data" / "product_catalog.json"
)


@job_guard("product_catalog_refresh")
async def run_product_catalog_refresh() -> None:
    from app.opportunities.connectors.open_finance_products import (
        OpenFinanceProductsConnector,
    )

    connector = OpenFinanceProductsConnector()
    catalog = connector.get_rates()

    if catalog.get("source") not in {"open_finance", "open_finance+supplemental"} or not catalog.get("products"):
        logger.info(
            "[product_catalog_refresh] catálogo vivo indisponível (source=%s) — "
            "mantendo catálogo atual",
            catalog.get("source"),
        )
        return

    products = catalog["products"]
    payload = {
        "note": "Catálogo normalizado via Open Finance Dados Abertos (job product_catalog_refresh).",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "open_finance",
        "products": products,
    }

    _CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _CATALOG_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(_CATALOG_PATH)

    institutions = {p.get("bank_name") for p in products}
    logger.info(
        "[product_catalog_refresh] catálogo atualizado: %d produtos de %d instituições",
        len(products), len(institutions),
    )
