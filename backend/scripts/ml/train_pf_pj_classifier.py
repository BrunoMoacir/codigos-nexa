"""
train_pf_pj_classifier.py - Treina Modelo Random Forest para Classificador PF/PJ

Objetivo: Treinar e validar modelo de ML para distinguir transações PF vs PJ,
usando o dataset rotulado criado anteriormente.

Features: 18 features (temporal, monetário, textual, categórico, recorrência)
Modelo: Random Forest Classifier
Avaliação: Accuracy, Precision, Recall, F1-Score
"""

import polars as pl
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder, StandardScaler
import joblib
import numpy as np
import sys
import os

# Adicionar o diretório backend ao path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def load_training_data():
    """Carrega dataset de treinamento"""
    data_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'training_dataset_pf_pj.parquet')
    df = pl.read_parquet(data_path)
    print(f"📊 Dataset carregado: {len(df)} amostras")

    # Converte para pandas para sklearn
    df_pd = df.to_pandas()
    return df_pd

def preprocess_features(df):
    """Pré-processa features para ML"""
    # Separa features e target
    feature_cols = [
        'hour_of_day', 'day_of_week', 'is_weekend', 'is_business_hour',
        'amount', 'amount_abs', 'amount_log', 'transaction_type', 'amount_category',
        'pf_keyword_score', 'pj_keyword_score', 'has_business_terms',
        'category', 'merchant_category', 'is_recurring'
    ]

    X = df[feature_cols].copy()
    y = df['label'].map({'PF': 0, 'PJ': 1})  # Encode labels

    # Encode categorical features
    categorical_cols = ['transaction_type', 'amount_category', 'category', 'merchant_category']

    encoders = {}
    for col in categorical_cols:
        encoder = LabelEncoder()
        X[col] = encoder.fit_transform(X[col].astype(str))
        encoders[col] = encoder

    # Scale numerical features
    numerical_cols = ['hour_of_day', 'day_of_week', 'amount', 'amount_abs', 'amount_log',
                     'pf_keyword_score', 'pj_keyword_score']

    scaler = StandardScaler()
    X[numerical_cols] = scaler.fit_transform(X[numerical_cols])

    return X, y, encoders, scaler

def train_random_forest(X, y):
    """Treina modelo Random Forest"""
    print("🌲 Treinando Random Forest...")

    # Split train/test (80/20)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Modelo com hiperparâmetros otimizados
    rf_model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=2,
        min_samples_leaf=1,
        random_state=42,
        class_weight='balanced'  # Balanceia classes PF/PJ
    )

    # Treina modelo
    rf_model.fit(X_train, y_train)

    # Predições
    y_pred = rf_model.predict(X_test)
    y_pred_proba = rf_model.predict_proba(X_test)

    return rf_model, X_train, X_test, y_train, y_test, y_pred, y_pred_proba

def evaluate_model(rf_model, X, y, y_pred, X_test, y_test):
    """Avalia performance do modelo"""
    print("\n📊 AVALIAÇÃO DO MODELO")
    print("=" * 40)

    # Classification report
    print("Classification Report:")
    print(classification_report(y_test, y_pred, target_names=['PF', 'PJ']))

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    print("\nConfusion Matrix:")
    print("          Predicted")
    print("          PF    PJ")
    print(f"Actual PF  {cm[0][0]}     {cm[0][1]}")
    print(f"      PJ  {cm[1][0]}     {cm[1][1]}")

    # Cross-validation
    cv_scores = cross_val_score(rf_model, X, y, cv=5, scoring='accuracy')
    print(f"Cross-Validation Accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std() * 2:.3f})")
    # Feature importance
    feature_importance = pd.DataFrame({
        'feature': X.columns,
        'importance': rf_model.feature_importances_
    }).sort_values('importance', ascending=False)

    print("\n🔍 Top 10 Features Mais Importantes:")
    for i, row in feature_importance.head(10).iterrows():
        print(f"   {row['feature']}: {row['importance']:.3f}")

    return feature_importance

def save_model(rf_model, encoders, scaler):
    """Salva modelo e preprocessors"""
    # Salva modelo
    model_path = os.path.join(os.path.dirname(__file__), '..', '..', 'models', 'pf_pj_classifier.pkl')
    joblib.dump(rf_model, model_path)

    # Salva encoders e scaler
    encoders_path = os.path.join(os.path.dirname(__file__), '..', '..', 'models', 'feature_encoders.pkl')
    scaler_path = os.path.join(os.path.dirname(__file__), '..', '..', 'models', 'feature_scaler.pkl')
    joblib.dump(encoders, encoders_path)
    joblib.dump(scaler, scaler_path)

    print(f"\n💾 Modelo salvo em: {model_path}")
    print(f"   Encoders salvos em: {encoders_path}")
    print(f"   Scaler salvo em: {scaler_path}")

def main():
    """Função principal"""
    print("🎯 TREINAMENTO DO CLASSIFICADOR PF/PJ")
    print("=" * 50)

    # Carrega dados
    df = load_training_data()
    print(f"   Distribuição: PF={len(df[df['label']=='PF'])}, PJ={len(df[df['label']=='PJ'])}")

    # Pré-processa
    X, y, encoders, scaler = preprocess_features(df)
    print(f"   Features: {X.shape[1]} colunas")

    # Treina modelo
    rf_model, X_train, X_test, y_train, y_test, y_pred, y_pred_proba = train_random_forest(X, y)

    # Avalia
    feature_importance = evaluate_model(rf_model, X, y, y_pred, X_test, y_test)

    # Salva modelo
    save_model(rf_model, encoders, scaler)

    print("\n✅ Treinamento concluído!")
    print("\n🚀 Modelo pronto para integração no pipeline ETL")

    # Teste rápido
    print("\n🧪 Teste rápido com primeira amostra:")
    sample = X.iloc[0:1]
    prediction = rf_model.predict(sample)[0]
    proba = rf_model.predict_proba(sample)[0]
    actual = 'PF' if y.iloc[0] == 0 else 'PJ'
    predicted = 'PF' if prediction == 0 else 'PJ'

    print(f"   Real: {actual} | Previsto: {predicted}")
    print(f"   Probabilidades: PF={proba[0]:.3f}, PJ={proba[1]:.3f}")
if __name__ == "__main__":
    main()