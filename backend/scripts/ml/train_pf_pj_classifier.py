"""
train_pf_pj_classifier.py - Treina Modelo Random Forest para Classificador PF/PJ

Objetivo: Treinar e validar modelo de ML para distinguir transações PF vs PJ,
usando o dataset rotulado criado anteriormente.

Features: 18 features (temporal, monetário, textual, categórico, recorrência)
Modelo: Random Forest Classifier
Avaliação: Accuracy, Precision, Recall, F1-Score
"""

import polars as pl
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
    return df

def preprocess_features(df: pl.DataFrame):
    """Pré-processa features para ML"""
    feature_cols = [
        'hour_of_day', 'day_of_week', 'is_weekend', 'is_business_hour',
        'amount', 'amount_abs', 'amount_log', 'transaction_type', 'amount_category',
        'pf_keyword_score', 'pj_keyword_score', 'has_business_terms',
        'category', 'merchant_category', 'is_recurring'
    ]
    categorical_cols = ['transaction_type', 'amount_category', 'category', 'merchant_category']
    numerical_cols = ['hour_of_day', 'day_of_week', 'amount', 'amount_abs', 'amount_log',
                      'pf_keyword_score', 'pj_keyword_score']

    # Encode labels
    y = np.array([0 if v == 'PF' else 1 for v in df['label'].to_list()])

    # Build float numpy matrix in correct column order
    X = np.zeros((len(df), len(feature_cols)), dtype=float)
    col_idx = {col: i for i, col in enumerate(feature_cols)}

    # Encode categorical features
    encoders = {}
    for col in categorical_cols:
        col_data = df[col].cast(pl.Utf8).to_numpy().astype(str)
        encoder = LabelEncoder()
        X[:, col_idx[col]] = encoder.fit_transform(col_data).astype(float)
        encoders[col] = encoder

    # Copy numerical features
    for col in feature_cols:
        if col not in categorical_cols:
            X[:, col_idx[col]] = df[col].cast(pl.Float64).to_numpy()

    # Scale numerical features
    scaler = StandardScaler()
    num_indices = [col_idx[col] for col in numerical_cols]
    X[:, num_indices] = scaler.fit_transform(X[:, num_indices])

    return X, y, encoders, scaler, feature_cols

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

def evaluate_model(rf_model, X, y, y_pred, X_test, y_test, feature_cols):
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

    # Feature importance usando numpy/sorted list
    importances = sorted(
        zip(feature_cols, rf_model.feature_importances_),
        key=lambda x: x[1],
        reverse=True,
    )
    print("\n🔍 Top 10 Features Mais Importantes:")
    for feat, imp in importances[:10]:
        print(f"   {feat}: {imp:.3f}")

    return importances

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
    pf_count = df.filter(pl.col('label') == 'PF').height
    pj_count = df.filter(pl.col('label') == 'PJ').height
    print(f"   Distribuição: PF={pf_count}, PJ={pj_count}")

    # Pré-processa
    X, y, encoders, scaler, feature_cols = preprocess_features(df)
    print(f"   Features: {X.shape[1]} colunas")

    # Treina modelo
    rf_model, X_train, X_test, y_train, y_test, y_pred, y_pred_proba = train_random_forest(X, y)

    # Avalia
    feature_importance = evaluate_model(rf_model, X, y, y_pred, X_test, y_test, feature_cols)

    # Salva modelo
    save_model(rf_model, encoders, scaler)

    print("\n✅ Treinamento concluído!")
    print("\n🚀 Modelo pronto para integração no pipeline ETL")

    # Teste rápido
    print("\n🧪 Teste rápido com primeira amostra:")
    sample = X[0:1]
    prediction = rf_model.predict(sample)[0]
    proba = rf_model.predict_proba(sample)[0]
    actual = 'PF' if y[0] == 0 else 'PJ'
    predicted = 'PF' if prediction == 0 else 'PJ'

    print(f"   Real: {actual} | Previsto: {predicted}")
    print(f"   Probabilidades: PF={proba[0]:.3f}, PJ={proba[1]:.3f}")
if __name__ == "__main__":
    main()