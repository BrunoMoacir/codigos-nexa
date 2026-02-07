from app.agent.nexa_financial_agent import FinancialAgent


def main():
    agent = FinancialAgent()

    print("\n🚀 Executando análise financeira completa...\n")

    result = agent.run(user_id="user_test_001")

    print("\n📊 RESULTADO FINAL:\n")
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
