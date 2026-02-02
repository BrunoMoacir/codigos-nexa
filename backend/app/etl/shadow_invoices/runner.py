# app/etl/shadow_invoices/runner.py

import polars as pl
from app.etl.shadow_invoices.installment_detector import InstallmentDetector
from app.etl.shadow_invoices.subscription_detector import SubscriptionDetector


def run_shadow_invoice_detection(df: pl.DataFrame) -> pl.DataFrame:
    results = []

    # 1️⃣ Detecta assinaturas primeiro
    subscription_detector = SubscriptionDetector()
    subscriptions = subscription_detector.detect(df)

    if not subscriptions.is_empty():
        results.append(subscriptions)

        # remove transações que viraram assinatura
        subscription_descriptions = subscriptions.select(
            pl.col("metadata").struct.field("description")
        ).to_series()

        df = df.filter(
            ~pl.col("description").is_in(subscription_descriptions)
        )

    # 2️⃣ Detecta parcelamentos no que sobrou
    installment_detector = InstallmentDetector()
    installments = installment_detector.detect(df)

    if not installments.is_empty():
        results.append(installments)

    if not results:
        return pl.DataFrame()

    return pl.concat(results)
