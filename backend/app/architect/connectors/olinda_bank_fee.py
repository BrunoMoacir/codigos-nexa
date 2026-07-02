"""
app/architect/connectors/olinda_bank_fee.py — Conector Olinda Tarifas Bancárias

Fornece tarifas bancárias por instituição financeira via API Olinda do BACEN.
Usado pelo D4 para verificar teto oficial de cada tarifa por IF.

Endpoint OData (requer PessoaFisicaOuJuridica e CNPJ como parâmetros):
  ListaTarifasPorInstituicaoFinanceira(PessoaFisicaOuJuridica=@P,CNPJ=@C)
  ?@P='F'&@C='CNPJ8'&$format=json

CNPJ8: primeiros 8 dígitos do CNPJ (identificador da IF no BACEN).

Cache: 7 dias (tarifas mudam raramente).
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

_BASE = (
    "https://olinda.bcb.gov.br/olinda/servico/"
    "Informes_ListaTarifasPorInstituicaoFinanceira/versao/v1/odata"
)

# Mapeamento nome normalizado → CNPJ8 dos principais bancos brasileiros
_BANK_CNPJ8: dict[str, str] = {
    "itau":         "60701190",
    "itaú":         "60701190",
    "bradesco":     "60746948",
    "santander":    "90400888",
    "banco do brasil": "00000000",
    "bb":           "00000000",
    "caixa":        "36122439",
    "cef":          "36122439",
    "nubank":       "18236120",
    "inter":        "00416968",
    "banco inter":  "00416968",
    "sicredi":      "01181521",
    "sicoob":       "02038232",
    "c6":           "31872495",
    "c6 bank":      "31872495",
    "xp":           "02332886",
    "original":     "92894922",
    "next":         "60746948",  # Bradesco
    "pan":          "59285411",
    "bmg":          "61186680",
    "agibank":      "10664513",
    "mercado pago": "10573521",
    "picpay":       "22896431",
    "pagbank":      "08561701",
}


class OlindaBankFeeConnector(BaseConnector):
    """
    Conector para tarifas bancárias por IF via Olinda BACEN.

    Uso:
        c = OlindaBankFeeConnector()
        ceiling = c.get_max_fee("Itaú Unibanco", "MANUTENCAO_CONTA")
        all_fees = c.get_all_fees("60701190")  # por CNPJ8
    """

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("cache_ttl_seconds", 604800)  # 7 dias
        super().__init__(**kwargs)

    def fetch_rates(self) -> dict:
        return {}

    def get_fallback_rates(self) -> dict:
        return {}

    # ── API pública ───────────────────────────────────────────────────

    def get_max_fee(
        self,
        bank_name: str,
        fee_code: str,
    ) -> Optional[float]:
        """
        Retorna o ValorMaximo (R$) registrado no BACEN para uma tarifa e IF.
        Retorna None se não encontrado ou CNPJ não mapeado.

        fee_code: código interno Nexa (ex: 'MANUTENCAO_CONTA', 'SAQUE', 'EXTRATO')
        """
        cnpj8 = self._resolve_cnpj8(bank_name)
        if not cnpj8:
            logger.debug("[OlindaFee] CNPJ8 não mapeado para: %s", bank_name)
            return None
        try:
            fees = self.get_all_fees(cnpj8)
            # Tenta match pelo código normalizado
            fee_code_norm = fee_code.lower().replace("_", " ")
            for fee in fees:
                servico_norm = (fee.get("NomeServico") or "").lower()
                codigo_norm  = (fee.get("CodigoServico") or "").lower()
                if fee_code_norm in servico_norm or fee_code_norm in codigo_norm:
                    val = fee.get("ValorMaximo")
                    if val is not None:
                        return round(float(val), 2)
            return None
        except Exception as exc:
            logger.debug("[OlindaFee] get_max_fee %s / %s: %s", bank_name, fee_code, exc)
            return None

    def get_all_fees(self, cnpj8: str) -> list[dict]:
        """
        Retorna todas as tarifas registradas para uma IF (por CNPJ8).
        Cada item: {CodigoServico, NomeServico, ValorMaximo, Periodicidade}
        """
        url = (
            f"{_BASE}/ListaTarifasPorInstituicaoFinanceira"
            f"(PessoaFisicaOuJuridica=@P,CNPJ=@C)"
            f"?@P='F'&@C='{cnpj8}'&$format=json"
        )
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url)
                resp.raise_for_status()
            data = resp.json()
            rows = data.get("value", [])
            logger.info("[OlindaFee] %d tarifas para CNPJ8=%s", len(rows), cnpj8)
            return rows
        except Exception as exc:
            raise ConnectorError(f"Olinda tarifas CNPJ8={cnpj8}: {exc}") from exc

    def resolve_cnpj8(self, bank_name: str) -> Optional[str]:
        """Expõe resolução de CNPJ8 para uso externo."""
        return self._resolve_cnpj8(bank_name)

    # ── Internos ──────────────────────────────────────────────────────

    @staticmethod
    def _resolve_cnpj8(bank_name: str) -> Optional[str]:
        norm = bank_name.lower().strip()
        # Busca exata
        if norm in _BANK_CNPJ8:
            return _BANK_CNPJ8[norm]
        # Busca parcial
        for key, cnpj8 in _BANK_CNPJ8.items():
            if key in norm or norm in key:
                return cnpj8
        return None


__all__ = ["OlindaBankFeeConnector"]
