"""
app/forecast/etl/currency.py — Conversão de moeda estrangeira para BRL.

╔══════════════════════════════════════════════════════════════════════╗
║ O PROBLEMA                                                           ║
╚══════════════════════════════════════════════════════════════════════╝

Compra internacional chega da Pluggy com `currencyCode: "USD"` e o valor
NA MOEDA DE ORIGEM. O schema passou a gravar a moeda certa, mas nenhum
engine (fluxo de caixa, safe-to-spend, health score, orçamento) olha esse
campo: US$ 120 entrava na soma como se fossem R$ 120 — subestimando o
gasto real em ~5x.

╔══════════════════════════════════════════════════════════════════════╗
║ A DECISÃO                                                            ║
╚══════════════════════════════════════════════════════════════════════╝

Converter na INGESTÃO, não na leitura. Motivos:

  1. Todo consumidor a jusante passa a trabalhar numa moeda só — não há
     como esquecer de converter em um cálculo novo;
  2. a taxa fica congelada no momento do lançamento, que é o valor que o
     usuário efetivamente pagou (reconverter depois com a cotação de hoje
     mudaria o passado a cada consulta).

O valor original é preservado em `original_amount`/`original_currency` e a
taxa aplicada em `fx_rate` — extrato e auditoria continuam podendo mostrar
"US$ 120,00 (R$ 648,00)".

╔══════════════════════════════════════════════════════════════════════╗
║ FONTE DA TAXA                                                        ║
╚══════════════════════════════════════════════════════════════════════╝

PTAX do BCB (mesma casa das séries SELIC/TR já usadas pelo projeto), com
cache em memória e tabela de fallback embutida. A busca ao vivo é
OPT-IN via settings.FX_LIVE_RATES: o sync roda no caminho crítico do
usuário e não pode ficar refém de uma chamada HTTP — e a suíte de testes
não pode depender de rede (ver o flaky do test_cet_acima_da_selic).

Sem cotação viva, o fallback erra na segunda casa; sem conversão nenhuma,
o erro é de 400%. É o trade-off certo enquanto a operação é só BRL + uma
compra internacional ocasional.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Optional

import polars as pl

logger = logging.getLogger(__name__)

MOEDA_BASE = "BRL"

# Cotações de fallback em BRL por unidade da moeda.
# Referência: PTAX de fechamento em 2026-08-14. ATUALIZAR trimestralmente
# (ou ligar FX_LIVE_RATES, que torna esta tabela apenas rede de segurança).
_FALLBACK_BRL: Dict[str, float] = {
    "BRL": 1.0,
    "USD": 5.40,
    "EUR": 5.85,
    "GBP": 6.80,
}

# Séries do SGS/BCB — cotação de VENDA, que é a que o cartão usa.
_SERIES_SGS: Dict[str, int] = {
    "USD": 1,      # Dólar comercial (venda)
    "EUR": 21619,  # Euro (venda)
    "GBP": 21623,  # Libra (venda)
}

_SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/1?formato=json"

_TTL_SEGUNDOS = 6 * 3600
_TIMEOUT_SEGUNDOS = 5.0


class CurrencyConverter:
    """
    Conversor com cache em memória. Thread-safe: o sync roda em thread de
    job e mais de um item pode sincronizar ao mesmo tempo.
    """

    def __init__(self, live: Optional[bool] = None, ttl_seconds: int = _TTL_SEGUNDOS):
        self._cache: Dict[str, tuple[float, float]] = {}  # moeda → (taxa, timestamp)
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._live = live

    # ── API pública ───────────────────────────────────────────────────

    def rate_to_brl(self, moeda: str) -> float:
        """Quantos reais vale 1 unidade de `moeda`. Nunca levanta."""
        moeda = (moeda or MOEDA_BASE).upper()
        if moeda == MOEDA_BASE:
            return 1.0

        with self._lock:
            cached = self._cache.get(moeda)
            if cached and (time.monotonic() - cached[1]) < self._ttl:
                return cached[0]

        taxa = self._fetch_live(moeda) if self._usa_live() else None
        if taxa is None:
            taxa = _FALLBACK_BRL.get(moeda)

        if taxa is None:
            # Moeda fora da tabela: converter com taxa inventada seria pior
            # do que não converter. Devolve 1.0 e o chamador registra o
            # aviso — o valor fica na moeda original, explicitamente.
            logger.warning("[FX] Sem cotação para %s — valor mantido sem conversão", moeda)
            return 1.0

        with self._lock:
            self._cache[moeda] = (taxa, time.monotonic())
        return taxa

    def rates_for(self, moedas: list[str]) -> Dict[str, float]:
        """Taxas de várias moedas de uma vez (uma busca por moeda, no máximo)."""
        return {m: self.rate_to_brl(m) for m in {(m or MOEDA_BASE).upper() for m in moedas}}

    # ── Interno ───────────────────────────────────────────────────────

    def _usa_live(self) -> bool:
        if self._live is not None:
            return self._live
        try:
            from app.core.config import settings

            return bool(getattr(settings, "FX_LIVE_RATES", False))
        except Exception:
            return False

    def _fetch_live(self, moeda: str) -> Optional[float]:
        serie = _SERIES_SGS.get(moeda)
        if serie is None:
            return None
        try:
            import httpx

            with httpx.Client(timeout=_TIMEOUT_SEGUNDOS) as client:
                resposta = client.get(_SGS_URL.format(serie=serie))
                resposta.raise_for_status()
            dados = resposta.json()
            valor = float(dados[0]["valor"])
            if valor <= 0:
                raise ValueError(f"cotação não-positiva: {valor}")
            logger.info("[FX] PTAX %s/BRL = %.4f (série %s)", moeda, valor, serie)
            return valor
        except Exception as e:
            logger.warning("[FX] PTAX %s indisponível (%s) — usando fallback", moeda, e)
            return None


# Singleton do processo: o cache só faz sentido compartilhado.
_conversor = CurrencyConverter()


def get_currency_converter() -> CurrencyConverter:
    return _conversor


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# APLICAÇÃO NO DATAFRAME
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def convert_to_brl(
    df: pl.DataFrame,
    converter: Optional[CurrencyConverter] = None,
) -> pl.DataFrame:
    """
    Converte amount/balance para BRL, preservando o original.

    Colunas adicionadas:
        original_amount   — valor como o banco mandou
        original_currency — moeda de origem (BRL quando não houve conversão)
        fx_rate           — taxa aplicada (1.0 para BRL)

    Lote 100% em reais sai com fx_rate=1.0 e nenhuma consulta de cotação —
    o caminho comum não paga nada por esta etapa.
    """
    if "currency" not in df.columns or df.is_empty():
        return df.with_columns([
            pl.col("amount").alias("original_amount"),
            pl.lit(MOEDA_BASE).alias("original_currency"),
            pl.lit(1.0).cast(pl.Float64).alias("fx_rate"),
        ])

    moeda_col = pl.col("currency").cast(pl.String).fill_null(MOEDA_BASE).str.to_uppercase()
    df = df.with_columns(moeda_col.alias("original_currency"))

    moedas = [m for m in df["original_currency"].unique().to_list() if m]
    estrangeiras = [m for m in moedas if m != MOEDA_BASE]

    if not estrangeiras:
        return df.with_columns([
            pl.col("amount").alias("original_amount"),
            pl.lit(1.0).cast(pl.Float64).alias("fx_rate"),
        ])

    taxas = (converter or get_currency_converter()).rates_for(moedas)
    logger.info("[FX] Convertendo %s para BRL: %s", estrangeiras, taxas)

    df = df.with_columns(
        pl.col("original_currency")
        .replace_strict(taxas, default=1.0, return_dtype=pl.Float64)
        .alias("fx_rate")
    )

    df = df.with_columns([
        pl.col("amount").alias("original_amount"),
        (pl.col("amount") * pl.col("fx_rate")).alias("amount"),
    ])

    if "balance" in df.columns:
        df = df.with_columns((pl.col("balance") * pl.col("fx_rate")).alias("balance"))

    return df
