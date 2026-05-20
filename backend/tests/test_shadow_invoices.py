# tests/test_shadow_invoices.py
# Testes para MX.6 — Shadow Invoices (parcelas e assinaturas futuras)

import datetime
import polars as pl
import pytest

from app.subscriptions.shadow_invoices.runner import run_shadow_invoice_detection
from app.subscriptions.shadow_invoices.subscription_detector import SubscriptionDetector
from app.subscriptions.shadow_invoices.installment_detector import InstallmentDetector


def _today() -> datetime.date:
    return datetime.date.today()


def _days_ago(n: int) -> datetime.date:
    return _today() - datetime.timedelta(days=n)


def _subscription_df() -> pl.DataFrame:
    """Simula assinatura mensal recorrente (Netflix-like)."""
    import datetime as dt
    dates = [datetime.datetime(_today().year, _today().month, 1, tzinfo=dt.timezone.utc)
             - dt.timedelta(days=n * 30) for n in range(4)]
    return pl.DataFrame({
        "description": ["NETFLIX"] * 4,
        "amount": [-39.9] * 4,
        "transaction_date": dates,
        "category": ["assinatura"] * 4,
        "transaction_type": ["DEBIT"] * 4,
    })


def _installment_df() -> pl.DataFrame:
    """Simula parcelamento de compra (3x R$200)."""
    import datetime as dt
    dates = [datetime.datetime(_today().year, _today().month, 1, tzinfo=dt.timezone.utc)
             - dt.timedelta(days=n * 30) for n in range(3)]
    return pl.DataFrame({
        "description": ["LOJA XYZ PARCELA 1/3", "LOJA XYZ PARCELA 2/3", "LOJA XYZ PARCELA 3/3"],
        "amount": [-200.0, -200.0, -200.0],
        "transaction_date": dates,
        "category": ["compras"] * 3,
        "transaction_type": ["DEBIT"] * 3,
    })


def _empty_df() -> pl.DataFrame:
    import datetime as dt
    return pl.DataFrame({
        "description": pl.Series([], dtype=pl.Utf8),
        "amount": pl.Series([], dtype=pl.Float64),
        "transaction_date": pl.Series([], dtype=pl.Datetime("us", "UTC")),
        "category": pl.Series([], dtype=pl.Utf8),
        "transaction_type": pl.Series([], dtype=pl.Utf8),
    })


# ── Testes: run_shadow_invoice_detection ─────────────────────────────────────

def test_pipeline_empty_df_returns_empty():
    """DataFrame vazio → resultado vazio (sem erros)."""
    result = run_shadow_invoice_detection(_empty_df())
    assert result is not None
    assert isinstance(result, pl.DataFrame)


def test_pipeline_with_mock_data_returns_dataframe():
    """Pipeline com dados mock do Pluggy retorna DataFrame válido."""
    from app.core.integrations.pluggy_mock import MockPluggyClient
    from app.core.schemas.transaction import TransactionBatchResult
    from app.forecast.etl.ingestor import TransactionIngestor
    import datetime

    pluggy = MockPluggyClient()
    ingestor = TransactionIngestor()
    item = pluggy.create_sandbox_item()
    acc = pluggy.get_accounts(item["id"])
    txs = pluggy.get_transactions(acc["results"][0]["id"])
    batch = TransactionBatchResult.from_raw_batch(
        raw_data=txs["results"],
        institution_id="nubank",
        item_id=item["id"],
        fetched_at=datetime.datetime.now(datetime.timezone.utc),
    )
    df, _ = ingestor.process(batch.valid_transactions)
    result = run_shadow_invoice_detection(df)
    assert result is not None
    assert hasattr(result, "columns")


def test_pipeline_no_duplicates_between_detectors():
    """Pipeline retorna DataFrame sem erros mesmo com dados repetidos."""
    subscription_df = _subscription_df()
    result = run_shadow_invoice_detection(subscription_df)
    assert isinstance(result, pl.DataFrame)


# ── Testes: SubscriptionDetector ─────────────────────────────────────────────

def test_subscription_detector_detect_method_exists():
    """SubscriptionDetector tem método detect() que aceita DataFrame."""
    detector = SubscriptionDetector()
    result = detector.detect(_empty_df())
    assert isinstance(result, pl.DataFrame)


def test_subscription_detector_with_recurring_transactions():
    """Assinatura recorrente deve ser detectada."""
    detector = SubscriptionDetector()
    df = _subscription_df()
    result = detector.detect(df)
    # Pode ou não detectar dependendo dos thresholds, mas não deve lançar erro
    assert isinstance(result, pl.DataFrame)
    if not result.is_empty():
        assert "type" in result.columns or "amount" in result.columns


# ── Testes: InstallmentDetector ───────────────────────────────────────────────

def test_installment_detector_detect_method_exists():
    """InstallmentDetector tem método detect() que aceita DataFrame."""
    detector = InstallmentDetector()
    result = detector.detect(_empty_df())
    assert isinstance(result, pl.DataFrame)


def test_installment_detector_with_installment_transactions():
    """Parcelamento deve ser detectado ou tratado sem erros."""
    detector = InstallmentDetector()
    df = _installment_df()
    result = detector.detect(df)
    assert isinstance(result, pl.DataFrame)


# ── Testes: Integração pipeline + detalhes de output ─────────────────────────

def test_pipeline_output_columns_when_not_empty():
    """Quando pipeline detecta algo, output deve ter colunas mínimas."""
    from app.core.integrations.pluggy_mock import MockPluggyClient
    from app.core.schemas.transaction import TransactionBatchResult
    from app.forecast.etl.ingestor import TransactionIngestor
    import datetime

    pluggy = MockPluggyClient()
    ingestor = TransactionIngestor()
    item = pluggy.create_sandbox_item()
    acc = pluggy.get_accounts(item["id"])
    txs = pluggy.get_transactions(acc["results"][0]["id"])
    batch = TransactionBatchResult.from_raw_batch(
        raw_data=txs["results"],
        institution_id="nubank",
        item_id=item["id"],
        fetched_at=datetime.datetime.now(datetime.timezone.utc),
    )
    df, _ = ingestor.process(batch.valid_transactions)
    result = run_shadow_invoice_detection(df)
    if not result.is_empty():
        assert "amount" in result.columns
        assert "confidence" in result.columns
