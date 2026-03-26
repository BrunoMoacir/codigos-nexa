# backend/app/cashflow/projector.py

"""
Projetor de Fluxo de Caixa - MOTOR EVENT-DRIVEN DA NEXA

RESPONSABILIDADE:
    Simular o fluxo financeiro diário futuro do usuário a partir de eventos financeiros explícitos.

PRINCÍPIO:
    Nenhum saldo é projetado sem um evento financeiro que o justifique.

O projector não trabalha apenas com valores,
ele constrói uma LINHA DO TEMPO FINANCEIRA EXPLICÁVEL.

Cada dia futuro contém:
    - Saldo projetado
    - Lista de eventos financeiros causadores
    - Flag de risco

Isso permite:
    - Auditoria
    - Explicabilidade
    - Narrativa financeira
    - Agentes inteligentes
"""

import logging
import polars as pl
from datetime import timedelta
from dataclasses import dataclass
from typing import Optional, Literal, List, Dict, Any

logger = logging.getLogger(__name__)


RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@dataclass
class ProjectionSummary:
    """
    Resumo agregado da projeção de cashflow.

    Esse resumo alimenta:
        - Safe-to-Spend
        - Alertas
        - Agente cognitivo
        - UI resumida

    Ele representa uma compressão informacional
    de toda a linha do tempo projetada.
    """
    
    horizon_days: int
    starting_balance: float
    ending_balance: float
    worst_balance: float
    negative_day: Optional[int]
    risk_level: RiskLevel
    total_shadow_impact: float


class CashflowProjector:
    """
    Motor de simulação financeira diária.

    Ele executa uma simulação determinística do futuro financeiro
    aplicando eventos financeiros previstos sobre o saldo atual.

    Esse motor é:

        - determinístico
        - explicável
        - auditável
        - resiliente

    Nenhum cálculo é estatístico aqui.
    Tudo é baseado em eventos financeiros reais detectados.
    """
    
    def __init__(self, horizon_days: int = 30):
        self.horizon_days = horizon_days
        self.logger = logging.getLogger(__name__)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CORE SIMULATION ENGINE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def project(
        self,
        transactions_df: pl.DataFrame,
        shadow_invoices_df: pl.DataFrame,
        current_balance: Optional[float] = None
    ) -> pl.DataFrame:
        """
        Executa a simulação financeira diária.

        Estratégia:
            1. Determinar saldo inicial confiável
            2. Construir calendário futuro
            3. Indexar eventos financeiros por data
            4. Simular dia a dia:
                   saldo[t+1] = saldo[t] + soma(eventos_do_dia)
            5. Persistir rastreabilidade de eventos

        Resultado:
            Uma linha do tempo financeira completamente explicável.
        """

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: Validações e preparação dos dados
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        if transactions_df.is_empty():
            raise ValueError("DataFrame de transações está vazio")

        if "transaction_date" not in transactions_df.columns:
            raise ValueError("transactions_df precisa conter 'transaction_date'")

        # Ordenar cronologicamente
        df_sorted = transactions_df.sort("transaction_date")

        # Determinar saldo inicial confiável
        if current_balance is not None:
            starting_balance = float(current_balance)
        else:
            if "balance" not in df_sorted.columns:
                raise ValueError(
                    "transactions_df não possui coluna 'balance' e current_balance não foi informado"
                )
            _last_balance = df_sorted["balance"][-1]
            if _last_balance is None:
                raise ValueError(
                    "Última transação não possui 'balance' — informe current_balance explicitamente"
                )
            starting_balance = float(_last_balance)

        # Data base da projeção: dia seguinte à última transação real
        last_date = df_sorted["transaction_date"].max()
        start_date = last_date

        self.logger.info(
            f"Inicializando projeção: saldo R$ {starting_balance:,.2f} em {start_date}"
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: Construir linha do tempo futura
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        calendar = [
            start_date + timedelta(days=i + 1)
            for i in range(self.horizon_days)
        ]

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: Indexar eventos financeiros por data
        #
        # Aqui transformamos:
        #   shadow_invoices_df
        #
        # Em:
        #   { date -> [eventos] }
        #
        # Isso permite lookup O(1) por dia
        # durante a simulação.
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        events_by_day: Dict[Any, List[Dict[str, Any]]] = {}

        if not shadow_invoices_df.is_empty():

            events_df = shadow_invoices_df.with_columns(
                pl.col("next_due_date").dt.date().alias("date")
            )

            for row in events_df.iter_rows(named=True):
                day = row["date"]

                event = {
                    "type": row.get("type", "shadow"),
                    "merchant": row.get("merchant", "UNKNOWN"),
                    "amount": float(row["amount"] or 0.0),
                    "origin": row.get("origin", "shadow_invoice")
                }

                events_by_day.setdefault(day, []).append(event)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 4: Simulação financeira diária (núcleo matemático)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        current_balance = starting_balance
        projection_rows = []

        for idx, day in enumerate(calendar, start=1):

            daily_events = events_by_day.get(day, [])

            # Soma financeira dos eventos do dia
            daily_delta = sum(e["amount"] for e in daily_events)

            # Atualizar saldo
            current_balance += daily_delta

            projection_rows.append({
                "date": day,
                "starting_balance": starting_balance,
                "projected_balance": round(current_balance, 2),
                "events": daily_events,
                "expenses": daily_delta,
                "risk_flag": "NEGATIVE_BALANCE" if current_balance < 0 else None
            })

        projection_df = pl.DataFrame(projection_rows)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # LOG FINAL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        worst_balance = projection_df['projected_balance'].min() or 0.0
        self.logger.info(
            f"Projeção finalizada: "
            f"Saldo final R$ {current_balance:,.2f} | "
            f"Menor saldo R$ {worst_balance:,.2f}"
        )

        return projection_df
