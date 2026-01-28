from app.simulations.factory import simulate_bank
from app.adapters.bank_adapter import adapt_simulation_to_webhook
from app.etl.ingestor import TransactionIngestor


def run(bank):
    raw = simulate_bank(bank)
    webhook_data = adapt_simulation_to_webhook(raw)

    ingestor = TransactionIngestor()
    df, metrics = ingestor.process(webhook_data)

    print(f"\n===== {bank.upper()} =====")
    print(df)
    print("\nMetrics:", metrics)


if __name__ == "__main__":
    for bank in ["nubank", "itau", "bb"]:
        run(bank)
