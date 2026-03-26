# app/etl/__init__.py
# LEGACY COMPATIBILITY LAYER
# All ETL modules have moved to app.forecast.etl
# This file re-exports everything for backward compatibility

from app.forecast.etl.ingestor import TransactionIngestor
from app.forecast.etl.classifier import TransactionClassifier

from app.forecast.etl.recurring_detector import (
    RecurringDetector,
    detect_recurring_patterns,
    print_recurring_stats,
)

from app.forecast.etl.data_quality import (
    DataQualityValidator,
    validate_data_quality,
)

from app.forecast.etl.profiles import UserProfileAnalyzer

from app.forecast.etl.income_profiler import IncomeProfile, IncomeProfiler

from app.forecast.etl.bank_strategy import get_bank_strategy

# Divider classifiers
from app.divider.classifier import PFPJClassifier
from app.divider.subcategory_classifier import get_pj_subcategory_classifier

__all__ = [
    "TransactionIngestor",
    "TransactionClassifier",
    "RecurringDetector",
    "detect_recurring_patterns",
    "print_recurring_stats",
    "DataQualityValidator",
    "validate_data_quality",
    "UserProfileAnalyzer",
    "IncomeProfile",
    "IncomeProfiler",
    "get_bank_strategy",
    "PFPJClassifier",
    "get_pj_subcategory_classifier",
]
