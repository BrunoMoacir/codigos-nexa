"""
app/etl/pf_pj_classifier.py - Classificador PF/PJ para o pipeline ETL

Integra modelo ML (Random Forest) com regras de fallback para classificar
transações como Pessoais (PF) ou Empresariais (PJ).

Uso no pipeline:
- Carrega modelo treinado + encoders/scalers
- Extrai features das transações
- Prediz com ML, usa fallback se confiança baixa
- Adiciona coluna 'pf_pj_label' ao DataFrame
"""

import polars as pl
import numpy as np
import joblib
import logging
import os
from datetime import datetime
import re
from typing import Dict, Any, Optional
import math

from app.divider.subcategory_classifier import get_pj_subcategory_classifier

logger = logging.getLogger(__name__)

class PFPJClassifier:
    """
    Classificador híbrido PF/PJ: ML + Rules Fallback

    Estratégia:
    1. Tenta predição ML se modelo disponível
    2. Usa regras determinísticas como fallback
    3. Retorna 'PF', 'PJ' ou 'UNCERTAIN'
    """

    def __init__(self, model_path: str = None,
                 encoders_path: str = None,
                 scaler_path: str = None):
        """
        Inicializa classificador.

        Args:
            model_path: Caminho para modelo Random Forest
            encoders_path: Caminho para encoders categóricos
            scaler_path: Caminho para scaler numérico
        """
        # Define caminhos padrão relativos ao backend
        if model_path is None:
            model_path = os.path.join(os.path.dirname(__file__), '..', '..', 'models', 'pf_pj_classifier.pkl')
        if encoders_path is None:
            encoders_path = os.path.join(os.path.dirname(__file__), '..', '..', 'models', 'feature_encoders.pkl')
        if scaler_path is None:
            scaler_path = os.path.join(os.path.dirname(__file__), '..', '..', 'models', 'feature_scaler.pkl')

        self.model = None
        self.encoders = {}
        self.scaler = None
        self.fallback_classifier = PFPJFallbackClassifier()

        # Tenta carregar modelo ML
        try:
            self.model = joblib.load(model_path)
            self.encoders = joblib.load(encoders_path)
            self.scaler = joblib.load(scaler_path)
            logger.info("✅ Modelo ML PF/PJ carregado com sucesso")
        except FileNotFoundError:
            logger.warning("⚠️  Modelo ML não encontrado - usando apenas regras de fallback")
        except Exception as e:
            logger.error(f"❌ Erro carregando modelo ML: {e} - usando fallback")

    def classify_batch(self, transactions_df: pl.DataFrame) -> pl.DataFrame:
        """
        Classifica batch de transações PF/PJ e adiciona subcategoria para PJ.

        Args:
            transactions_df: DataFrame com transações (depois do ETL Ingestor)

        Returns:
            DataFrame com colunas 'pf_pj_label' e 'pj_subcategory' adicionadas.
            'pj_subcategory' é None para transações PF/UNCERTAIN.
        """
        logger.info(f"Classificando {len(transactions_df)} transacoes PF/PJ...")

        rows = list(transactions_df.iter_rows(named=True))
        classifications = [self._classify_single(row) for row in rows]

        # Subcategoria PJ: só classifica quem foi rotulado PJ
        pj_classifier = get_pj_subcategory_classifier()
        subcategories = [
            pj_classifier.classify(row) if label == "PJ" else None
            for row, label in zip(rows, classifications)
        ]

        result_df = transactions_df.with_columns([
            pl.Series("pf_pj_label", classifications),
            pl.Series("pj_subcategory", subcategories),
        ])

        pf_count = classifications.count("PF")
        pj_count = classifications.count("PJ")
        uncertain_count = classifications.count("UNCERTAIN")

        logger.info(f"Classificacao completa: PF={pf_count}, PJ={pj_count}, UNCERTAIN={uncertain_count}")

        return result_df

    def _classify_single(self, transaction: Dict[str, Any]) -> str:
        """
        Classifica uma única transação.

        Estratégia:
        1. Tenta ML se disponível e confiança > threshold
        2. Usa regras de fallback
        """
        # Tenta ML primeiro
        if self.model is not None:
            ml_result = self._predict_ml(transaction)
            if ml_result and ml_result['confidence'] > 0.8:  # Threshold de confiança
                return ml_result['prediction']

        # Fallback para regras
        rules_result = self.fallback_classifier.classify(transaction)
        if rules_result != 'UNCERTAIN':
            return rules_result

        # Se tudo falhou, retorna UNCERTAIN
        return 'UNCERTAIN'

    def _predict_ml(self, transaction: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Prediz usando modelo ML.

        Returns:
            Dict com 'prediction' e 'confidence', ou None se erro
        """
        try:
            # Extrai features
            features = self._extract_features(transaction)

            # Colunas na mesma ordem do treinamento
            _feature_cols = [
                'hour_of_day', 'day_of_week', 'is_weekend', 'is_business_hour',
                'amount', 'amount_abs', 'amount_log', 'transaction_type', 'amount_category',
                'pf_keyword_score', 'pj_keyword_score', 'has_business_terms',
                'category', 'merchant_category', 'is_recurring',
            ]
            _categorical_cols = ['transaction_type', 'amount_category', 'category', 'merchant_category']
            _numerical_cols = ['hour_of_day', 'day_of_week', 'amount', 'amount_abs', 'amount_log',
                               'pf_keyword_score', 'pj_keyword_score']

            # Encode categóricas diretamente no dict
            encoded = dict(features)
            for col in _categorical_cols:
                if col in self.encoders:
                    encoder = self.encoders[col]
                    val = str(encoded.get(col, ''))
                    if val not in encoder.classes_:
                        val = encoder.classes_[0]
                    encoded[col] = int(encoder.transform([val])[0])

            # Constrói array numpy na ordem correta de colunas
            X = np.array([[encoded.get(col, 0) for col in _feature_cols]], dtype=float)

            # Scale numéricas
            _num_indices = [_feature_cols.index(col) for col in _numerical_cols]
            X[:, _num_indices] = self.scaler.transform(X[:, _num_indices])

            # Prediz
            prediction_proba = self.model.predict_proba(X)[0]
            prediction_idx = self.model.predict(X)[0]

            # Converte para labels
            prediction = 'PF' if prediction_idx == 0 else 'PJ'
            confidence = max(prediction_proba)

            return {
                'prediction': prediction,
                'confidence': confidence,
                'probabilities': prediction_proba
            }

        except Exception as e:
            logger.warning(f"Erro na predição ML: {e}")
            return None

    def _extract_features(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrai features da transação para ML.
        Mesmo código usado no treinamento.
        """
        # Dados básicos com tratamento de None
        description = transaction.get('description', '') or ''
        category = transaction.get('category', '') or ''
        amount = transaction.get('amount', 0) or 0
        merchant = transaction.get('merchant', '') or ''

        # Features temporais com tratamento de None
        transaction_date = transaction.get('transaction_date')
        if isinstance(transaction_date, str):
            try:
                transaction_date = datetime.fromisoformat(transaction_date.replace('Z', '+00:00'))
            except:
                transaction_date = None
        elif not isinstance(transaction_date, datetime):
            transaction_date = None

        hour_of_day = transaction_date.hour if transaction_date else 12
        day_of_week = transaction_date.weekday() + 1 if transaction_date else 1  # 1=Seg

        # Features monetárias com tratamento de None
        try:
            amount = float(amount) if amount is not None else 0.0
        except (ValueError, TypeError):
            amount = 0.0

        amount_abs = abs(amount)
        amount_log = math.log(amount_abs + 1) if amount_abs > 0 else 0
        transaction_type = 'credit' if amount > 0 else 'debit'

        # Categorização de valor
        if amount_abs < 50:
            amount_category = 'very_low'
        elif amount_abs < 100:
            amount_category = 'low'
        elif amount_abs < 500:
            amount_category = 'medium'
        elif amount_abs < 1000:
            amount_category = 'high'
        else:
            amount_category = 'very_high'

        # Features textuais
        pf_keywords = ['uber', 'netflix', 'carrefour', 'academia', 'restaurante', 'drogaria',
                      'shopping', 'cinepolis', 'padaria', 'spotify', 'lavanderia', 'starbucks',
                      'pet shop', 'livraria', 'pix recebido', 'amigo']

        pj_keywords = ['salario', 'empresa', 'ltda', 'fornecedor', 'aluguel', 'escritorio',
                      'imobiliaria', 'viagem negocios', 'software', 'corporativo', 'marketing',
                      'cemig empresas', 'consultoria', 'contador']

        description_lower = description.lower() if description else ''
        pf_keyword_score = sum(1 for kw in pf_keywords if kw in description_lower)
        pj_keyword_score = sum(1 for kw in pj_keywords if kw in description_lower)

        # Merchant category
        merchant_lower = merchant.lower() if merchant else ''
        if any(m in merchant_lower for m in ['uber', 'starbucks', 'netflix', 'cinepolis', 'spotify']):
            merchant_category = 'entertainment'
        elif any(m in merchant_lower for m in ['carrefour', 'padaria', 'restaurante']):
            merchant_category = 'food_grocery'
        elif any(m in merchant_lower for m in ['academia', 'drogaria', 'pet shop']):
            merchant_category = 'health_pets'
        elif any(m in merchant_lower for m in ['shopping', 'livraria']):
            merchant_category = 'shopping_education'
        elif 'lavanderia' in merchant_lower:
            merchant_category = 'services'
        elif any(m in merchant_lower for m in ['microsoft', 'fornecedor', 'imobiliaria', 'cemig', 'contador']):
            merchant_category = 'business'
        else:
            merchant_category = 'other'

        # Features temporais adicionais
        is_weekend = 1 if day_of_week >= 6 else 0
        is_business_hour = 1 if 9 <= hour_of_day <= 17 else 0

        # Recorrência (simplificada)
        is_recurring = 1 if (category in ['ENTERTAINMENT', 'FOOD', 'HEALTH', 'SERVICES'] and amount_abs < 200) else 0

        # Business terms flag
        has_business_terms = 1 if re.search(r'\b(empresa|ltda|fornecedor|escritorio|corporativo)\b', description_lower, re.IGNORECASE) else 0

        return {
            'hour_of_day': hour_of_day,
            'day_of_week': day_of_week,
            'is_weekend': is_weekend,
            'is_business_hour': is_business_hour,
            'amount': amount,
            'amount_abs': amount_abs,
            'amount_log': amount_log,
            'transaction_type': transaction_type,
            'amount_category': amount_category,
            'pf_keyword_score': pf_keyword_score,
            'pj_keyword_score': pj_keyword_score,
            'has_business_terms': has_business_terms,
            'category': category,
            'merchant_category': merchant_category,
            'is_recurring': is_recurring
        }


class PFPJFallbackClassifier:
    """
    Classificador rule-based (mesmo código de pf_pj_fallback_rules.py)
    """

    def __init__(self):
        self.pj_keywords = [
            'empresa', 'ltda', 'fornecedor', 'aluguel', 'escritorio', 'imobiliaria',
            'viagem negocios', 'software', 'corporativo', 'marketing', 'cemig empresas',
            'consultoria', 'contador', 'salario', 'papelaria'
        ]
        self.pf_keywords = [
            'uber', 'netflix', 'carrefour', 'academia', 'restaurante', 'drogaria',
            'shopping', 'cinepolis', 'padaria', 'spotify', 'lavanderia', 'starbucks',
            'pet shop', 'livraria', 'pix recebido', 'amigo'
        ]
        self.pj_categories = [
            'SALARY', 'OFFICE_SUPPLIES', 'RENT', 'SOFTWARE', 'CONSULTING',
            'MARKETING', 'UTILITIES', 'TELEPHONE'
        ]

    def classify(self, transaction: Dict[str, Any]) -> str:
        """Classifica usando regras determinísticas"""
        description = transaction.get('description', '') or ''
        category = transaction.get('category', '') or ''
        amount = transaction.get('amount', 0) or 0
        transaction_date = transaction.get('transaction_date')
        hour_of_day = 12  # default
        if isinstance(transaction_date, datetime):
            hour_of_day = transaction_date.hour
        elif isinstance(transaction_date, str):
            try:
                parsed_date = datetime.fromisoformat(transaction_date.replace('Z', '+00:00'))
                hour_of_day = parsed_date.hour
            except:
                pass
        merchant = transaction.get('merchant', '') or ''

        # Converte para tipos apropriados
        description = description.lower()
        merchant = merchant.lower()
        amount = abs(amount)

        # Regras de alta prioridade
        if category in self.pj_categories:
            return 'PJ'

        if any(kw in description for kw in self.pj_keywords):
            return 'PJ'

        if amount > 2000:
            return 'PJ'

        if any(kw in description for kw in self.pf_keywords):
            return 'PF'

        if amount < 20 and (hour_of_day < 8 or hour_of_day > 18):
            return 'PF'

        # Merchants conhecidos
        if any(m in merchant for m in ['microsoft', 'fornecedor', 'imobiliaria', 'cemig', 'contador']):
            return 'PJ'
        if any(m in merchant for m in ['uber', 'netflix', 'starbucks', 'cinepolis', 'spotify']):
            return 'PF'

        return 'UNCERTAIN'