from app.agent.nexa_financial_agent import FinancialAgent

transactions = [
    {"date": "2025-01-01", "description": "Salário", "amount": 7200},
    {"date": "2025-01-02", "description": "Aluguel", "amount": -1800},
    {"date": "2025-01-05", "description": "Netflix", "amount": -39.9},
    {"date": "2025-02-05", "description": "Netflix", "amount": -39.9},
    {"date": "2025-03-05", "description": "Netflix", "amount": -39.9},
    {"date": "2025-01-10", "description": "Mercado", "amount": -600},
]

agent = FinancialAgent()
result = agent.run(transactions)

from pprint import pprint
pprint(result)
