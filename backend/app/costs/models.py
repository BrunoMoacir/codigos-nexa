"""
app/costs/models.py — Schemas do F5: Raio-X de Custos Bancários

Tipos de entrada e saída do BankFeeAnalyzer.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class FeeType(str, Enum):
    ANUIDADE_CARTAO    = "ANUIDADE_CARTAO"     # anuidade de cartão de crédito
    TARIFA_MANUTENCAO  = "TARIFA_MANUTENCAO"   # taxa de manutenção de conta
    TED_DOC            = "TED_DOC"             # transferências com custo
    SAQUE              = "SAQUE"               # saque em caixa eletrônico
    JUROS_ROTATIVO     = "JUROS_ROTATIVO"      # juros do crédito rotativo
    SEGURO_PRESTAMISTA = "SEGURO_PRESTAMISTA"  # seguro embutido em crédito
    PACOTE_SERVICOS    = "PACOTE_SERVICOS"     # pacote mensal de serviços
    IOF                = "IOF"                 # IOF em operações de crédito
    OUTROS_CUSTOS      = "OUTROS_CUSTOS"       # tarifas não classificadas


class FeeEntry(BaseModel):
    """Tarifa individual detectada em uma transação."""
    transaction_date: date
    fee_type: FeeType
    amount: float                              # valor pago (sempre positivo)
    bank_name: str                             # nome legível do banco
    institution_id: str                        # ID original da instituição
    description: str                           # descrição original da transação


class BankFeeSummary(BaseModel):
    """Custos agregados de uma instituição financeira."""
    bank_name: str
    institution_id: str
    total_paid: float                          # total pago no período analisado (R$)
    monthly_avg: float                         # média mensal (R$)
    fees_by_type: dict[str, float]             # {FeeType: valor_total}
    transaction_count: int                     # número de cobranças detectadas


class MarketBenchmark(BaseModel):
    """Referência de mercado para comparação de custos."""
    bank_name: str
    monthly_avg_market: float                  # média de mercado para o mesmo banco/perfil
    source: str = "dados_publicos_bacen_2026"


class BankCostReport(BaseModel):
    """Relatório completo de custos bancários do usuário."""
    user_id: str
    analysis_months: int                       # meses de histórico analisados
    period_start: Optional[date] = None
    period_end: Optional[date] = None

    # Custo total
    total_paid: float                          # total pago em tarifas no período (R$)
    monthly_avg: float                         # média mensal total (R$)
    annual_projection: float                   # projeção anual (monthly_avg × 12)
    # Compatibilidade legada: total de tarifas no período (esperado por testes antigos)
    total_fees_period: float = 0.0

    # Detalhamento por banco
    by_bank: list[BankFeeSummary]

    # Detalhamento por tipo de tarifa
    by_fee_type: dict[str, float]              # {FeeType: valor_total}

    # Comparação com mercado
    market_benchmarks: list[MarketBenchmark]
    savings_opportunity: float = Field(
        description="Quanto poderia economizar migrando para o banco mais barato do mercado (R$/mês)"
    )

    # Metadados
    fees_detected: list[FeeEntry]              # todas as tarifas individuais detectadas
    confidence_score: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
