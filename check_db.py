import duckdb

files = [
    "../finance.duckdb",
    "../data/transactions.duckdb",
    "finance.duckdb",
    "nexa.duckdb",
    "data/finance.duckdb",
    "data/transactions.duckdb"
]

for f in files:
    try:
        con = duckdb.connect(f, read_only=True)
        tables = con.execute("SHOW TABLES").fetchall()
        tables = [t[0] for t in tables]
        if "transactions_clean" in tables or "financial_goals" in tables:
            print(f"File {f} has tables: {tables}")
    except Exception as e:
        pass
