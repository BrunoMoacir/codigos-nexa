#!/usr/bin/env python3
"""
Script para popular o banco Railway via API
Cria um usuário mock completo com transações variadas
"""

import requests
import random
from datetime import datetime, timedelta
from typing import List, Dict

# Configuração
API_URL = "https://codigos-nexa-production-d3b3.up.railway.app/api/v1"
MOCK_USER_EMAIL = "teste@nexa.com"
MOCK_USER_PASSWORD = "teste123"
MOCK_USER_NAME = "Bruno Teste"

# Categorias e descrições
EXPENSE_CATEGORIES = {
    "Alimentação": ["Mercado Extra", "Pão de Açúcar", "Carrefour", "Padaria Central"],
    "Transporte": ["Uber", "99 Taxi", "Posto Shell", "Gasolina Ipiranga"],
    "Moradia": ["Aluguel", "Condomínio", "Energia Elétrica", "Água"],
    "Saúde": ["Farmácia São Paulo", "Drogasil", "Consulta Médica"],
    "Lazer": ["Cinema", "Teatro", "Show", "Netflix", "Spotify"],
    "Mercado": ["Extra", "Carrefour", "Pão de Açúcar"],
    "Restaurante": ["McDonald's", "Outback", "Starbucks", "Subway"],
    "Assinaturas": ["Netflix", "Spotify", "Amazon Prime", "iCloud"],
    "Contas": ["Internet Vivo", "Telefone", "Água", "Luz"],
}

AMOUNT_RANGES = {
    "Alimentação": (20, 150),
    "Transporte": (15, 80),
    "Moradia": (500, 2500),
    "Saúde": (30, 500),
    "Lazer": (40, 300),
    "Mercado": (100, 600),
    "Restaurante": (25, 180),
    "Assinaturas": (10, 50),
    "Contas": (80, 350),
}


def create_user_and_login() -> tuple[str, str]:
    """Cria usuário e faz login, retorna (user_id, token)"""
    print(f"👤 Criando/fazendo login do usuário {MOCK_USER_EMAIL}...")

    # Tentar criar usuário (pode falhar se já existir)
    try:
        response = requests.post(
            f"{API_URL}/auth/register",
            json={
                "email": MOCK_USER_EMAIL,
                "password": MOCK_USER_PASSWORD,
                "full_name": MOCK_USER_NAME,
            },
        )
        if response.status_code == 201:
            print("✅ Usuário criado com sucesso!")
        elif response.status_code == 400:
            print("⚠️  Usuário já existe, fazendo login...")
    except Exception as e:
        print(f"⚠️  Erro ao criar usuário (provavelmente já existe): {e}")

    # Fazer login
    response = requests.post(
        f"{API_URL}/auth/token",
        data={
            "username": MOCK_USER_EMAIL,
            "password": MOCK_USER_PASSWORD,
        },
    )

    if response.status_code != 200:
        raise Exception(f"Erro no login: {response.text}")

    data = response.json()
    token = data["access_token"]
    user_id = data["user_id"]
    print(f"✅ Login bem-sucedido! User ID: {user_id}\n")

    return user_id, token


def generate_transactions(months_back: int = 6) -> List[Dict]:
    """Gera lista de transações mock"""
    transactions = []
    today = datetime.now()

    # Salários mensais
    for month_offset in range(months_back):
        salary_date = today - timedelta(days=30 * month_offset)
        salary_date = salary_date.replace(day=5)

        transactions.append({
            "description": "Salário - Empresa XYZ S.A.",
            "amount": 8500.00,
            "date": salary_date.strftime("%Y-%m-%d"),
            "category": "Salário",
        })

        # Freelance ocasional
        if random.random() < 0.4:
            freelance_date = salary_date + timedelta(days=random.randint(7, 20))
            transactions.append({
                "description": "Freelance - Projeto Web",
                "amount": round(random.uniform(500, 3000), 2),
                "date": freelance_date.strftime("%Y-%m-%d"),
                "category": "Freelance",
            })

    # Despesas variadas
    start_date = today - timedelta(days=30 * months_back)
    current_date = start_date

    while current_date <= today:
        # 3-7 transações por dia
        num_transactions = random.randint(3, 7) if current_date.weekday() < 5 else random.randint(1, 4)

        for _ in range(num_transactions):
            category = random.choice(list(EXPENSE_CATEGORIES.keys()))
            description = random.choice(EXPENSE_CATEGORIES[category])
            min_amt, max_amt = AMOUNT_RANGES.get(category, (20, 200))
            amount = -round(random.uniform(min_amt, max_amt), 2)  # Negativo para despesa

            transactions.append({
                "description": description,
                "amount": amount,
                "date": current_date.strftime("%Y-%m-%d"),
                "category": category,
            })

        current_date += timedelta(days=1)

    # Assinaturas mensais
    subscriptions = [
        ("Netflix", 29.90),
        ("Spotify", 21.90),
        ("Amazon Prime", 19.90),
        ("iCloud", 9.90),
    ]

    for month_offset in range(months_back):
        for i, (name, price) in enumerate(subscriptions):
            sub_date = today - timedelta(days=30 * month_offset)
            sub_date = sub_date.replace(day=1 + i * 3)

            transactions.append({
                "description": f"{name} - Assinatura Mensal",
                "amount": -price,
                "date": sub_date.strftime("%Y-%m-%d"),
                "category": "Assinaturas",
            })

    return transactions


def create_transactions_via_api(token: str, transactions: List[Dict]):
    """
    NOTA: Este script gera as transações mas a API atual não tem endpoint
    público para criar transações individuais.

    As transações virão do Pluggy/Open Finance.

    Este script serve como template para quando houver endpoint de seed.
    """
    print(f"📊 Geramos {len(transactions)} transações mock")
    print("\n⚠️  IMPORTANTE:")
    print("   A API atual não tem endpoint público para criar transações mock.")
    print("   As transações devem vir do Pluggy (Open Finance).")
    print("\n✅ Sugestões:")
    print("   1. Use o endpoint /pluggy/sandbox para criar item de teste")
    print("   2. Ou conecte uma conta real via Pluggy widget")
    print("   3. Depois sincronize com /pluggy/sync\n")


def main():
    print("=" * 70)
    print("🚀 SEED DO BANCO RAILWAY VIA API")
    print("=" * 70)
    print(f"\n📧 Email: {MOCK_USER_EMAIL}")
    print(f"🔑 Senha: {MOCK_USER_PASSWORD}")
    print(f"👤 Nome: {MOCK_USER_NAME}")
    print(f"🌐 API: {API_URL}\n")

    try:
        # Criar usuário e fazer login
        user_id, token = create_user_and_login()

        # Gerar transações
        transactions = generate_transactions(months_back=6)

        # Tentar criar via API (não disponível ainda)
        create_transactions_via_api(token, transactions)

        print("=" * 70)
        print("✨ USUÁRIO CRIADO COM SUCESSO!")
        print("=" * 70)
        print(f"\n🎯 Próximos passos:")
        print(f"   1. Acesse: https://codigos-nexa-production-d3b3.up.railway.app")
        print(f"   2. Faça login com: {MOCK_USER_EMAIL} / {MOCK_USER_PASSWORD}")
        print(f"   3. Vá em 'Conexões' e crie um item Sandbox do Pluggy")
        print(f"   4. Clique em 'Sincronizar transações' para popular os dados\n")

    except Exception as e:
        print(f"\n❌ Erro: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
