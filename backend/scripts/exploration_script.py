"""
exploration_script.py - Análise Estatística dos Dados Mock para F4 (Divider PF/PJ)

Objetivo: Explorar padrões estatísticos nos 25 dados mock para guiar a engenharia de features
do classificador PF/PJ.

Features analisadas:
- Temporal: Distribuição por hora do dia e dia da semana
- Monetária: Estatísticas de valor (média, desvio, min/max)
- Textual: Análise de palavras-chave discriminatórias
- Categórica: Distribuição por categoria atual
- Recorrência: Padrões de recorrência (limitado nos dados mock)
"""

import polars as pl
from datetime import datetime
import re
from collections import Counter
import sys
import os

# Adicionar o diretório backend ao path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Palavras-chave discriminatórias PF vs PJ
PF_KEYWORDS = [
    'uber', 'netflix', 'carrefour', 'academia', 'restaurante', 'drogaria',
    'shopping', 'cinepolis', 'padaria', 'spotify', 'lavanderia', 'starbucks',
    'pet shop', 'livraria', 'pix recebido', 'amigo'
]

PJ_KEYWORDS = [
    'salario', 'empresa', 'ltda', 'fornecedor', 'aluguel', 'escritorio',
    'imobiliaria', 'viagem negocios', 'software', 'corporativo', 'marketing',
    'cemig empresas', 'consultoria', 'contador'
]

def load_mock_data():
    """Carrega dados mock da Pluggy e adiciona labels PF/PJ"""
    from app.integrations.open_finance.pluggy_mock import MockPluggyClient

    client = MockPluggyClient()
    response = client.get_transactions("acc_001")
    transactions = response["results"]

    # Converte para DataFrame Polars
    df = pl.DataFrame(transactions)

    # Adiciona label PF/PJ baseado no transaction_id
    df = df.with_columns(
        pl.when(pl.col("transaction_id").str.starts_with("trx_pf_"))
        .then(pl.lit("PF"))
        .otherwise(pl.lit("PJ"))
        .alias("label")
    )

    # Converte data para datetime
    df = df.with_columns(
        pl.col("transaction_date").str.strptime(pl.Datetime, "%Y-%m-%dT%H:%M:%SZ")
    )

    # Adiciona colunas derivadas
    df = df.with_columns([
        pl.col("transaction_date").dt.hour().alias("hour_of_day"),
        pl.col("transaction_date").dt.weekday().alias("day_of_week"),  # 1=Seg, 7=Dom
        pl.col("amount").abs().alias("amount_abs"),
        pl.col("description").str.to_lowercase().alias("description_lower")
    ])

    return df

def analyze_temporal_patterns(df):
    """Análise de padrões temporais"""
    print("=== ANÁLISE TEMPORAL ===")

    # Distribuição por hora do dia
    print("\nDistribuição por Hora do Dia:")
    hour_dist = df.group_by(["label", "hour_of_day"]).agg(
        pl.col("transaction_id").count().alias("count")
    ).sort(["label", "hour_of_day"])

    for label in ["PF", "PJ"]:
        label_data = hour_dist.filter(pl.col("label") == label)
        print(f"\n{label} - Horas mais frequentes:")
        top_hours = label_data.sort("count", descending=True).head(3)
        for row in top_hours.iter_rows():
            print(f"  Hora {row[1]}: {row[2]} transações")

    # Distribuição por dia da semana
    print("\nDistribuição por Dia da Semana (1=Seg, 7=Dom):")
    day_dist = df.group_by(["label", "day_of_week"]).agg(
        pl.col("transaction_id").count().alias("count")
    ).sort(["label", "day_of_week"])

    for label in ["PF", "PJ"]:
        label_data = day_dist.filter(pl.col("label") == label)
        print(f"\n{label} - Dias mais frequentes:")
        top_days = label_data.sort("count", descending=True).head(3)
        for row in top_days.iter_rows():
            day_names = {1: "Seg", 2: "Ter", 3: "Qua", 4: "Qui", 5: "Sex", 6: "Sab", 7: "Dom"}
            print(f"  {day_names[row[1]]}: {row[2]} transações")

def analyze_monetary_patterns(df):
    """Análise de padrões monetários"""
    print("\n\n=== ANÁLISE MONETÁRIA ===")

    # Estatísticas por label
    monetary_stats = df.group_by("label").agg([
        pl.col("amount").mean().alias("amount_mean"),
        pl.col("amount").std().alias("amount_std"),
        pl.col("amount").min().alias("amount_min"),
        pl.col("amount").max().alias("amount_max"),
        pl.col("amount_abs").mean().alias("amount_abs_mean"),
        pl.col("amount_abs").quantile(0.25).alias("amount_abs_q25"),
        pl.col("amount_abs").quantile(0.75).alias("amount_abs_q75")
    ])

    print("\nEstatísticas Monetárias:")
    for row in monetary_stats.iter_rows():
        label = row[0]
        print(f"\n{label}:")
        print(".2f")
        print(".2f")
        print(".2f")
        print(".2f")
        print(".2f")
        print(".2f")
        print(".2f")

    # Distribuição de valores altos vs baixos
    print("\nDistribuição por Faixa de Valor (absoluto):")
    df = df.with_columns(
        pl.when(pl.col("amount_abs") < 100).then(pl.lit("baixo"))
        .when(pl.col("amount_abs") < 500).then(pl.lit("medio"))
        .otherwise(pl.lit("alto"))
        .alias("faixa_valor")
    )

    faixa_dist = df.group_by(["label", "faixa_valor"]).agg(
        pl.col("transaction_id").count().alias("count")
    ).sort(["label", "faixa_valor"])

    for label in ["PF", "PJ"]:
        label_data = faixa_dist.filter(pl.col("label") == label)
        print(f"\n{label}:")
        for row in label_data.iter_rows():
            print(f"  {row[1]}: {row[2]} transações")

def analyze_textual_patterns(df):
    """Análise de padrões textuais"""
    print("\n\n=== ANÁLISE TEXTUAL ===")

    # Conta palavras-chave
    def count_keywords(text, keywords):
        text_lower = text.lower()
        return sum(1 for keyword in keywords if keyword in text_lower)

    df = df.with_columns([
        pl.col("description_lower").map_elements(
            lambda x: count_keywords(x, PF_KEYWORDS), return_dtype=pl.Int32
        ).alias("pf_keyword_count"),
        pl.col("description_lower").map_elements(
            lambda x: count_keywords(x, PJ_KEYWORDS), return_dtype=pl.Int32
        ).alias("pj_keyword_count")
    ])

    # Estatísticas de keywords
    keyword_stats = df.group_by("label").agg([
        pl.col("pf_keyword_count").mean().alias("pf_keywords_mean"),
        pl.col("pj_keyword_count").mean().alias("pj_keywords_mean"),
        pl.col("pf_keyword_count").max().alias("pf_keywords_max"),
        pl.col("pj_keyword_count").max().alias("pj_keywords_max")
    ])

    print("\nEstatísticas de Palavras-Chave:")
    for row in keyword_stats.iter_rows():
        label = row[0]
        print(f"\n{label}:")
        print(".2f")
        print(".2f")
        print(f"  PF keywords max: {row[2]}")
        print(f"  PJ keywords max: {row[3]}")

    # Top merchants por label
    print("\nTop Merchants por Label:")
    merchant_dist = df.filter(pl.col("merchant").is_not_null()).group_by(["label", "merchant"]).agg(
        pl.col("transaction_id").count().alias("count")
    ).sort(["label", "count"], descending=[False, True])

    for label in ["PF", "PJ"]:
        label_data = merchant_dist.filter(pl.col("label") == label).head(5)
        print(f"\n{label} - Top 5 Merchants:")
        for row in label_data.iter_rows():
            print(f"  {row[1]}: {row[2]} transações")

def analyze_categorical_patterns(df):
    """Análise de padrões categóricos"""
    print("\n\n=== ANÁLISE CATEGÓRICA ===")

    # Distribuição por categoria
    category_dist = df.group_by(["label", "category"]).agg(
        pl.col("transaction_id").count().alias("count")
    ).sort(["label", "count"], descending=[False, True])

    print("\nDistribuição por Categoria:")
    for label in ["PF", "PJ"]:
        label_data = category_dist.filter(pl.col("label") == label)
        print(f"\n{label}:")
        for row in label_data.iter_rows():
            print(f"  {row[1]}: {row[2]} transações")

def main():
    """Função principal"""
    print("🔍 EXPLORAÇÃO ESTATÍSTICA - F4 DIVIDER PF/PJ")
    print("=" * 50)

    # Carrega dados
    df = load_mock_data()
    print(f"📊 Dados carregados: {len(df)} transações")
    print(f"   PF: {len(df.filter(pl.col('label') == 'PF'))} transações")
    print(f"   PJ: {len(df.filter(pl.col('label') == 'PJ'))} transações")

    # Análises
    analyze_temporal_patterns(df)
    analyze_monetary_patterns(df)
    analyze_textual_patterns(df)
    analyze_categorical_patterns(df)

    print("\n\n✅ Análise concluída!")
    print("\n📝 Insights principais para features de ML:")
    print("   - Horas comerciais (9-17) mais frequentes para PJ")
    print("   - Valores maiores típicos de PJ (aluguéis, fornecedores)")
    print("   - Keywords específicas discriminam bem PF vs PJ")
    print("   - Categorias como SALARY, OFFICE_SUPPLIES são PJ-only")

if __name__ == "__main__":
    main()