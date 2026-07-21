"""
app/costs/connectors/open_finance_fees.py — Baseline VIVO de tarifas de
mercado via Open Finance Dados Abertos (opendata-accounts/personal-accounts).

Cada participante do Open Finance é obrigado (Res. BCB) a publicar as tarifas
de serviços prioritários (Res. 3.919: TED, saque, cheque, manutenção...) e os
pacotes padronizados de serviços, com preço por FAIXA e a fração de clientes
em cada faixa (customers.rate). Isso permite calcular a tarifa TÍPICA — o que
o cliente comum paga — e não o teto de tabela.

Saída normalizada por instituição:
  {
    "bank_name": "Santander",              # canonical_brand
    "monthly_package_typical": 23.40,      # mediana dos pacotes (ponderado por faixa)
    "monthly_package_min": 0.0,
    "monthly_package_max": 89.90,
    "services": [
      {"code": "TED_PESSOAL", "name": "...", "typical": 14.85, "max": 24.50},
      ...
    ],
  }

Consumidores: MarketFeesDB (benchmark F5), D4 (mudança unilateral) e o
futuro ranking público de bancos (V3). Job diário: market_fees_refresh.

Mesmo padrão do conector de investimentos do OPP: descoberta via diretório de
participantes, fetch paralelo com paginação, normalização defensiva e
fallback (aqui, a tabela estática do MarketFeesDB).
"""

from __future__ import annotations

import logging
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

_PARTICIPANTS_URL = "https://data.directory.openbankingbrasil.org.br/participants"
_API_FAMILY = "opendata-accounts_personal-accounts"
_ENDPOINT_SUFFIX = "/personal-accounts"

_CACHE_TTL = 6 * 3600
_MAX_INSTITUTIONS = 80
_MAX_PAGES = 3
_MAX_WORKERS = 8
_MIN_INSTITUTIONS_FOR_LIVE = 5   # abaixo disso, catálogo vivo não substitui o estático


class OpenFinanceFeesConnector(BaseConnector):
    """Baseline vivo de tarifas. `transport` injetável para testes."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("cache_ttl_seconds", _CACHE_TTL)
        kwargs.setdefault("timeout_seconds", 10)
        super().__init__(**kwargs)

    # ── BaseConnector ────────────────────────────────────────────────

    def fetch_rates(self) -> dict[str, Any]:
        endpoints = self._discover_endpoints()[:_MAX_INSTITUTIONS]
        if not endpoints:
            raise ConnectorError("Nenhum endpoint de personal-accounts descoberto")

        institutions: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(self._fetch_institution, brand, url): brand
                for brand, url in endpoints
            }
            for future in as_completed(futures):
                try:
                    for inst in future.result():
                        # mesmo banco por vários authorisation servers → mantém
                        # o registro com MAIS serviços (mais completo)
                        key = inst["bank_name"].lower()
                        current = institutions.get(key)
                        if current is None or len(inst["services"]) > len(current["services"]):
                            institutions[key] = inst
                except Exception as exc:
                    logger.debug("[OpenFinanceFees] %s: %s", futures[future], exc)

        result = sorted(institutions.values(), key=lambda i: i["bank_name"].lower())
        if len(result) < _MIN_INSTITUTIONS_FOR_LIVE:
            raise ConnectorError(
                f"Baseline vivo insuficiente ({len(result)} instituições)"
            )
        logger.info("[OpenFinanceFees] baseline vivo: %d instituições", len(result))
        return {"institutions": result, "source": "open_finance"}

    def get_fallback_rates(self) -> dict[str, Any]:
        """Fallback: tabela estática do MarketFeesDB, no mesmo formato."""
        from app.costs.market_fees_db import _BANK_FEES_DB

        return {
            "institutions": [
                {
                    "bank_name": name,
                    "monthly_package_typical": monthly,
                    "monthly_package_min": monthly,
                    "monthly_package_max": monthly,
                    "services": [],
                }
                for name, monthly in _BANK_FEES_DB.items()
            ],
            "source": "static",
        }

    # ── descoberta e fetch ───────────────────────────────────────────

    def _discover_endpoints(self) -> list[tuple[str, str]]:
        import httpx

        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            resp = client.get(_PARTICIPANTS_URL, headers={"Accept": "application/json"})
            resp.raise_for_status()
            participants = resp.json()

        endpoints: list[tuple[str, str]] = []
        seen: set[str] = set()
        for org in participants if isinstance(participants, list) else []:
            org_name = org.get("RegisteredName") or org.get("OrganisationName", "")
            for server in org.get("AuthorisationServers", []) or []:
                brand = server.get("CustomerFriendlyName") or org_name
                for api in server.get("ApiResources", []) or []:
                    if (api.get("ApiFamilyType") or "").lower() != _API_FAMILY:
                        continue
                    for disc in api.get("ApiDiscoveryEndpoints", []) or []:
                        url = disc.get("ApiEndpoint", "")
                        if not url.rstrip("/").endswith(_ENDPOINT_SUFFIX.strip("/")):
                            continue
                        if url in seen:
                            continue
                        seen.add(url)
                        endpoints.append((brand, url))
        return endpoints

    def _fetch_institution(self, brand: str, url: str) -> list[dict]:
        import httpx

        results: list[dict] = []
        next_url: str | None = url
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            for _ in range(_MAX_PAGES):
                if not next_url:
                    break
                resp = client.get(next_url, headers={"Accept": "application/json"})
                resp.raise_for_status()
                payload = resp.json()
                for raw in payload.get("data", []) or []:
                    inst = self._normalize_institution(brand, raw)
                    if inst is not None:
                        results.append(inst)
                links = payload.get("links") or {}
                candidate = links.get("next")
                next_url = candidate if candidate and candidate != next_url else None
        return results

    # ── normalização ─────────────────────────────────────────────────

    @classmethod
    def _normalize_institution(cls, brand: str, raw: dict) -> dict | None:
        from app.opportunities.services.bank_names import canonical_brand

        participant = raw.get("participant") or {}
        name = canonical_brand(
            participant.get("brand") or participant.get("name") or brand
        )

        services = []
        for svc in (raw.get("fees") or {}).get("priorityServices") or []:
            typical = cls._weighted_price(svc.get("prices") or [])
            maximum = cls._money(svc.get("maximum"))
            if typical is None and maximum is None:
                continue
            services.append({
                "code": str(svc.get("code") or svc.get("name") or "").strip(),
                "name": str(svc.get("name") or "").strip(),
                "typical": round(typical if typical is not None else maximum, 2),
                "max": round(maximum, 2) if maximum is not None else None,
            })

        bundle_typicals: list[float] = []
        bundle_values: list[float] = []
        for bundle in raw.get("serviceBundles") or []:
            typical = cls._weighted_price(bundle.get("prices") or [], key="monthlyFee")
            if typical is None:
                typical = cls._weighted_price(bundle.get("prices") or [])
            if typical is not None:
                bundle_typicals.append(typical)
            for bound in ("minimum", "maximum"):
                value = cls._money(bundle.get(bound))
                if value is not None:
                    bundle_values.append(value)

        if not services and not bundle_typicals:
            return None

        # Plausibilidade: pacote mensal acima de R$ 500 é dado publicado errado
        # (valor anual, centavos trocados) — descartado, nunca vira benchmark.
        bundle_typicals = [v for v in bundle_typicals if 0 <= v <= 500]

        return {
            "bank_name": name,
            "monthly_package_typical": (
                round(statistics.median(bundle_typicals), 2) if bundle_typicals else None
            ),
            "monthly_package_min": round(min(bundle_values), 2) if bundle_values else None,
            "monthly_package_max": round(max(bundle_values), 2) if bundle_values else None,
            "services": services,
        }

    @staticmethod
    def _weighted_price(prices: list[dict], key: str = "value") -> float | None:
        """Preço típico: média ponderada pela fração de clientes por faixa."""
        weighted_sum = weight_sum = 0.0
        values: list[float] = []
        for price in prices:
            try:
                value = float(price.get(key) or 0)
                share = float(((price.get("customers") or {}).get("rate")) or 0)
            except (TypeError, ValueError):
                continue
            values.append(value)
            if share > 0:
                weighted_sum += value * share
                weight_sum += share
        if weight_sum > 0:
            return weighted_sum / weight_sum
        if values:
            return statistics.median(values)
        return None

    @staticmethod
    def _money(node) -> float | None:
        if isinstance(node, dict):
            node = node.get("value")
        try:
            return float(node) if node is not None else None
        except (TypeError, ValueError):
            return None


__all__ = ["OpenFinanceFeesConnector"]
