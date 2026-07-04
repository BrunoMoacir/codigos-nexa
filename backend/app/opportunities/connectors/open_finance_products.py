"""
app/opportunities/connectors/open_finance_products.py

V2 (docs/OPP.md §3.3/§7, Etapa 3) — conector para os Dados Abertos de
investimentos do Open Finance Brasil.

Não requer consentimento do usuário — são ofertas públicas das instituições,
padronizadas por regulação do BACEN. O fluxo:

  1. Diretório de participantes (data.directory.openbankingbrasil.org.br)
     → descobre os endpoints `opendata-investments/bank-fixed-incomes`
       de cada instituição participante.
  2. Busca as ofertas de CDB/RDB/LCI/LCA de cada endpoint (limitado a
     _MAX_INSTITUTIONS por execução — o job de refresh roda diariamente).
  3. Normaliza para o schema interno de bank_products.json (bank_name,
     product_type, cdi_pct, min_amount, liquidity, liquidity_days, ...).

Fallback (get_fallback_rates): catálogo curado backend/data/bank_products.json
— o OPP nunca fica sem catálogo, mesmo com o diretório fora do ar.

A estrutura da API de dados abertos é verbosa e varia em detalhes entre
instituições; a normalização é defensiva (best-effort com múltiplas chaves
candidatas) e descarta silenciosamente produtos que não consegue interpretar.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

_CURATED_CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "bank_products.json"

_PARTICIPANTS_URL = "https://data.directory.openbankingbrasil.org.br/participants"
_API_FAMILY = "opendata-investments_bank-fixed-incomes"
_ENDPOINT_SUFFIX = "/bank-fixed-incomes"

_CACHE_TTL = 6 * 3600          # 6h — ofertas públicas não mudam a cada minuto
_MAX_INSTITUTIONS = 20         # limite por execução (job diário completa a cobertura)
_MIN_PRODUCTS_FOR_LIVE = 8     # abaixo disso o catálogo vivo não substitui o curado

_SUPPORTED_TYPES = {"CDB", "RDB", "LCI", "LCA"}


class OpenFinanceProductsConnector(BaseConnector):
    """
    Conector de catálogo vivo de renda fixa via Open Finance Dados Abertos.

    Uso:
        connector = OpenFinanceProductsConnector()
        catalog = connector.get_rates()          # {"products": [...], "source": ...}
        products = connector.get_products("CDB")
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("cache_ttl_seconds", _CACHE_TTL)
        kwargs.setdefault("timeout_seconds", 10)
        super().__init__(**kwargs)

    # ── BaseConnector interface ──────────────────────────────────────

    def fetch_rates(self) -> dict[str, Any]:
        """Busca e normaliza as ofertas públicas de renda fixa bancária."""
        import httpx

        endpoints = self._discover_endpoints()
        if not endpoints:
            raise ConnectorError("Nenhum endpoint de bank-fixed-incomes descoberto no diretório")

        products: list[dict] = []
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            for institution, url in endpoints[:_MAX_INSTITUTIONS]:
                try:
                    resp = client.get(url, headers={"Accept": "application/json"})
                    resp.raise_for_status()
                    products.extend(self._normalize_payload(institution, resp.json()))
                except Exception as exc:
                    logger.debug("[OpenFinanceProducts] %s (%s): %s", institution, url, exc)

        if len(products) < _MIN_PRODUCTS_FOR_LIVE:
            raise ConnectorError(
                f"Catálogo vivo insuficiente ({len(products)} produtos normalizados)"
            )

        institutions = {p["bank_name"] for p in products}
        logger.info(
            "[OpenFinanceProducts] catálogo vivo: %d produtos de %d instituições",
            len(products), len(institutions),
        )
        return {"products": products, "source": "open_finance"}

    def get_fallback_rates(self) -> dict[str, Any]:
        """Fallback = catálogo curado (backend/data/bank_products.json)."""
        try:
            with open(_CURATED_CATALOG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return {"products": data.get("products", []), "source": "curated"}
        except Exception as exc:
            logger.error("[OpenFinanceProducts] fallback curado falhou: %s", exc)
            return {"products": [], "source": "curated"}

    # ── API pública ──────────────────────────────────────────────────

    def get_products(self, product_type: str | None = None) -> list[dict]:
        catalog = self.get_rates()
        products = catalog.get("products", [])
        if product_type:
            products = [p for p in products if p.get("product_type") == product_type]
        return products

    # ── Descoberta de endpoints ──────────────────────────────────────

    def _discover_endpoints(self) -> list[tuple[str, str]]:
        """Lê o diretório de participantes e retorna (instituição, url) dos
        endpoints de bank-fixed-incomes."""
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
                    family = (api.get("ApiFamilyType") or "").lower()
                    if _API_FAMILY not in family and "opendata-investments" not in family:
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

    # ── Normalização ─────────────────────────────────────────────────

    @classmethod
    def _normalize_payload(cls, institution: str, payload: dict) -> list[dict]:
        """Converte o payload verboso do opendata em produtos no schema
        interno. Descarta o que não consegue interpretar (best-effort)."""
        normalized: list[dict] = []
        for raw in payload.get("data", []) or []:
            try:
                product = cls._normalize_product(institution, raw)
                if product is not None:
                    normalized.append(product)
            except Exception:
                continue
        return normalized

    @classmethod
    def _normalize_product(cls, institution: str, raw: dict) -> dict | None:
        ptype = str(raw.get("investmentType") or raw.get("type") or "").upper()
        if ptype not in _SUPPORTED_TYPES:
            return None
        if ptype == "RDB":
            ptype = "CDB"  # RDB tem tratamento fiscal idêntico ao CDB

        brand = (
            (raw.get("participant") or {}).get("brandName")
            or raw.get("issuerInstitutionName")
            or institution
        )

        cdi_pct = cls._extract_cdi_pct(raw)
        if cdi_pct is None or not (30.0 <= cdi_pct <= 200.0):
            return None  # só produtos pós-fixados CDI com taxa plausível

        min_amount = cls._extract_float(
            raw, ("minimumAmount", "applicationMinimumAmount", "minimumApplicationAmount")
        ) or 1.0

        redemption_days = cls._extract_redemption_days(raw)
        liquidity = "daily" if redemption_days <= 1 else (
            "12m" if redemption_days <= 365 else "24m"
        )

        return {
            "bank_name": str(brand).strip(),
            "product_type": ptype,
            "cdi_pct": round(cdi_pct, 2),
            "min_amount": float(min_amount),
            "liquidity": liquidity,
            "liquidity_days": redemption_days,
            "rating": "N/A",
            "index": "CDI",
            "is_tax_exempt": ptype in ("LCI", "LCA"),
            "fgc_covered": True,
        }

    @staticmethod
    def _extract_cdi_pct(raw: dict) -> float | None:
        """Taxa pós-fixada como % do CDI. O opendata expressa em decimal
        (1.10 = 110% do CDI) dentro de estruturas variadas de remuneração."""
        candidates: list[Any] = []
        for key in ("remuneration", "indexedRates", "rates"):
            node = raw.get(key)
            if isinstance(node, dict):
                candidates.append(node)
            elif isinstance(node, list):
                candidates.extend(n for n in node if isinstance(n, dict))
        candidates.append(raw)

        for node in candidates:
            indexer = str(node.get("indexer") or node.get("index") or "").upper()
            if indexer and indexer not in ("CDI", "DI"):
                continue
            for rate_key in ("postFixedIndexerRate", "rate", "indexerRate", "minRate", "maxRate"):
                value = node.get(rate_key)
                if value is None:
                    continue
                try:
                    rate = float(value)
                except (TypeError, ValueError):
                    continue
                # decimal (1.10) vs percentual (110.0)
                return rate * 100 if rate <= 3.0 else rate
        return None

    @staticmethod
    def _extract_float(raw: dict, keys: tuple[str, ...]) -> float | None:
        for key in keys:
            value = raw.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _extract_redemption_days(raw: dict) -> int:
        for key in ("redemptionTerm", "term", "expirationTerm", "gracePeriod"):
            node = raw.get(key)
            if isinstance(node, dict):
                node = node.get("days") or node.get("value")
            if node is None:
                continue
            try:
                return max(int(float(node)), 1)
            except (TypeError, ValueError):
                continue
        # Sem prazo declarado → assume 12 meses. Assumir liquidez diária seria
        # otimista demais e poderia ranquear produto ilíquido como se fosse líquido.
        return 360


__all__ = ["OpenFinanceProductsConnector"]
