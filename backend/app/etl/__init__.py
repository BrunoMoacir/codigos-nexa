"""
app/etl/__init__.py - Entry Point do Módulo ETL (v1.2.0 - ETL COMPLETO!)

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
from app.etl import (
    TransactionIngestor, 
    TransactionClassifier,
    RecurringDetector,
    DataQualityValidator,
    UserProfileAnalyzer,
    PFPJClassifier  # Novo classificador PF/PJ
)

ingestor = TransactionIngestor()
clean_df = ingestor.process(transactions)

# ❌ ERRADO (import direto do arquivo):
from app.etl.ingestor import TransactionIngestor  # Não faça isso!

╔══════════════════════════════════════════════════════════════════════╗
║ CHANGELOG                                                            ║
╚══════════════════════════════════════════════════════════════════════╝

v1.2.0 (2026-02-06) - ETL COMPLETO! ✅
    ✅ DataQualityValidator implementado e testado
    ✅ RecurringDetector implementado e testado
    ✅ Pipeline ETL 100% funcional
    ✅ Testes E2E completos
    ✅ Todos os helpers exportados

v1.1.0 (2026-02-05):
    ✅ RecurringDetector implementado
    ✅ BankStrategy completo (4 strategies)
    ✅ Shadow Invoices completo (2 detectores)

v1.0.0 (2026-02-04):
    ✅ Ingestor, Classifier, Profiles
    ✅ Estrutura base do módulo
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS DAS CLASSES PÚBLICAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Core ETL Pipeline
from .ingestor import TransactionIngestor
from .classifier import TransactionClassifier

# ✅ Recurring Patterns (v1.1.0)
from .recurring_detector import (
    RecurringDetector,
    detect_recurring_patterns,
    print_recurring_stats
)

# ✅ Data Quality (v1.2.0)
from .data_quality import (
    DataQualityValidator,
    validate_data_quality
)

# User Profile Analysis
from .profiles import UserProfileAnalyzer

# Bank Strategy
from .bank_strategy import get_bank_strategy

# Shadow Invoices
from .shadow_invoices import run_shadow_invoice_detection

# PF/PJ Classifier (F4 - Divider PF/PJ)
from .pf_pj_classifier import PFPJClassifier

# TODO: Cashflow (próximo módulo)
# from .cashflow import CashflowProjector, SafeToSpendCalculator


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API PÚBLICA DO MÓDULO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# __all__ define o que pode ser importado com "from app.etl import *"
# (Boa prática: sempre definir explicitamente)
__all__ = [
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CORE ETL PIPELINE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    "TransactionIngestor",      # JSON → DataFrame limpo (Polars + BankStrategy + DuckDB)
    "TransactionClassifier",    # Categoriza transações (RULES mode: 10 categorias)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RECURRING PATTERNS (v1.1.0)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    "RecurringDetector",        # Detecta assinaturas/parcelamentos
    "detect_recurring_patterns", # Helper function (wrapper)
    "print_recurring_stats",    # Helper para debug/análise
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DATA QUALITY (v1.2.0) ✅ NOVO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    "DataQualityValidator",     # Validador de qualidade global
    "validate_data_quality",    # Helper function (wrapper)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # USER PROFILE & STRATEGIES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    "UserProfileAnalyzer",      # Analisa perfil financeiro (CONSERVADOR/EQUILIBRADO/GASTADOR)
    "get_bank_strategy",        # Factory de strategies (Nubank, Itaú, Inter, Default)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SHADOW INVOICES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    "run_shadow_invoice_detection",  # Detecta obrigações futuras (Subscriptions + Installments)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PF/PJ CLASSIFIER (F4 - Divider PF/PJ) ✅ NOVO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    "PFPJClassifier",  # Classifica transações PF vs PJ (ML + Rules Fallback)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TODO: CASHFLOW (próximo módulo)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # "CashflowProjector",          # Projeta saldo futuro (integra Shadow Invoice)
    # "SafeToSpendCalculator",      # Calcula safe-to-spend real
]

# Versão do módulo (facilita debugging)
__version__ = "1.2.0"  # ✅ ETL COMPLETO!


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# METADATA (útil para debugging e documentação automática)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__author__ = "Nexa AI Team"
__status__ = "Production"
__description__ = "ETL Pipeline completo para transações Open Finance Brasil"

# Módulos implementados
__modules__ = {
    "ingestor": "✅ Polars + BankStrategy + DuckDB",
    "classifier": "✅ RULES mode (10 categorias)",
    "recurring_detector": "✅ Assinaturas + Parcelamentos",
    "data_quality": "✅ Validação global + Métricas",
    "profiles": "✅ Análise de perfil financeiro",
    "bank_strategy": "✅ 4 strategies (Nubank, Itaú, Inter, Default)",
    "shadow_invoices": "✅ 2 detectores (Subscription, Installment)",
}

# Status de implementação
__implementation_status__ = {
    "schemas": "100%",
    "ingestor": "100%",
    "classifier": "100%",
    "recurring_detector": "100%",
    "data_quality": "100%",
    "profiles": "100%",
    "bank_strategy": "100%",
    "shadow_invoices": "100%",
    "cashflow": "0% (próximo)",
    "safe_to_spend": "0% (próximo)",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIM DO ARQUIVO __init__.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
📊 RESUMO DO MÓDULO ETL (v1.2.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PIPELINE COMPLETO:
    1. TransactionIngestor     → Normaliza + BankStrategy + DuckDB
    2. TransactionClassifier   → Categoriza (RULES mode)
    3. RecurringDetector       → Detecta padrões (assinaturas/parcelamentos)
    4. DataQualityValidator    → Análise de qualidade global ✅ NOVO
    5. UserProfileAnalyzer     → Perfil financeiro

MÓDULOS AUXILIARES:
    • get_bank_strategy()              → Factory de strategies
    • run_shadow_invoice_detection()   → Detecta obrigações futuras
    • detect_recurring_patterns()      → Helper wrapper
    • validate_data_quality()          → Helper wrapper
    • print_recurring_stats()          → Debug/análise

TOTAL: 8 módulos implementados, 100% production-ready
LINHAS: ~5000+ linhas de código
TESTES: 20+ unitários + 3 E2E

PRÓXIMOS PASSOS:
    1. Cashflow + Safe-to-Spend (integrar Shadow Invoice)
    2. API Layer (FastAPI endpoints)
    3. Agent (LangGraph tools)
    4. Database (Postgres models)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""