#!/usr/bin/env python3
"""
Script para popular o banco Railway com um usuário mock completo
Cria transações variadas de todos os tipos para testes completos
"""

import asyncio
import os
import sys
import random
from datetime import datetime, timedelta
from decimal import Decimal

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.core.db.users import create_user
from app.core.models.user import User
from app.core.models.account import Account
from app.core.models.transaction import Transaction
from app.core.models.goal import Goal

# Configuração do usuário mock
MOCK_USER_EMAIL = "teste@nexa.com"
MOCK_USER_PASSWORD = "teste123"
MOCK_USER_NAME = "Bruno Teste"

# Categorias de transações
CATEGORIES = {
    "income": [
        "Salário",
        "Freelance",
        "Investimentos",
        "Bônus",
        "13º Salário",
    ],
    "expense": [
        "Alimentação",
        "Transporte",
        "Moradia",
        "Saúde",
        "Educação",
        "Lazer",
        "Assinaturas",
        "Vestuário",
        "Contas",
        "Mercado",
        "Restaurante",
        "Academia",
        "Internet",
        "Telefone",
        "Uber",
        "Gasolina",
        "Shopping",
        "Farmácia",
        "Streaming",
        "Clube",
    ],
}

# Descrições de transações
DESCRIPTIONS = {
    "Alimentação": ["Mercado Extra", "Pão de Açúcar", "Carrefour", "Padaria Central", "Hortifruti"],
    "Transporte": ["Uber", "99 Taxi", "Posto Shell", "Posto Ipiranga", "Estacionamento"],
    "Moradia": ["Aluguel", "Condomínio", "Energia Elétrica", "Água", "IPTU"],
    "Saúde": ["Farmácia São Paulo", "Drogasil", "Consulta Médica", "Laboratório", "Plano de Saúde"],
    "Educação": ["Mensalidade Faculdade", "Curso Online Udemy", "Livros Amazon", "Material Escolar"],
    "Lazer": ["Cinema", "Teatro", "Show", "Parque", "Viagem"],
    "Assinaturas": ["Netflix", "Spotify", "Amazon Prime", "YouTube Premium", "iCloud"],
    "Vestuário": ["Zara", "C&A", "Renner", "Nike", "Adidas"],
    "Contas": ["Conta de Luz", "Conta de Água", "Internet", "Gás", "Telefone"],
    "Mercado": ["Extra", "Carrefour", "Pão de Açúcar", "Walmart", "Assaí"],
    "Restaurante": ["McDonald's", "Outback", "Pizza Hut", "Starbucks", "Subway"],
    "Academia": ["Smart Fit", "Bio Ritmo", "Bodytech", "Personal Trainer"],
    "Internet": ["Vivo Fibra", "NET", "Claro", "TIM"],
    "Telefone": ["Vivo", "Claro", "TIM", "Oi"],
    "Uber": ["Uber - Corrida Centro", "Uber - Aeroporto", "Uber - Shopping"],
    "Gasolina": ["Posto Shell", "Posto Ipiranga", "Posto BR"],
    "Shopping": ["Shopping Iguatemi", "Shopping Pátio Paulista", "Magazine Luiza"],
    "Farmácia": ["Drogasil", "Drogaria São Paulo", "Pague Menos"],
    "Streaming": ["Netflix", "Spotify", "Disney+", "HBO Max", "Apple Music"],
    "Clube": ["Clube Esportivo", "Clube de Campo"],
    "Salário": ["Empressa XYZ S.A."],
    "Freelance": ["Projeto Web", "Consultoria", "Design Freelance"],
    "Investimentos": ["Dividendos", "Renda Fixa", "Tesouro Direto"],
    "Bônus": ["Bônus Anual", "Participação nos Lucros"],
}


def create_mock_transactions(db: Session, user_id: str, account_id: str, months_back: int = 6):
    """Cria transações mock para os últimos N meses"""
    transactions_created = 0
    today = datetime.now()

    # Criar transações de salário (mensal)
    for month_offset in range(months_back):
        # Data do salário (dia 5 de cada mês)
        salary_date = today - timedelta(days=30 * month_offset)
        salary_date = salary_date.replace(day=5)

        salary = Transaction(
            user_id=user_id,
            account_id=account_id,
            description="Salário - Empresa XYZ S.A.",
            amount=Decimal("8500.00"),
            date=salary_date,
            category="Salário",
            type="CREDIT",
            merchant="Empresa XYZ",
        )
        db.add(salary)
        transactions_created += 1

        # Freelance ocasional (40% de chance)
        if random.random() < 0.4:
            freelance_date = salary_date + timedelta(days=random.randint(7, 20))
            freelance = Transaction(
                user_id=user_id,
                account_id=account_id,
                description=random.choice(DESCRIPTIONS["Freelance"]),
                amount=Decimal(str(random.uniform(500, 3000))),
                date=freelance_date,
                category="Freelance",
                type="CREDIT",
            )
            db.add(freelance)
            transactions_created += 1

    # Criar despesas variadas ao longo dos meses
    start_date = today - timedelta(days=30 * months_back)
    current_date = start_date

    while current_date <= today:
        # 3-7 transações por dia (dias úteis mais transações)
        num_transactions = random.randint(3, 7) if current_date.weekday() < 5 else random.randint(1, 4)

        for _ in range(num_transactions):
            category = random.choice(CATEGORIES["expense"])
            possible_descriptions = DESCRIPTIONS.get(category, [f"{category} Genérico"])
            description = random.choice(possible_descriptions)

            # Valores baseados na categoria
            amount_ranges = {
                "Alimentação": (20, 150),
                "Transporte": (15, 80),
                "Moradia": (500, 2500),
                "Saúde": (30, 500),
                "Educação": (50, 1500),
                "Lazer": (40, 300),
                "Assinaturas": (10, 50),
                "Vestuário": (50, 400),
                "Contas": (80, 350),
                "Mercado": (100, 600),
                "Restaurante": (25, 180),
                "Academia": (80, 200),
                "Internet": (100, 150),
                "Telefone": (50, 120),
                "Uber": (12, 45),
                "Gasolina": (200, 350),
                "Shopping": (80, 500),
                "Farmácia": (20, 180),
                "Streaming": (15, 60),
                "Clube": (150, 400),
            }

            min_amt, max_amt = amount_ranges.get(category, (20, 200))
            amount = Decimal(str(round(random.uniform(min_amt, max_amt), 2)))

            transaction = Transaction(
                user_id=user_id,
                account_id=account_id,
                description=description,
                amount=-amount,  # Despesa é negativa
                date=current_date + timedelta(hours=random.randint(6, 22)),
                category=category,
                type="DEBIT",
                merchant=description.split(" - ")[0] if " - " in description else description,
            )
            db.add(transaction)
            transactions_created += 1

        current_date += timedelta(days=1)

    # Criar transações recorrentes (assinaturas)
    subscription_categories = ["Netflix", "Spotify", "Amazon Prime", "YouTube Premium", "iCloud"]
    subscription_prices = [29.90, 21.90, 19.90, 23.90, 9.90]

    for month_offset in range(months_back):
        for i, (sub_name, sub_price) in enumerate(zip(subscription_categories, subscription_prices)):
            # Data da cobrança (dia 1 + offset baseado no serviço)
            sub_date = today - timedelta(days=30 * month_offset)
            sub_date = sub_date.replace(day=1 + i * 3)

            subscription = Transaction(
                user_id=user_id,
                account_id=account_id,
                description=f"{sub_name} - Assinatura Mensal",
                amount=-Decimal(str(sub_price)),
                date=sub_date,
                category="Assinaturas",
                type="DEBIT",
                merchant=sub_name,
            )
            db.add(subscription)
            transactions_created += 1

    # Adicionar investimentos ocasionais
    for month_offset in range(months_back):
        if random.random() < 0.6:  # 60% de chance
            investment_date = today - timedelta(days=30 * month_offset, hours=random.randint(0, 23))
            investment = Transaction(
                user_id=user_id,
                account_id=account_id,
                description=random.choice(DESCRIPTIONS["Investimentos"]),
                amount=Decimal(str(random.uniform(100, 800))),
                date=investment_date,
                category="Investimentos",
                type="CREDIT",
            )
            db.add(investment)
            transactions_created += 1

    db.commit()
    return transactions_created


def create_mock_goals(db: Session, user_id: str):
    """Cria metas financeiras mock"""
    goals_data = [
        {
            "title": "Viagem para Europa",
            "target_amount": Decimal("15000.00"),
            "current_amount": Decimal("8500.00"),
            "deadline": (datetime.now() + timedelta(days=180)).date(),
            "status": "active",
        },
        {
            "title": "Fundo de Emergência",
            "target_amount": Decimal("30000.00"),
            "current_amount": Decimal("22000.00"),
            "deadline": (datetime.now() + timedelta(days=365)).date(),
            "status": "active",
        },
        {
            "title": "Comprar Carro",
            "target_amount": Decimal("60000.00"),
            "current_amount": Decimal("15000.00"),
            "deadline": (datetime.now() + timedelta(days=730)).date(),
            "status": "active",
        },
        {
            "title": "Curso de Inglês",
            "target_amount": Decimal("5000.00"),
            "current_amount": Decimal("5000.00"),
            "deadline": (datetime.now() - timedelta(days=30)).date(),
            "status": "completed",
        },
    ]

    goals_created = 0
    for goal_data in goals_data:
        goal = Goal(
            user_id=user_id,
            title=goal_data["title"],
            target_amount=goal_data["target_amount"],
            current_amount=goal_data["current_amount"],
            deadline=goal_data["deadline"],
            status=goal_data["status"],
        )
        db.add(goal)
        goals_created += 1

    db.commit()
    return goals_created


def main():
    print("🚀 Iniciando seed do banco Railway...")
    print(f"📧 Email: {MOCK_USER_EMAIL}")
    print(f"🔑 Senha: {MOCK_USER_PASSWORD}")
    print(f"👤 Nome: {MOCK_USER_NAME}\n")

    db = SessionLocal()

    try:
        # Verificar se usuário já existe
        existing_user = db.query(User).filter(User.email == MOCK_USER_EMAIL).first()

        if existing_user:
            print(f"⚠️  Usuário {MOCK_USER_EMAIL} já existe!")
            response = input("Deseja recriar? (s/N): ").strip().lower()

            if response == 's':
                # Deletar transações, contas e metas existentes
                db.query(Transaction).filter(Transaction.user_id == existing_user.user_id).delete()
                db.query(Goal).filter(Goal.user_id == existing_user.user_id).delete()
                db.query(Account).filter(Account.user_id == existing_user.user_id).delete()
                db.delete(existing_user)
                db.commit()
                print("✅ Dados antigos removidos")
            else:
                print("❌ Operação cancelada")
                return

        # Criar usuário
        print("👤 Criando usuário...")
        hashed_password = get_password_hash(MOCK_USER_PASSWORD)
        user_data = create_user(
            db=db,
            email=MOCK_USER_EMAIL,
            hashed_password=hashed_password,
            full_name=MOCK_USER_NAME,
        )

        if not user_data:
            print("❌ Erro ao criar usuário")
            return

        user_id = user_data["user_id"]
        print(f"✅ Usuário criado: {user_id}\n")

        # Criar conta bancária
        print("🏦 Criando conta bancária...")
        account = Account(
            user_id=user_id,
            name="Conta Corrente Nubank",
            type="CONTA_CORRENTE",
            balance=Decimal("12500.00"),
            currency="BRL",
            institution="Nubank",
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        print(f"✅ Conta criada: {account.account_id}\n")

        # Criar transações
        print("💰 Criando transações (isso pode demorar um pouco)...")
        months = 6
        transactions_count = create_mock_transactions(db, user_id, account.account_id, months_back=months)
        print(f"✅ {transactions_count} transações criadas ({months} meses)\n")

        # Criar metas
        print("🎯 Criando metas financeiras...")
        goals_count = create_mock_goals(db, user_id)
        print(f"✅ {goals_count} metas criadas\n")

        print("=" * 60)
        print("✨ SEED CONCLU ÍDO COM SUCESSO!")
        print("=" * 60)
        print(f"\n📊 Resumo:")
        print(f"  • Usuário: {MOCK_USER_EMAIL}")
        print(f"  • Senha: {MOCK_USER_PASSWORD}")
        print(f"  • Nome: {MOCK_USER_NAME}")
        print(f"  • Transações: {transactions_count}")
        print(f"  • Metas: {goals_count}")
        print(f"\n🌐 Faça login em: https://codigos-nexa-production-d3b3.up.railway.app")
        print("\n")

    except Exception as e:
        print(f"\n❌ Erro: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
