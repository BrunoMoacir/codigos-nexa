"""
app/etl/classifier.py - Classifica transações em categorias (CatBoost ML)

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Classifica transações em categorias financeiras usando Machine Learning:
- Transporte (Uber, Taxi, Gasolina)
- Alimentação (Restaurantes, Mercado, iFood)
- Assinaturas (Netflix, Spotify, Gym)
- Saúde (Farmácia, Médico, Plano de saúde)
- Etc...

╔══════════════════════════════════════════════════════════════════════╗
║ POR QUE CATBOOST?                                                    ║
╚══════════════════════════════════════════════════════════════════════╝

CatBoost é ideal para classificação de transações porque:
1. Trabalha bem com features categóricas (merchant, description)
2. Não precisa de muito tuning (já vem otimizado)
3. Rápido para inferência (milhares de transações/segundo)
4. Interpretável (mostra quais features foram importantes)

╔══════════════════════════════════════════════════════════════════════╗
║ PRIORIDADES DE CLASSIFICAÇÃO (3 NÍVEIS)                             ║
╚══════════════════════════════════════════════════════════════════════╝

1. PRIORIDADE 1: Categoria do banco (se confiável)
   └─> Se banco tem TIER_1 (Nubank) e enviou categoria → USAR
   
2. PRIORIDADE 2: CatBoost ML (se confidence > 0.6)
   └─> Modelo treinado em milhares de transações → USAR
   
3. PRIORIDADE 3: Heurísticas (fallback sempre funciona)
   └─> Regras simples baseadas em keywords → USAR

╔══════════════════════════════════════════════════════════════════════╗
║ ESTADO ATUAL (MVP)                                                   ║
╚══════════════════════════════════════════════════════════════════════╝

🚧 STUB IMPLEMENTATION (implementação temporária)

Por enquanto, este arquivo retorna:
- predicted_category: "Outros" (categoria padrão)
- ml_confidence: 0.5 (confiança neutra)
- category_source: "heuristic" (fallback)

⏰ TODO (FUTURO):
1. Treinar modelo CatBoost com dados reais
2. Salvar modelo em app/ml/models/category_classifier.cbm
3. Implementar predict() real
4. Implementar heurísticas por keyword

╔══════════════════════════════════════════════════════════════════════╗
║ EXEMPLO DE USO                                                       ║
╚══════════════════════════════════════════════════════════════════════╝

from app.etl import TransactionClassifier, TransactionIngestor

# 1. Limpa transações
ingestor = TransactionIngestor()
clean_df, _ = ingestor.process(transactions)

# 2. Classifica
classifier = TransactionClassifier()
categorized_df = classifier.predict(clean_df)

# 3. Resultado:
# ┌──────────────┬───────────────┬──────────────┬─────────────────┐
# │ description  │ final_category│ ml_confidence│ category_source │
# ├──────────────┼───────────────┼──────────────┼─────────────────┤
# │ uber viagem  │ Transporte    │ 0.92         │ ml              │
# │ netflix      │ Assinaturas   │ 0.88         │ ml              │
# │ mercado      │ Alimentação   │ 0.75         │ ml              │
# └──────────────┴───────────────┴──────────────┴─────────────────┘
"""

import logging
from pathlib import Path

import polars as pl

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO DE LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Path para o modelo treinado (futuro)
MODEL_PATH = Path("app/ml/models/category_classifier.cbm")

# Categorias possíveis
CATEGORIES = [
    "Alimentação",
    "Transporte",
    "Assinaturas",
    "Saúde",
    "Educação",
    "Lazer",
    "Moradia",
    "Vestuário",
    "Outros"
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLASSE PRINCIPAL: TRANSACTION CLASSIFIER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TransactionClassifier:
    """
    Classifica transações em categorias usando CatBoost ML.
    
    Prioridades de classificação:
        1. Categoria do banco (TIER_1 apenas)
        2. CatBoost ML (confidence > 0.6)
        3. Heurísticas (fallback)
    
    Estado atual (MVP):
        🚧 STUB - Retorna categoria padrão "Outros"
        
    TODO (Futuro):
        - Treinar modelo CatBoost
        - Implementar predict() real
        - Implementar heurísticas
    """
    
    def __init__(self):
        """
        Inicializa o classificador.
        
        Por enquanto não carrega modelo (stub).
        No futuro, vai carregar CatBoost de MODEL_PATH.
        """
        self.model = None  # TODO: Carregar CatBoost aqui
        
        logger.warning(
            "TransactionClassifier inicializado no modo STUB. "
            "Retornará categoria padrão 'Outros'. "
            "Para habilitar ML, treinar modelo CatBoost."
        )
    
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MÉTODO PRINCIPAL: PREDICT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def predict(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Classifica transações em categorias.
        
        Adiciona 3 colunas ao DataFrame:
            - predicted_category: Categoria final (str)
            - ml_confidence: Confiança do modelo (float 0.0-1.0)
            - category_source: Origem da categoria ("bank" | "ml" | "heuristic")
        
        Args:
            df: DataFrame limpo (após ingestor.process())
        
        Returns:
            DataFrame com colunas de classificação adicionadas
        
        Notes:
            - 🚧 STUB: Por enquanto retorna "Outros" para tudo
            - Confidence sempre 0.5 (neutro)
            - Source sempre "heuristic" (fallback)
        
        TODO (Futuro):
            1. Se df["category"] exists E institution_id é TIER_1:
               → use bank category (source="bank")
            
            2. Senão, use CatBoost:
               features = df.select(["merchant", "description", "amount"])
               predictions = self.model.predict(features)
               confidences = self.model.predict_proba(features).max(axis=1)
               
               → se confidence > 0.6: use ML (source="ml")
               → senão: use heurística (source="heuristic")
            
            3. Heurísticas (keywords):
               - "uber|taxi|99" → Transporte
               - "netflix|spotify" → Assinaturas
               - "ifood|restaurante" → Alimentação
        
        Example (futuro):
            >>> classifier = TransactionClassifier()
            >>> df_categorized = classifier.predict(clean_df)
            >>> df_categorized.select(["description", "predicted_category"])
            
            ┌──────────────┬───────────────┐
            │ description  │ predicted_cat │
            ├──────────────┼───────────────┤
            │ uber viagem  │ Transporte    │
            │ netflix      │ Assinaturas   │
            │ ifood pedido │ Alimentação   │
            └──────────────┴───────────────┘
        """
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # IMPLEMENTAÇÃO STUB (TEMPORÁRIA)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Por enquanto, retorna categoria padrão para todas as transações
        df_categorized = df.with_columns([
            # Categoria padrão: "Outros"
            pl.lit("Outros").alias("predicted_category"),
            
            # Confiança neutra: 0.5 (50%)
            pl.lit(0.5).alias("ml_confidence"),
            
            # Source: heuristic (fallback)
            pl.lit("heuristic").alias("category_source")
        ])
        
        logger.info(
            "Transações classificadas (modo STUB)",
            extra={
                "total_classified": len(df_categorized),
                "default_category": "Outros"
            }
        )
        
        return df_categorized
    
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MÉTODOS PRIVADOS (FUTURO)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _load_model(self) -> None:
        """
        TODO: Carrega modelo CatBoost do disco.
        
        Implementation:
            from catboost import CatBoostClassifier
            
            if MODEL_PATH.exists():
                self.model = CatBoostClassifier()
                self.model.load_model(str(MODEL_PATH))
                logger.info("Modelo CatBoost carregado")
            else:
                logger.warning("Modelo não encontrado, usando heurísticas")
        """
        pass
    
    
    def _predict_with_ml(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        TODO: Predição real com CatBoost.
        
        Args:
            df: DataFrame com features (merchant, description, amount)
        
        Returns:
            DataFrame com predicted_category e ml_confidence
        
        Implementation:
            # Extrair features
            features = df.select(["merchant", "description", "amount"])
            
            # Predição
            predictions = self.model.predict(features)
            probabilities = self.model.predict_proba(features)
            
            # Pegar confiança máxima (melhor classe)
            confidences = probabilities.max(axis=1)
            
            # Adicionar ao DataFrame
            df = df.with_columns([
                pl.Series("predicted_category", predictions),
                pl.Series("ml_confidence", confidences)
            ])
            
            return df
        """
        pass
    
    
    def _predict_with_heuristics(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        TODO: Classificação por keywords (fallback).
        
        Heurísticas:
            - "uber|taxi|99|gasolina" → Transporte
            - "netflix|spotify|prime|disney" → Assinaturas
            - "ifood|rappi|restaurante|mercado" → Alimentação
            - "farmacia|droga|clinica|hospital" → Saúde
            - "academia|personal|crossfit" → Saúde
        
        Implementation:
            # Cria coluna de categoria baseada em regex
            df = df.with_columns(
                pl.when(
                    pl.col("description").str.contains("uber|taxi|99")
                ).then(pl.lit("Transporte"))
                .when(
                    pl.col("description").str.contains("netflix|spotify")
                ).then(pl.lit("Assinaturas"))
                .otherwise(pl.lit("Outros"))
                .alias("predicted_category")
            )
            
            # Confidence sempre 0.7 (heurística é confiável)
            df = df.with_columns(pl.lit(0.7).alias("ml_confidence"))
            
            return df
        """
        pass