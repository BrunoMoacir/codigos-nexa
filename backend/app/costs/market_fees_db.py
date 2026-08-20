"""
app/costs/market_fees_db.py — F5: Base de Tarifas de Mercado

Fonte: Tabelas de tarifas padronizadas BACEN (Resolução 3.919/2010),
       sites institucionais e pesquisa de mercado — março/2026.

Estrutura:
  _BANK_FEES_DB  → custo mensal médio por banco (tarifas cobradas de fato,
                   não o valor publicado no pacote máximo)
  MarketFeesDB   → classe que resolve benchmarks para os bancos do usuário
                   e sempre inclui o "melhor banco digital" como referência mínima

Atualização:
  Os valores são estáticos. Para atualização automática via BACEN/scraping,
  substituir _BANK_FEES_DB por leitura de data/fees/bank_fees.json com
  cache em Redis (TTL 30 dias).
  TODO: Fase 2 — migrar para data/fees/bank_fees.json + Redis cache.
"""

from __future__ import annotations

from app.costs.models import BankFeeSummary, MarketBenchmark

_SOURCE = "bacen_resolucao_3919_pesquisa_mercado_2026"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BASE DE TARIFAS MÉDIAS MENSAIS POR BANCO
# Valores = média real cobrada (não o teto publicado no pacote)
# Inclui: manutenção de conta + tarifas de serviço mais comuns
# Exclui: anuidade de cartão (variável por produto) e juros rotativos
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_BANK_FEES_DB: dict[str, float] = {
    # ── Bancos digitais (referência de menor custo) ───────────────
    "Nubank":        0.0,    # conta corrente gratuita; anuidade varia por cartão
    "Banco Inter":   0.0,    # conta digital gratuita
    "C6 Bank":       0.0,    # conta digital gratuita
    "Next":          0.0,    # conta digital Bradesco sem tarifa de manutenção
    "PicPay":        0.0,    # conta digital gratuita
    "XP":            0.0,    # conta corrente gratuita

    # ── Bancos tradicionais (pacote padrão mais contratado) ───────
    "Itaú":              42.90,  # Pacote Essencial + TED + saque
    "Bradesco":          38.50,  # Pacote Bradesco Click + tarifas pontuais
    "Santander":         44.00,  # Pacote Santander Free + serviços avulsos
    "Banco do Brasil":   31.00,  # Pacote Essencial + tarifas de saque
    "Caixa Econômica":   24.50,  # Conta Caixa Fácil + manutenção
}

# Referência universal incluída sempre no relatório:
# banco digital de menor custo comprovado (Nubank/Inter/C6 = R$ 0)
_BENCHMARK_DIGITAL_REFERENCE = MarketBenchmark(
    bank_name="Melhor banco digital (Nubank / Inter / C6)",
    monthly_avg_market=0.0,
    source=_SOURCE,
)


# Baseline VIVO (job market_fees_refresh, 02h15): tarifas publicadas pelos
# próprios bancos no Open Finance Dados Abertos, ponderadas por faixa de
# clientes. Preferido quando existe; a tabela estática acima é o fallback.
_LIVE_FEES_PATH = (
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "data" / "fees" / "market_fees_live.json"
)
_LIVE_TTL_SECONDS = 15 * 60


class MarketFeesDB:
    """
    Resolve benchmarks de mercado para os bancos identificados no perfil do usuário.

    Fontes (nesta ordem):
      1. data/fees/market_fees_live.json — baseline vivo via Open Finance
         (recarregado por mtime/TTL; o job diário atualiza sem restart);
      2. _BANK_FEES_DB — tabela estática curada (fallback sempre disponível).

    Sempre inclui a referência digital (R$ 0/mês) para mostrar
    o potencial máximo de economia.
    """

    def __init__(self) -> None:
        self._live: dict[str, dict] | None = None
        self._live_mtime: float = 0.0
        self._live_loaded_at: float = 0.0

    # ── baseline vivo ────────────────────────────────────────────────

    def _refresh_live(self) -> None:
        import json
        import time

        now = time.monotonic()
        if self._live is not None and (now - self._live_loaded_at) < _LIVE_TTL_SECONDS:
            return
        self._live_loaded_at = now
        try:
            if not _LIVE_FEES_PATH.exists():
                self._live = None
                return
            mtime = _LIVE_FEES_PATH.stat().st_mtime
            if self._live is not None and mtime == self._live_mtime:
                return
            data = json.loads(_LIVE_FEES_PATH.read_text(encoding="utf-8"))
            institutions = data.get("institutions", [])
            self._live = {
                inst["bank_name"].lower(): inst
                for inst in institutions
                if inst.get("monthly_package_typical") is not None
            }
            self._live_mtime = mtime
        except Exception:
            self._live = None

    def _live_lookup(self, bank_name: str) -> float | None:
        """Pacote mensal típico do baseline vivo, com matching tolerante."""
        self._refresh_live()
        if not self._live:
            return None
        from app.opportunities.services.bank_names import find_matching

        key = find_matching(bank_name, set(self._live.keys()))
        if key is None:
            return None
        return float(self._live[key]["monthly_package_typical"])

    @property
    def live_available(self) -> bool:
        self._refresh_live()
        return bool(self._live)

    def get_benchmarks(
        self, user_banks: list[BankFeeSummary]
    ) -> list[MarketBenchmark]:
        """
        Retorna benchmarks para cada banco do usuário + referência digital.

        Args:
            user_banks: Bancos detectados nas transações do usuário.

        Returns:
            Lista de MarketBenchmark ordenada do mais barato ao mais caro.
        """
        seen: set[str] = set()
        benchmarks: list[MarketBenchmark] = []

        for bank in user_banks:
            name = bank.bank_name
            if name in seen:
                continue
            seen.add(name)

            # Banco não identificado não recebe benchmark. Antes recebia a média
            # dos tradicionais como proxy — e como em produção TODAS as tarifas
            # caíam nesse balde (transactions_clean não tem coluna de
            # instituição), o relatório comparava o usuário contra bancos que
            # talvez nem sejam os dele e chamava a diferença de "economia".
            from app.costs.fee_detector import banco_identificado

            if not banco_identificado(name):
                continue

            live_avg = self._live_lookup(name)
            if live_avg is not None:
                market_avg, source = live_avg, "open_finance_dados_abertos"
            else:
                market_avg = _BANK_FEES_DB.get(name)
                source = _SOURCE
                if market_avg is None:
                    # Banco conhecido, sem preço na base: média dos tradicionais
                    market_avg = self._traditional_bank_avg()

            benchmarks.append(
                MarketBenchmark(
                    bank_name=name,
                    monthly_avg_market=market_avg,
                    source=source,
                )
            )

        # Adiciona referência digital se não for já o único banco do usuário
        if _BENCHMARK_DIGITAL_REFERENCE.bank_name not in seen:
            benchmarks.append(_BENCHMARK_DIGITAL_REFERENCE.model_copy())

        # Ordena do mais barato ao mais caro (facilita leitura no relatório)
        benchmarks.sort(key=lambda b: b.monthly_avg_market)
        return benchmarks

    def get_avg_for_bank(self, bank_name: str) -> float:
        """Retorna custo médio mensal de mercado para um banco específico."""
        live_avg = self._live_lookup(bank_name)
        if live_avg is not None:
            return live_avg
        return _BANK_FEES_DB.get(bank_name, self._traditional_bank_avg())

    @staticmethod
    def _traditional_bank_avg() -> float:
        """Média dos bancos tradicionais mapeados — proxy para bancos desconhecidos."""
        traditional = [v for k, v in _BANK_FEES_DB.items() if v > 0]
        return round(sum(traditional) / len(traditional), 2) if traditional else 35.0
