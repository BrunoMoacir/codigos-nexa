"""
app/jobs/market_fees_refresh.py — Job diário 02h15.

Atualiza o baseline VIVO de tarifas de mercado via Open Finance Dados Abertos
(opendata-accounts/personal-accounts) e persiste em
data/fees/market_fees_live.json — o MarketFeesDB (benchmark F5/D4) prefere
esse arquivo quando existe (fallback: tabela estática).

Só sobrescreve quando a fonte é "open_finance" — o fallback estático do
conector nunca é gravado como se fosse baseline vivo.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.jobs._base import job_guard

logger = logging.getLogger(__name__)

_LIVE_FEES_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "fees" / "market_fees_live.json"
)


@job_guard("market_fees_refresh")
async def run_market_fees_refresh() -> None:
    from app.costs.connectors.open_finance_fees import OpenFinanceFeesConnector

    connector = OpenFinanceFeesConnector()
    baseline = connector.get_rates()

    if baseline.get("source") != "open_finance" or not baseline.get("institutions"):
        logger.info(
            "[market_fees_refresh] baseline vivo indisponível (source=%s) — mantendo atual",
            baseline.get("source"),
        )
        return

    payload = {
        "note": "Baseline de tarifas via Open Finance Dados Abertos (job market_fees_refresh).",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "open_finance",
        "institutions": baseline["institutions"],
    }

    _LIVE_FEES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _LIVE_FEES_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(_LIVE_FEES_PATH)

    logger.info(
        "[market_fees_refresh] baseline atualizado: %d instituições",
        len(baseline["institutions"]),
    )
