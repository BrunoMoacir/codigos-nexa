"""
app/etl/__init__.py - Entry Point do Módulo ETL

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Este arquivo torna `app/etl/` um módulo Python importável e define
quais classes/funções são públicas (podem ser importadas por outros módulos).

╔══════════════════════════════════════════════════════════════════════╗
║ POR QUE É IMPORTANTE                                                 ║
╚══════════════════════════════════════════════════════════════════════╝

1. Encapsulamento: Esconde detalhes de implementação
2. Descobribilidade: IDE mostra autocomplete das classes públicas
3. Organização: Centraliza imports (outros módulos importam de app.etl)

╔══════════════════════════════════════════════════════════════════════╗
║ COMO USAR (EM OUTROS ARQUIVOS)                                       ║
╚══════════════════════════════════════════════════════════════════════╝

# ✅ CORRETO (import do módulo):
from app.etl import TransactionIngestor, TransactionClassifier

ingestor = TransactionIngestor()
clean_df = ingestor.process(transactions)

# ❌ ERRADO (import direto do arquivo):
from app.etl.ingestor import TransactionIngestor  # Não faça isso!
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS DAS CLASSES PÚBLICAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Importa classes de cada arquivo do módulo
from .ingestor import TransactionIngestor
from .classifier import TransactionClassifier
from .recurring_detector import RecurringDetector
from .data_quality import DataQualityValidator

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API PÚBLICA DO MÓDULO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# __all__ define o que pode ser importado com "from app.etl import *"
# (Boa prática: sempre definir explicitamente)
__all__ = [
    "TransactionIngestor",     # JSON → DataFrame limpo
    "TransactionClassifier",   # Categoriza transações (CatBoost)
    "RecurringDetector",       # Detecta assinaturas/parcelamentos
    "DataQualityValidator",    # Calcula confidence scores
]

# Versão do módulo (facilita debugging)
__version__ = "1.0.0"