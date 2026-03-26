"""
create_labeled_dataset.py - Cria Dataset Rotulado para Treinamento do Classificador PF/PJ

Objetivo: Gerar dataset inicial com labels PF/PJ e features extraídas dos dados mock,
preparado para treinamento do modelo de ML (Random Forest).

Features incluídas:
- Temporais: hour_of_day, day_of_week, is_weekend, is_business_hour
- Monetárias: amount, amount_abs, amount_log, amount_category
- Textuais: pf_keyword_score, pj_keyword_score, has_business_terms
- Categóricas: category (one-hot encoded), merchant_category
- Recorrência: is_recurring (simulado)
"""

import polars as pl
from datetime import datetime
import numpy as np
import sys
import os

# Adicionar o diretório backend ao path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Palavras-chave para scoring
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

def load_and_label_data():
    """Carrega dados mock e adiciona labels PF/PJ"""
    from app.integrations.open_finance.pluggy_mock import MockPluggyClient

    client = MockPluggyClient()
    response = client.get_transactions("acc_001")
    transactions = response["results"]

    df = pl.DataFrame(transactions)

    # Label PF/PJ
    df = df.with_columns(
        pl.when(pl.col("transaction_id").str.starts_with("trx_pf_"))
        .then(pl.lit("PF"))
        .otherwise(pl.lit("PJ"))
        .alias("label")
    )

    # Converte data
    df = df.with_columns(
        pl.col("transaction_date").str.strptime(pl.Datetime, "%Y-%m-%dT%H:%M:%SZ")
    )

    return df

def extract_temporal_features(df):
    """Extrai features temporais"""
    df = df.with_columns([
        pl.col("transaction_date").dt.hour().alias("hour_of_day"),
        pl.col("transaction_date").dt.weekday().alias("day_of_week"),  # 1=Seg, 7=Dom
        pl.when(pl.col("transaction_date").dt.weekday() >= 6)
        .then(pl.lit(1))
        .otherwise(pl.lit(0))
        .alias("is_weekend"),
        pl.when((pl.col("transaction_date").dt.hour() >= 9) &
                (pl.col("transaction_date").dt.hour() <= 17))
        .then(pl.lit(1))
        .otherwise(pl.lit(0))
        .alias("is_business_hour")
    ])

    return df

def extract_monetary_features(df):
    """Extrai features monetárias"""
    df = df.with_columns([
        pl.col("amount").abs().alias("amount_abs"),
        (pl.col("amount").abs() + 1).log().alias("amount_log"),  # +1 para evitar log(0)
        pl.when(pl.col("amount") > 0).then(pl.lit("credit")).otherwise(pl.lit("debit")).alias("transaction_type"),
        pl.when(pl.col("amount").abs() < 50).then(pl.lit("very_low"))
        .when(pl.col("amount").abs() < 100).then(pl.lit("low"))
        .when(pl.col("amount").abs() < 500).then(pl.lit("medium"))
        .when(pl.col("amount").abs() < 1000).then(pl.lit("high"))
        .otherwise(pl.lit("very_high"))
        .alias("amount_category")
    ])

    return df

def extract_textual_features(df):
    """Extrai features textuais"""
    def calculate_keyword_score(text, keywords):
        """Calcula score baseado em presença de keywords"""
        if not text:
            return 0
        text_lower = text.lower()
        score = 0
        for keyword in keywords:
            if keyword in text_lower:
                score += 1
        return score

    df = df.with_columns([
        pl.col("description").str.to_lowercase().alias("description_lower"),
        pl.col("description").map_elements(
            lambda x: calculate_keyword_score(x, PF_KEYWORDS) if x else 0,
            return_dtype=pl.Int32
        ).alias("pf_keyword_score"),
        pl.col("description").map_elements(
            lambda x: calculate_keyword_score(x, PJ_KEYWORDS) if x else 0,
            return_dtype=pl.Int32
        ).alias("pj_keyword_score"),
        pl.when(pl.col("description").str.contains(r"(?i)(empresa|ltda|fornecedor|escritorio|corporativo)"))
        .then(pl.lit(1))
        .otherwise(pl.lit(0))
        .alias("has_business_terms")
    ])

    return df

def extract_categorical_features(df):
    """Extrai features categóricas"""
    # Merchant category baseada no merchant
    df = df.with_columns([
        pl.when(pl.col("merchant").is_null())
        .then(pl.lit("unknown"))
        .when(pl.col("merchant").str.contains(r"(?i)(uber|starbucks|netflix|spotify|cinepolis)"))
        .then(pl.lit("entertainment"))
        .when(pl.col("merchant").str.contains(r"(?i)(carrefour|padaria|restaurante)"))
        .then(pl.lit("food_grocery"))
        .when(pl.col("merchant").str.contains(r"(?i)(academia|drogaria|pet shop)"))
        .then(pl.lit("health_pets"))
        .when(pl.col("merchant").str.contains(r"(?i)(shopping|livraria)"))
        .then(pl.lit("shopping_education"))
        .when(pl.col("merchant").str.contains(r"(?i)(lavanderia)"))
        .then(pl.lit("services"))
        .when(pl.col("merchant").str.contains(r"(?i)(papelaria|microsoft|fornecedor|imobiliaria|latam|cemig|vivo|agencia|contador)"))
        .then(pl.lit("business"))
        .otherwise(pl.lit("other"))
        .alias("merchant_category")
    ])

    return df

def extract_recurrence_features(df):
    """Extrai features de recorrência (simulado para dados mock)"""
    # Simula recorrência baseada em categoria e valor
    df = df.with_columns([
        pl.when((pl.col("category").is_in(["ENTERTAINMENT", "FOOD", "HEALTH", "SERVICES"])) &
                (pl.col("amount").abs() < 200))
        .then(pl.lit(1))
        .otherwise(pl.lit(0))
        .alias("is_recurring")
    ])

    return df

def create_training_dataset():
    """Cria dataset completo para treinamento"""
    print("🔧 Criando dataset rotulado para treinamento...")

    # Carrega dados
    df = load_and_label_data()

    # Extrai todas as features
    df = extract_temporal_features(df)
    df = extract_monetary_features(df)
    df = extract_textual_features(df)
    df = extract_categorical_features(df)
    df = extract_recurrence_features(df)

    # Seleciona colunas relevantes para ML
    feature_cols = [
        # Target
        "label",

        # Temporais
        "hour_of_day", "day_of_week", "is_weekend", "is_business_hour",

        # Monetárias
        "amount", "amount_abs", "amount_log", "transaction_type", "amount_category",

        # Textuais
        "pf_keyword_score", "pj_keyword_score", "has_business_terms",

        # Categóricas
        "category", "merchant_category",

        # Recorrência
        "is_recurring",

        # Metadata (para referência)
        "transaction_id", "description", "merchant"
    ]

    training_df = df.select(feature_cols)

    # Salva dataset
    output_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'training_dataset_pf_pj.parquet')
    training_df.write_parquet(output_path)

    # Também salva CSV para visualização
    csv_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'training_dataset_pf_pj.csv')
    training_df.write_csv(csv_path)

    print(f"✅ Dataset criado com {len(training_df)} amostras")
    print(f"   PF: {len(training_df.filter(pl.col('label') == 'PF'))}")
    print(f"   PJ: {len(training_df.filter(pl.col('label') == 'PJ'))}")
    print(f"   Salvo em: {output_path}")

    # Mostra amostra
    print("\n📊 Amostra do dataset:")
    print(training_df.head(5))

    return training_df

def main():
    """Função principal"""
    print("🎯 CRIANDO DATASET ROTULADO - F4 DIVIDER PF/PJ")
    print("=" * 50)

    dataset = create_training_dataset()

    print("\n📋 Features extraídas:")
    print("   ✅ Temporais: hour_of_day, day_of_week, is_weekend, is_business_hour")
    print("   ✅ Monetárias: amount, amount_abs, amount_log, transaction_type, amount_category")
    print("   ✅ Textuais: pf_keyword_score, pj_keyword_score, has_business_terms")
    print("   ✅ Categóricas: category, merchant_category")
    print("   ✅ Recorrência: is_recurring")

    print("\n🚀 Pronto para treinamento do Random Forest!")

if __name__ == "__main__":
    main()