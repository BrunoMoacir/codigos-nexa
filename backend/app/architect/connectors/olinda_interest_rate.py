"""
app/architect/connectors/olinda_interest_rate.py — Conector Olinda taxaJuros v2

Fornece taxas médias de juros POR INSTITUIÇÃO FINANCEIRA via API Olinda do BACEN.
Mais preciso que o SGS (taxas populacionais) para D3 e D6.

Endpoints:
  TaxasJurosMensalPorMes  — taxas mensais por modalidade e IF
  TaxasJurosDiariaPorInicioPeriodo — diário por início de período

Campos retornados:
  Modalidade, InstituicaoFinanceira, cnpj8, TaxaJurosAoMes, TaxaJurosAoAno,
  NumeroDeContratos, Posicao

Cache: 24h (dados mudam mensalmente).
Sem autenticação necessária.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

_BASE = "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata"

# Mapeamento de modalidades Olinda → chaves internas Nexa
_MODALITY_MAP = {
    "rotativo":          ["Cartão de crédito rotativo", "Crédito rotativo"],
    "parcelado":         ["Cartão de crédito parcelado", "Crédito parcelado"],
    "cheque_especial":   ["Cheque especial", "Conta garantida"],
    "consignado":        ["Crédito consignado", "Crédito consignado INSS"],
    "pessoal":           ["Crédito pessoal", "Crédito pessoal não consignado"],
    "veiculo":           ["Aquisição de veículos", "Financiamento de veículos"],
    "imovel":            ["Financiamento imobiliário", "Aquisição de imóveis"],
}

# Fallback: média de mercado mai/2026 (BacenCreditConnector) em % a.m.
_FALLBACK_MARKET = {
    "rotativo":        15.67,
    "cheque_especial": 10.80,
    "consignado":       1.75,
    "pessoal":          3.20,
}


class OlindaInterestRateConnector(BaseConnector):
    """
    Conector para taxaJuros v2 do Olinda BACEN.

    Uso:
        c = OlindaInterestRateConnector()
        # Médias de mercado por modalidade (% a.m.)
        rates = c.get_market_averages()
        # Taxa do banco específico
        rate = c.get_rate_by_institution("Itaú Unibanco", "rotativo", "2026-05")
        # Melhor taxa disponível no mercado para uma modalidade
        best = c.get_best_rate("pessoal", "2026-05")
    """

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("cache_ttl_seconds", 86400)  # 24h
        super().__init__(**kwargs)

    def fetch_rates(self) -> dict:
        """Interface BaseConnector — retorna médias de mercado por modalidade."""
        return self._fetch_monthly_averages(self._current_month())

    def get_fallback_rates(self) -> dict:
        return {k: v / 100 for k, v in _FALLBACK_MARKET.items()}

    # ── API pública ───────────────────────────────────────────────────

    def get_market_averages(self, mes: Optional[str] = None) -> dict[str, float]:
        """
        Retorna taxa média de mercado por modalidade em decimal (% a.m.).
        Ex: {"rotativo": 0.1567, "cheque_especial": 0.1080, ...}
        """
        mes = mes or self._current_month()
        try:
            raw = self._fetch_monthly_averages(mes)
            return raw
        except Exception as exc:
            logger.warning("[OlindaIR] get_market_averages fallback: %s", exc)
            return self.get_fallback_rates()

    def get_rate_by_institution(
        self,
        institution_name: str,
        modality: str,
        mes: Optional[str] = None,
    ) -> Optional[float]:
        """
        Retorna taxa média em % a.m. (decimal) para uma IF específica e modalidade.
        Retorna None se não encontrado.
        """
        mes = mes or self._current_month()
        olinda_modalities = _MODALITY_MAP.get(modality, [modality])
        try:
            rows = self._fetch_raw(mes)
            matches = [
                r for r in rows
                if self._name_match(r.get("InstituicaoFinanceira", ""), institution_name)
                and any(
                    m.lower() in (r.get("Modalidade") or "").lower()
                    for m in olinda_modalities
                )
            ]
            if not matches:
                return None
            rates = [
                float(r["TaxaJurosAoMes"])
                for r in matches
                if r.get("TaxaJurosAoMes") not in (None, "")
            ]
            return round(sum(rates) / len(rates) / 100, 6) if rates else None
        except Exception as exc:
            logger.debug("[OlindaIR] get_rate_by_institution: %s", exc)
            return None

    def get_best_rate(
        self,
        modality: str,
        mes: Optional[str] = None,
        min_contracts: int = 100,
    ) -> Optional[float]:
        """
        Retorna a MENOR taxa disponível no mercado para uma modalidade (% a.m. decimal).
        Filtra por volume mínimo de contratos para evitar IFs irrelevantes.
        """
        mes = mes or self._current_month()
        olinda_modalities = _MODALITY_MAP.get(modality, [modality])
        try:
            rows = self._fetch_raw(mes)
            candidates = []
            for r in rows:
                if not any(
                    m.lower() in (r.get("Modalidade") or "").lower()
                    for m in olinda_modalities
                ):
                    continue
                try:
                    n_contracts = int(r.get("NumeroDeContratos") or 0)
                    if n_contracts < min_contracts:
                        continue
                    rate = float(r["TaxaJurosAoMes"]) / 100
                    candidates.append(rate)
                except (TypeError, ValueError):
                    continue
            return round(min(candidates), 6) if candidates else None
        except Exception as exc:
            logger.debug("[OlindaIR] get_best_rate: %s", exc)
            return None

    def get_institution_ranking(
        self,
        modality: str,
        mes: Optional[str] = None,
    ) -> list[dict]:
        """
        Retorna ranking de IFs por taxa (menor para maior) para uma modalidade.
        Útil para D6 (sugerir banco alvo de portabilidade).
        """
        mes = mes or self._current_month()
        olinda_modalities = _MODALITY_MAP.get(modality, [modality])
        try:
            rows = self._fetch_raw(mes)
            result = []
            for r in rows:
                if not any(
                    m.lower() in (r.get("Modalidade") or "").lower()
                    for m in olinda_modalities
                ):
                    continue
                try:
                    result.append({
                        "institution": r.get("InstituicaoFinanceira", ""),
                        "cnpj8": r.get("cnpj8", ""),
                        "rate_month": round(float(r["TaxaJurosAoMes"]) / 100, 6),
                        "rate_year":  round(float(r.get("TaxaJurosAoAno", 0)) / 100, 6),
                        "n_contracts": int(r.get("NumeroDeContratos") or 0),
                    })
                except (TypeError, ValueError):
                    continue
            result.sort(key=lambda x: x["rate_month"])
            return result
        except Exception as exc:
            logger.debug("[OlindaIR] get_institution_ranking: %s", exc)
            return []

    # ── Internos ──────────────────────────────────────────────────────

    def _fetch_monthly_averages(self, mes: str) -> dict[str, float]:
        rows = self._fetch_raw(mes)
        averages: dict[str, list[float]] = {k: [] for k in _MODALITY_MAP}
        for r in rows:
            mod_raw = (r.get("Modalidade") or "").lower()
            for key, aliases in _MODALITY_MAP.items():
                if any(a.lower() in mod_raw for a in aliases):
                    try:
                        averages[key].append(float(r["TaxaJurosAoMes"]))
                    except (TypeError, ValueError):
                        pass
                    break
        result = {}
        for key, vals in averages.items():
            if vals:
                result[key] = round(sum(vals) / len(vals) / 100, 6)
        return result or self.get_fallback_rates()

    def _fetch_raw(self, mes: str) -> list[dict]:
        url = (
            f"{_BASE}/TaxasJurosMensalPorMes"
            f"?$filter=anoMes eq '{mes}'"
            f"&$format=json"
            f"&$top=5000"
        )
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()
        data = resp.json()
        rows = data.get("value", [])
        if not rows:
            raise ConnectorError(f"Olinda taxaJuros: sem dados para {mes}")
        logger.info("[OlindaIR] %d registros para %s", len(rows), mes)
        return rows

    @staticmethod
    def _current_month() -> str:
        d = date.today()
        # Olinda tem delay de ~45 dias; usar mês anterior se ainda no início do mês
        if d.day < 15:
            m = d.month - 1 if d.month > 1 else 12
            y = d.year if d.month > 1 else d.year - 1
            return f"{y}-{m:02d}"
        return d.strftime("%Y-%m")

    @staticmethod
    def _name_match(olinda_name: str, search: str) -> bool:
        return search.lower() in olinda_name.lower()


__all__ = ["OlindaInterestRateConnector"]
