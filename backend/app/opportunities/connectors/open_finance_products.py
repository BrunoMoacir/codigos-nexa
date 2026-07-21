"""
app/opportunities/connectors/open_finance_products.py

V3 (F8) — conector para os Dados Abertos de investimentos do Open Finance
Brasil, agora varrendo TODOS os participantes do diretório.

Não requer consentimento do usuário — são ofertas públicas das instituições,
padronizadas por regulação do BACEN. O fluxo:

  1. Diretório de participantes (data.directory.openbankingbrasil.org.br)
     → descobre os endpoints `opendata-investments/bank-fixed-incomes`
       de cada instituição participante (~45 em 2026-07).
  2. Busca as ofertas de CDB/RDB/LCI/LCA de todos os endpoints em paralelo
     (ThreadPool), seguindo paginação via links.next (máx. _MAX_PAGES).
  3. Normaliza para o schema interno (bank_name, product_type, cdi_pct,
     min_amount, liquidity, liquidity_days, ...) seguindo o spec real do
     opendata-investments v1: taxa em index.issueRemunerationRate.prices[]
     (fração do CDI por faixa, ponderada por operationRate), condições em
     investmentConditions, público em targetAudience (PJ é descartado).
  4. Deduplica: mantém a melhor taxa por (banco, tipo, janela de liquidez).

Fallback (get_fallback_rates): catálogo curado backend/data/bank_products.json
— o OPP nunca fica sem catálogo, mesmo com o diretório fora do ar.

A normalização é defensiva: mantém caminhos legados para payloads fora do
spec e descarta silenciosamente produtos que não consegue interpretar.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

_CURATED_CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "bank_products.json"

_PARTICIPANTS_URL = "https://data.directory.openbankingbrasil.org.br/participants"
_API_FAMILY = "opendata-investments_bank-fixed-incomes"
_ENDPOINT_SUFFIX = "/bank-fixed-incomes"

_CACHE_TTL = 6 * 3600          # 6h — ofertas públicas não mudam a cada minuto
_MAX_INSTITUTIONS = 80         # teto de segurança (diretório tem ~45 hoje)
_MAX_PAGES = 3                 # páginas seguidas por instituição (links.next)
_MAX_WORKERS = 8               # fetches concorrentes
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
        endpoints = self._discover_endpoints()
        if not endpoints:
            raise ConnectorError("Nenhum endpoint de bank-fixed-incomes descoberto no diretório")

        endpoints = endpoints[:_MAX_INSTITUTIONS]
        products: list[dict] = []
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(self._fetch_institution, institution, url): institution
                for institution, url in endpoints
            }
            for future in as_completed(futures):
                try:
                    products.extend(future.result())
                except Exception as exc:
                    logger.debug("[OpenFinanceProducts] %s: %s", futures[future], exc)

        products = self._dedupe(products)

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

    # ── Fetch por instituição (com paginação) ────────────────────────

    def _fetch_institution(self, institution: str, url: str) -> list[dict]:
        """Busca todas as páginas (até _MAX_PAGES) de uma instituição."""
        import httpx

        products: list[dict] = []
        next_url: str | None = url
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            for _ in range(_MAX_PAGES):
                if not next_url:
                    break
                resp = client.get(next_url, headers={"Accept": "application/json"})
                resp.raise_for_status()
                payload = resp.json()
                products.extend(self._normalize_payload(institution, payload))
                links = payload.get("links") or {}
                candidate = links.get("next")
                # alguns servidores repetem self em next — evita loop infinito
                next_url = candidate if candidate and candidate != next_url else None
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

    # ── Deduplicação ─────────────────────────────────────────────────

    @staticmethod
    def _dedupe(products: list[dict]) -> list[dict]:
        """Mantém a melhor taxa por (banco, tipo, janela de liquidez) —
        catálogo compacto sem perder a melhor oferta de cada banco."""
        best: dict[tuple, dict] = {}
        for p in products:
            key = (p["bank_name"].lower(), p["product_type"], p["liquidity"])
            current = best.get(key)
            if current is None or p["cdi_pct"] > current["cdi_pct"]:
                best[key] = p
        return sorted(
            best.values(),
            key=lambda p: (p["bank_name"].lower(), p["product_type"], -p["cdi_pct"]),
        )

    # ── Normalização ─────────────────────────────────────────────────

    @classmethod
    def _normalize_payload(cls, institution: str, payload: dict) -> list[dict]:
        """Converte o payload do opendata em produtos no schema interno.
        Descarta o que não consegue interpretar (best-effort)."""
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

        # Catálogo do OPP é para pessoa física
        audience = str(raw.get("targetAudience") or "").upper()
        if "JURIDICA" in audience:
            return None

        from app.opportunities.services.bank_names import canonical_brand

        participant = raw.get("participant") or {}
        brand = canonical_brand(
            participant.get("brand")
            or participant.get("brandName")
            or participant.get("name")
            or raw.get("issuerInstitutionName")
            or institution
        )

        cdi_pct, cdi_pct_max = cls._extract_cdi_pct(raw)
        if cdi_pct is None or not (30.0 <= cdi_pct <= 200.0):
            return None  # só produtos pós-fixados CDI com taxa plausível

        conditions = raw.get("investmentConditions") or {}
        min_amount = cls._extract_float(
            conditions, ("minimumAmount",)
        ) or cls._extract_float(
            raw, ("minimumAmount", "applicationMinimumAmount", "minimumApplicationAmount")
        ) or 1.0

        redemption_days = cls._extract_redemption_days(raw, conditions)
        liquidity = "daily" if redemption_days <= 1 else (
            "12m" if redemption_days <= 365 else "24m"
        )

        product = {
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
        if cdi_pct_max is not None and cdi_pct_max > cdi_pct:
            product["cdi_pct_max"] = round(cdi_pct_max, 2)
        # Acima de 130% do CDI é quase sempre teaser promocional (prazo curto,
        # teto baixo, só clientes novos) — marcado para o comparador/UI não
        # tratar como taxa permanente.
        if cdi_pct > 130.0:
            product["promotional"] = True
        return product

    @classmethod
    def _extract_cdi_pct(cls, raw: dict) -> tuple[float | None, float | None]:
        """
        Taxa pós-fixada como % do CDI: (típica, máxima).

        Spec opendata-investments v1: `index.indexer` + faixas em
        `index.issueRemunerationRate.prices[]`, onde `value` é a fração do
        CDI (1.10 = 110%) e `operationRate` a participação daquela faixa
        nas operações. A taxa "típica" é a média ponderada por
        operationRate — representa o que o cliente comum recebe; `maximum`
        vira cdi_pct_max ("até X% do CDI").
        """
        index_node = raw.get("index")
        if isinstance(index_node, dict):
            indexer = str(index_node.get("indexer") or "").upper()
            if indexer in ("CDI", "DI"):
                remuneration = index_node.get("issueRemunerationRate") or {}
                prices = remuneration.get("prices") or []
                weighted_sum = weight_sum = 0.0
                values: list[float] = []
                for price in prices:
                    try:
                        value = float(price.get("value") or 0)
                        share = float(price.get("operationRate") or 0)
                    except (TypeError, ValueError):
                        continue
                    if value <= 0:
                        continue
                    values.append(value)
                    if share > 0:
                        weighted_sum += value * share
                        weight_sum += share

                maximum = None
                try:
                    max_raw = float(remuneration.get("maximum") or 0)
                    maximum = max_raw if max_raw > 0 else None
                except (TypeError, ValueError):
                    pass

                typical = None
                if weight_sum > 0:
                    typical = weighted_sum / weight_sum
                elif values:
                    typical = max(values)
                elif maximum:
                    typical = maximum

                if typical is not None:
                    scale = 100 if typical <= 3.0 else 1
                    return (
                        typical * scale,
                        maximum * (100 if (maximum or 0) <= 3.0 else 1) if maximum else None,
                    )
            elif indexer:
                return (None, None)  # prefixado/IPCA — fora do comparador CDI

        # Caminho legado: payloads fora do spec (chaves planas)
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
                return (rate * 100 if rate <= 3.0 else rate, None)
        return (None, None)

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
    def _extract_redemption_days(raw: dict, conditions: dict) -> int:
        """
        Dias até liquidez, a partir do spec:
          redemptionTerm "DIARIA" → 1 dia
          "DATA_VENCIMENTO" → limite inferior de expirationPeriod
        expirationPeriod é categórico: "1_180", "181_360", "361_1080",
        "ACIMA_1080" — extraímos o primeiro número como piso conservador.
        """
        term = str(conditions.get("redemptionTerm") or "").upper()
        if "DIARIA" in term:
            return 1
        if term:
            expiration = str(conditions.get("expirationPeriod") or "")
            digits = ""
            for ch in expiration:
                if ch.isdigit():
                    digits += ch
                elif digits:
                    break
            if digits:
                days = int(digits)
                # "ACIMA_1080" → o número é piso; soma 1 para cair na faixa seguinte
                return days + 1 if "ACIMA" in expiration.upper() else max(days, 1)
            return 360  # DATA_VENCIMENTO sem prazo declarado → assume 12 meses

        # Caminho legado (chaves numéricas planas)
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
