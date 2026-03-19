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


class MarketFeesDB:
    """
    Resolve benchmarks de mercado para os bancos identificados no perfil do usuário.

    Sempre inclui a referência digital (R$ 0/mês) para mostrar
    o potencial máximo de economia.
    """

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

            market_avg = _BANK_FEES_DB.get(name)
            if market_avg is None:
                # Banco não mapeado: usa média dos bancos tradicionais como proxy
                market_avg = self._traditional_bank_avg()

            benchmarks.append(
                MarketBenchmark(
                    bank_name=name,
                    monthly_avg_market=market_avg,
                    source=_SOURCE,
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
        return _BANK_FEES_DB.get(bank_name, self._traditional_bank_avg())

    @staticmethod
    def _traditional_bank_avg() -> float:
        """Média dos bancos tradicionais mapeados — proxy para bancos desconhecidos."""
        traditional = [v for k, v in _BANK_FEES_DB.items() if v > 0]
        return round(sum(traditional) / len(traditional), 2) if traditional else 35.0
