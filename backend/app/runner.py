"""
app/runner.py

Runner financeiro da Nexa — versão integrada com Pluggy real e Mock.

Este runner orquestra todo o pipeline financeiro:

    Pluggy → Validação → ETL → Shadow Invoice → Cashflow → Safe to Spend → Agent/API

Ele pode operar em dois modos:
    - DEV  → Pluggy mock (testes locais)
    - PROD → Pluggy real (produção / sandbox real)

Este arquivo é o ponto central para:
    - Testes ponta-a-ponta completos
    - Execução por Agent
    - Debug financeiro completo
"""

from datetime import date, datetime, timezone
import logging
import polars as pl

# Configure logging
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Integrações Open Finance
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.integrations.open_finance.pluggy import PluggyClient
from app.integrations.open_finance.pluggy_mock import MockPluggyClient

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Schemas (para validação de batch)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.schemas.transaction import TransactionBatchResult

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ETLs (Pipeline completo)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.etl import (
    TransactionIngestor,
    TransactionClassifier,
    RecurringDetector,
    run_shadow_invoice_detection,
    PFPJClassifier,  # Novo classificador PF/PJ
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cashflow (Projeção + Safe-to-Spend)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.cashflow.projector import CashflowProjector
from app.cashflow.safe_to_spend import SafeToSpendCalculator
from app.cashflow.burn_rate import BurnRateAnalyzer
from app.etl.income_profiler import IncomeProfiler


class NexaRunner:
    """
    Orquestrador financeiro completo da Nexa.

    Pipeline completo:
        1. Pluggy (real ou mock) → Transações brutas
        2. Validação (Pydantic) → TransactionBatchResult
        3. ETL Ingestor → Normalização + BankStrategy + DuckDB
        4. ETL Classifier → Categorização automática
        5. PF/PJ Classifier → Classificação PF vs PJ (ML + Rules)
        6. Recurring Detector → Detecção de padrões
        7. Shadow Invoice ETL → Projeção de obrigações futuras
        8. Cashflow Projector → Simulação diária de saldo
        9. Safe-to-Spend → Quanto pode gastar com segurança

    Ele NÃO implementa regras financeiras.
    Ele apenas executa as etapas na ordem correta.
    """

    def __init__(self, mode: str = "dev"):
        """
        Inicializa o runner.

        Args:
            mode (str): 'dev' (mock local) ou 'prod' (Pluggy real)
        """
        # Escolher client (mock ou real)
        if mode == "prod":
            self.pluggy = PluggyClient()
            logger.info("🔌 Usando Pluggy REAL (produção)")
        else:
            self.pluggy = MockPluggyClient()
            logger.info("🎭 Usando Pluggy MOCK (desenvolvimento)")

        # Inicializar componentes do pipeline
        self.ingestor = TransactionIngestor()
        self.classifier = TransactionClassifier(mode="RULES")
        self.pf_pj_classifier = PFPJClassifier()  # Novo classificador PF/PJ
        self.recurring_detector = RecurringDetector()
        self.cashflow_projector = CashflowProjector()
        self.safe_calc = SafeToSpendCalculator()
        self.burn_rate_analyzer = BurnRateAnalyzer()

        logger.info("✅ NexaRunner inicializado com sucesso")

    def run(self, horizon_days: int = 30) -> dict:
        """
        Executa o pipeline financeiro completo.

        Args:
            horizon_days: Dias para projetar no futuro

        Returns:
            dict com resultados de cada etapa do pipeline
        """

        try:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 1️⃣ PLUGGY: Criar sandbox item e buscar transações
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            logger.info("📡 [1/8] Buscando transações da Pluggy...")
            item = self.pluggy.create_sandbox_item()
            item_id = item["id"]
            logger.info(f"   ✅ Sandbox item criado: {item_id}")

            accounts_resp = self.pluggy.get_accounts(item_id)
            account_id = accounts_resp["results"][0]["id"]
            logger.info(f"   ✅ Conta obtida: {account_id}")

            raw_transactions = self.pluggy.get_transactions(account_id)
            logger.info(f"   ✅ {len(raw_transactions['results'])} transações brutas obtidas")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 2️⃣ VALIDAÇÃO: Converter para TransactionWebhook (tolerante)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            logger.info("🔍 [2/8] Validando batch de transações (Pydantic)...")
            connector_id = str(item.get("connector", {}).get("id", "unknown"))
            institution_id_map = {
                "201": "nubank", "202": "itau", "203": "bradesco", "204": "inter"
            }
            institution_id = institution_id_map.get(connector_id, "unknown")

            batch_result = TransactionBatchResult.from_raw_batch(
                raw_data=raw_transactions["results"],
                institution_id=institution_id,
                item_id=item_id,
                fetched_at=datetime.now(timezone.utc)
            )
            logger.info(
                f"   ✅ Batch validado: {batch_result.total_valid} válidas, "
                f"{batch_result.total_rejected} rejeitadas (taxa: {batch_result.rejection_rate:.1%})"
            )

            if not batch_result.valid_transactions:
                logger.error("❌ Nenhuma transação válida no batch!")
                raise ValueError("Batch rejected: all transactions invalid")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 3️⃣ ETL INGESTOR: Normaliza + BankStrategy + DuckDB
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            logger.info("🧹 [3/8] Executando ETL Ingestor (normalização + dedup)...")
            transactions_clean, metrics = self.ingestor.process(
                batch_result.valid_transactions
            )
            logger.info(
                f"   ✅ Ingestor completo: "
                f"records={len(transactions_clean)}, "
                f"dedup_removed={metrics.duplicates_removed}, "
                f"quality_score={metrics.quality_score:.1%}"
            )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 4️⃣ CLASSIFIER: Categoriza automaticamente
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            logger.info("🏷️  [4/9] Executando Classifier (categorização)...")
            transactions_categorized = self.classifier.predict(transactions_clean)
            logger.info(f"   ✅ Classifier completo")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 4.5️⃣ PF/PJ CLASSIFIER: Classifica PF vs PJ
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            logger.info("👥 [5/9] Executando PF/PJ Classifier...")
            transactions_pf_pj = self.pf_pj_classifier.classify_batch(transactions_categorized)
            logger.info(f"   ✅ PF/PJ Classifier completo")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 5.5️⃣ INCOME PROFILER: Estima renda real líquida (MI.5)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            logger.info("💵 [5.5/9] Executando IncomeProfiler...")
            income_profile = IncomeProfiler().build(transactions_pf_pj)
            monthly_income_net = (
                income_profile.monthly_net_income
                if income_profile.confidence >= 0.5
                else None
            )
            logger.info(
                f"   ✅ IncomeProfiler: renda=R$ {income_profile.monthly_net_income:,.0f}/mês, "
                f"padrão={income_profile.income_pattern.value}, "
                f"confiança={income_profile.confidence:.0%}"
            )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 5️⃣ RECURRING DETECTOR: Detecta padrões (assinaturas/parcelamentos)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            logger.info("📊 [6/9] Executando Recurring Detector...")
            recurring_patterns = self.recurring_detector.detect(
                transactions_pf_pj  # Agora usa transações com PF/PJ
            )
            logger.info(
                f"   ✅ Recurring Detector: "
                f"{len(recurring_patterns)} padrões detectados"
            )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 6️⃣ SHADOW INVOICE: Gera obrigações futuras
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            logger.info("👻 [7/9] Executando Shadow Invoice ETL...")
            shadow_events = run_shadow_invoice_detection(transactions_pf_pj)
            logger.info(
                f"   ✅ Shadow Invoice: "
                f"{len(shadow_events)} eventos futuros gerados"
            )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 7️⃣ CASHFLOW: Projeta saldo diário
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            logger.info("💰 [8/9] Executando Cashflow Projector...")
            start_balance = accounts_resp["results"][0]["balance"]

            # Ensure shadow_events is a DataFrame
            if isinstance(shadow_events, pl.DataFrame):
                shadow_events_df = shadow_events
            else:
                shadow_events_df = pl.DataFrame(shadow_events)
            
            cashflow_forecast = self.cashflow_projector.project(
                transactions_df=transactions_pf_pj,  # Agora usa transações com PF/PJ
                shadow_invoices_df=shadow_events_df,
                current_balance=start_balance
            )
            logger.info(
                f"   ✅ Cashflow projetado: "
                f"{len(cashflow_forecast)} dias, saldo min: "
                f"R$ {cashflow_forecast.select('projected_balance').min().item():.2f}"
            )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 8️⃣ SAFE-TO-SPEND: Calcula quanto pode gastar
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            logger.info("🛡️  [9/9] Calculando Safe-to-Spend...")
            safe_to_spend = self.safe_calc.calculate(
                projection_df=cashflow_forecast,
                horizon_days=horizon_days
            )
            logger.info(
                f"   ✅ Safe-to-Spend: "
                f"R$ {safe_to_spend.safe_to_spend_total:.2f} "
                f"(risk_level: {safe_to_spend.risk_level})"
            )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 9.5️⃣ BURN RATE: Velocidade de gasto + escalada por renda (MI.5)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            logger.info("🔥 [9.5/9] Calculando Burn Rate...")
            burn_rate_result = self.burn_rate_analyzer.analyze(
                transactions_df=transactions_pf_pj,
                monthly_income=monthly_income_net,  # MI.5: escalada por renda
            )
            logger.info(
                f"   ✅ Burn Rate: alert={burn_rate_result.alert_level}, "
                f"ratio={burn_rate_result.burn_rate_ratio:.1%}"
                + (
                    f", income_ratio={burn_rate_result.income_ratio:.1%}"
                    if burn_rate_result.income_ratio is not None
                    else ""
                )
            )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # RESULTADO FINAL
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            logger.info("✨ Pipeline financeiro concluído com sucesso!")

            return {
                "status": "success",
                "metadata": {
                    "institution": institution_id,
                    "item_id": item_id,
                    "account_id": account_id,
                    "horizon_days": horizon_days,
                },
                "transactions": {
                    "raw_count": len(raw_transactions["results"]),
                    "valid_count": batch_result.total_valid,
                    "rejected_count": batch_result.total_rejected,
                    "clean_df": transactions_clean,
                    "categorized_df": transactions_categorized,
                    "pf_pj_classified_df": transactions_pf_pj,  # Novo: transações com PF/PJ
                },
                "analysis": {
                    "recurring_patterns": recurring_patterns,
                    "quality_metrics": metrics,
                    "income_profile": income_profile,         # MI.5: renda líquida estimada
                    "burn_rate": burn_rate_result,            # MI.5: velocidade de gasto
                },
                "projections": {
                    "shadow_events": shadow_events,
                    "cashflow_forecast": cashflow_forecast,
                    "safe_to_spend": safe_to_spend,
                    "current_balance": start_balance,
                    "min_projected_balance": cashflow_forecast.select("projected_balance").min().item(),
                    "max_projected_balance": cashflow_forecast.select("projected_balance").max().item(),
                },
            }

        except Exception as e:
            logger.error(f"❌ Erro no pipeline: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }
