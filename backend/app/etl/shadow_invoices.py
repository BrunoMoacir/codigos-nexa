"""
app/etl/shadow_invoices.py

Este módulo é responsável por gerar a chamada "Shadow Invoice" da Nexa.

A Shadow Invoice é uma projeção matemática da fatura futura do usuário,
calculada exclusivamente a partir do seu histórico real de transações,
sem depender de PDFs, OCR ou dados instáveis das APIs bancárias.

Sua função principal é garantir que:
    - O sistema nunca fique sem previsão
    - O fluxo de caixa futuro continue funcional mesmo com falhas no Open Finance
    - Toda previsão seja explicável, auditável e determinística

Este módulo NÃO faz previsão estatística.
Ele apenas transforma padrões históricos confiáveis em eventos futuros explícitos.
"""

import polars as pl

# Detecta assinaturas e gastos recorrentes
from app.analysis.recurring_detector import RecurringDetector

# Detecta parcelamentos e projeta parcelas futuras
from app.analysis.shadow_invoice_detector import ShadowInvoiceDetector

# Camada de persistência (banco ou parquet)
from app.db import save_shadow_events


class ShadowInvoiceETL:
    """
    Orquestrador da geração de eventos financeiros futuros.

    Responsabilidade:
        - Consumir transações já limpas e normalizadas (transactions_clean)
        - Identificar padrões matemáticos confiáveis
        - Gerar eventos financeiros futuros
        - Persistir esses eventos para uso posterior no forecast

    Esse módulo NÃO toma decisões.
    Ele apenas detecta padrões objetivos presentes nos dados.
    """

    def __init__(self):
        """
        Inicializa os detectores principais.

        A separação em dois detectores garante:
            - Modularidade
            - Testabilidade isolada
            - Evolução futura independente
        """

        # Detector de recorrência:
        # Encontra assinaturas e despesas fixas mensais.
        self.recurring_detector = RecurringDetector()

        # Detector de parcelamento:
        # Identifica padrões 01/10, 02/10, etc, e projeta parcelas futuras.
        self.shadow_detector = ShadowInvoiceDetector()

    def run(self, transactions: pl.DataFrame) -> pl.DataFrame:
        """
        Executa o pipeline completo da Shadow Invoice.

        Entrada:
            transactions: DataFrame Polars contendo transações já limpas,
                          classificadas e normalizadas.

        Saída:
            DataFrame Polars contendo eventos financeiros futuros projetados,
            com estrutura:

            date | merchant | amount | type | origin

        Onde:
            type   -> 'recurrence' | 'parcel'
            origin -> explicação semântica da origem da projeção
        """

        # ---------------------------------------------------------------------
        # 1️⃣ Detectar recorrências
        #
        # Objetivo:
        #     Encontrar gastos previsíveis que ocorrem todo mês,
        #     como assinaturas, mensalidades, planos e contas fixas.
        #
        # Impacto financeiro:
        #     Esses valores representam compromissos futuros obrigatórios
        #     e devem ser considerados no Safe-to-Spend.
        # ---------------------------------------------------------------------

        recurring_events = self.recurring_detector.detect(transactions)

        # ---------------------------------------------------------------------
        # 2️⃣ Detectar parcelamentos
        #
        # Objetivo:
        #     Identificar compras parceladas e projetar automaticamente
        #     as parcelas futuras ainda não debitadas.
        #
        # Impacto financeiro:
        #     Parcelas futuras representam dívida já assumida.
        #     Ignorar isso gera falsa sensação de liquidez.
        # ---------------------------------------------------------------------

        parcel_events = self.shadow_detector.detect(transactions)

        # ---------------------------------------------------------------------
        # 3️⃣ Consolidar eventos futuros
        #
        # Ambos os conjuntos representam compromissos financeiros reais,
        # apenas obtidos por fontes diferentes.
        #
        # A concatenação cria a "Shadow Invoice" unificada.
        # ---------------------------------------------------------------------

        events = pl.concat([recurring_events, parcel_events], how="vertical")

        # ---------------------------------------------------------------------
        # 4️⃣ Persistência (Audit Trail)
        #
        # A Shadow Invoice precisa ser:
        #     - auditável
        #     - versionada
        #     - reproduzível
        #
        # Por isso, persistimos os eventos projetados,
        # mantendo rastreabilidade completa.
        # ---------------------------------------------------------------------

        if not events.is_empty():
            save_shadow_events(events)

        return events
