import polars as pl
from datetime import date
from app.cashflow.projector import CashflowProjector

# 1. Histórico: O usuário termina com R$ 1.900,00
transactions_df = pl.DataFrame({
    "transaction_date": [date(2024, 1, 1), date(2024, 1, 5)],
    "amount": [7200.0, -5300.0],
    "balance": [7200.0, 1900.0]
})

# 2. Futuro: Temos uma conta de R$ 2.000,00 vencendo dia 20/01
# Isso deve deixar o saldo NEGATIVO em -R$ 100,00
shadow_invoices_df = pl.DataFrame({
    "amount": [-2000.0], 
    "next_due_date": [date(2024, 1, 20)]
})

# 3. Projetar 30 dias à frente
projector = CashflowProjector(horizon_days=30)

print(f"--- INICIANDO PROJEÇÃO COM SALDO DE R$ {1900.00} ---")
print(f"--- CONTA FUTURA DETECTADA: R$ 2.000,00 (Vence em 20/01) ---\n")

projection = projector.project(
    transactions_df=transactions_df, 
    shadow_invoices_df=shadow_invoices_df
)

# 4. Mostrar os dias críticos (onde o saldo vira negativo)
# Filtramos apenas a data do vencimento e os dias próximos para visualizar
start_view = date(2024, 1, 18)
end_view = date(2024, 1, 22)

view = projection.filter(
    (pl.col("date") >= start_view) & 
    (pl.col("date") <= end_view)
)

print(view)