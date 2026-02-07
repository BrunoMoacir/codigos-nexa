from app.agent.nexa_financial_agent import FinancialAgent
from datetime import date, timedelta

# Simulação completa de histórico financeiro
transactions = [
    {"date": "2024-01-01", "description": "Salário", "amount": 7200},
    {"date": "2024-01-05", "description": "Aluguel", "amount": -2300},
    {"date": "2024-01-10", "description": "Cartão Crédito", "amount": -1900},
    {"date": "2024-01-15", "description": "Mercado", "amount": -1100},

    # Shadow invoices
    {"date": "2024-01-01", "description": "Netflix", "amount": -39.9},
    {"date": "2024-02-01", "description": "Netflix", "amount": -39.9},
    {"date": "2024-03-01", "description": "Netflix", "amount": -39.9},

    {"date": "2024-01-02", "description": "Spotify", "amount": -29.9},
    {"date": "2024-02-02", "description": "Spotify", "amount": -29.9},
    {"date": "2024-03-02", "description": "Spotify", "amount": -29.9},
]

agent = FinancialAgent()

result = agent.run(transactions)

print("\n🧠 NEXA FINANCIAL AGENT RESULT\n")
for k, v in result.items():
    print(f"{k.upper()}:\n{v}\n")
