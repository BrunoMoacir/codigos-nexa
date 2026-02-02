"""
test_shadow_invoices_debug.py - Teste com debug detalhado

Investiga por que o detector não está encontrando parcelamentos.
"""

import polars as pl
import logging
from app.etl.shadow_invoices.runner import run_shadow_invoice_detection

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HABILITAR LOGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s'
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRIAR DATASET DE TESTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("="*70)
print("🧪 TESTE: Shadow Invoice Detection (DEBUG)")
print("="*70)

df = pl.DataFrame({
    "transaction_id": [1, 2, 3, 4, 5, 6],
    "description": [
        "Netflix",           # Assinatura
        "Netflix",
        "Netflix",
        "Amazon Parcelado",  # Parcelamento
        "Amazon Parcelado",
        "Amazon Parcelado"
    ],
    "amount": [-39.9, -39.9, -39.9, -120.0, -120.0, -120.0],
    "transaction_date": pl.date_range(
        start=pl.date(2025, 7, 1),
        end=pl.date(2025, 12, 1),
        interval="1mo",
        eager=True
    )
})

print("\n📋 DATASET DE ENTRADA:")
print(df)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DEBUG MANUAL: AGRUPAR E VERIFICAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n" + "="*70)
print("🔍 DEBUG: Agrupamento manual")
print("="*70)

df_with_month = df.with_columns([
    pl.col("transaction_date").dt.truncate("1mo").alias("month")
])

grouped = (
    df_with_month.group_by(["description", "amount"])
    .agg([
        pl.count().alias("count"),
        pl.col("month").n_unique().alias("months")
    ])
)

print("\n📊 AGRUPAMENTOS:")
print(grouped)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTAR FILTROS INDIVIDUAIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n" + "="*70)
print("🔍 DEBUG: Testando filtros")
print("="*70)

# Filtro 1: count >= 3
filter_1 = grouped.filter(pl.col("count") >= 3)
print(f"\n✅ Filtro 1 (count >= 3): {len(filter_1)} resultados")
print(filter_1)

# Filtro 2: months >= 2
filter_2 = filter_1.filter(pl.col("months") >= 2)
print(f"\n✅ Filtro 2 (months >= 2): {len(filter_2)} resultados")
print(filter_2)

# Filtro 3: Contém palavra-chave (case-insensitive)
keywords_pattern = "(?i)(parcel|parc|parcela|x|/)"
filter_3 = filter_2.filter(
    pl.col("description").str.contains(keywords_pattern)
)
print(f"\n✅ Filtro 3 (keyword): {len(filter_3)} resultados")
print(filter_3)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RODAR DETECTOR COMPLETO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n" + "="*70)
print("🚀 RODANDO DETECTOR COMPLETO")
print("="*70)

result = run_shadow_invoice_detection(df)

print("\n📊 RESULTADO FINAL:")
if result.is_empty():
    print("⚠️  Nenhum shadow invoice detectado!")
else:
    print(result)

print("\n" + "="*70)
print("✅ TESTE CONCLUÍDO")
print("="*70)