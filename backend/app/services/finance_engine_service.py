#app/services/finance_engine_service
from app.core_engine.safe_to_spend.engine import SafeToSpendEngine
from app.core_engine.profile.analyzer import UserProfileAnalyzer
from app.core_engine.shadow_invoices.detector import ShadowInvoiceDetector
from app.core_engine.data_quality.validator import DataQualityValidator


class FinanceEngineService:
    """
    Orquestra todo o Core Engine financeiro.
    Essa classe vira o ponto único de acesso à inteligência financeira.
    """

    def __init__(self):
        self.safe_engine = SafeToSpendEngine()
        self.profile_engine = UserProfileAnalyzer()
        self.shadow_engine = ShadowInvoiceDetector()
        self.quality_engine = DataQualityValidator()

    def build_dashboard(self, df):
        """
        Recebe o DataFrame final do ETL e retorna
        todo o painel financeiro consolidado.
        """
        quality = self.quality_engine.validate(df)
        profile = self.profile_engine.analyze(df)
        safe = self.safe_engine.calculate(df)
        shadow = self.shadow_engine.detect(df)

        return {
            "profile": profile.model_dump(),
            "health_score": profile.health_score,
            "safe_to_spend": safe.model_dump(),
            "shadow_invoices": shadow.model_dump(),
            "data_quality": quality.model_dump()
        }
