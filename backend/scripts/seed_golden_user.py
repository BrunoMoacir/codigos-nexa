import sys
import polars as pl
from datetime import datetime
from dateutil.relativedelta import relativedelta
import random

sys.path.append('.')
from app.db.queries import save_transactions_clean
from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash

def generate_mock_data(user_id="golden_user_777", num_months=12):
    print(f"Gerando dados sintéticos para {user_id} nos últimos {num_months} meses...")
    
    db = SessionLocal()
    
    # Ensure Golden User exists in PostgreSQL
    user = db.query(User).filter(User.email == "demo@nexa.com").first()
    if not user:
        user = User(
            user_id=user_id,
            email="demo@nexa.com",
            hashed_password=get_password_hash("demo123"),
            full_name="Usuario Master Demo"
        )
        db.add(user)
        try:
            db.commit()
            print("Usuário demo@nexa.com (senha: demo123) criado com sucesso.")
        except Exception as e:
            db.rollback()
            print(f"Erro ao criar user: {e}")
    else:
        user_id = user.user_id # reuse existing user details
    
    end_date = datetime.today()
    start_date = end_date - relativedelta(months=num_months)
    
    # Perfis de gastos
    pf_categories = [
        ("moradia", 2500.0, 3000.0),
        ("alimentacao", 800.0, 1500.0),
        ("transporte", 300.0, 600.0),
        ("saude", 400.0, 500.0),
        ("lazer", 500.0, 1200.0),
        ("vestuario", 100.0, 400.0),
        ("educacao", 800.0, 900.0)
    ]
    
    pj_subcategories = [
        ("software e assinaturas", 200.0, 500.0),
        ("marketing", 500.0, 1500.0),
        ("impostos", 100.0, 300.0),
        ("material de escritorio", 50.0, 150.0)
    ]
    
    data = []
    
    # Salário e Receitas
    current_date = start_date
    tx_id_counter = 1
    
    while current_date <= end_date:
        # 1. Renda Fixa PF
        data.append({
            "transaction_id": f"seed_{tx_id_counter}",
            "description": "SALARIO MENSAL INSS",
            "amount": 12000.0,
            "date": current_date.replace(day=5).date(),
            "transaction_type": "CREDIT",
            "category": "renda",
            "is_recurring": True,
            "is_installment": False,
            "context_type": "PF",
            "context_confidence": 0.99,
            "context_override_by_user": False,
            "pj_subcategory": None
        })
        tx_id_counter += 1
        
        # 2. Receita PJ (Faturamento)
        data.append({
            "transaction_id": f"seed_{tx_id_counter}",
            "description": "RECEBIMENTO NF-E CLIENTE X",
            "amount": 8500.0,
            "date": current_date.replace(day=10).date(),
            "transaction_type": "CREDIT",
            "category": "receita",
            "is_recurring": False,
            "is_installment": False,
            "context_type": "PJ",
            "context_confidence": 0.95,
            "context_override_by_user": False,
            "pj_subcategory": "receita_servicos"
        })
        tx_id_counter += 1

        # 3. Despesas PF
        for cat, min_val, max_val in pf_categories:
            amount = round(random.uniform(min_val, max_val), 2)
            data.append({
                "transaction_id": f"seed_{tx_id_counter}",
                "description": f"COMPRA {cat.upper()}",
                "amount": -amount,  # Despesas são negativas
                "date": current_date.replace(day=random.randint(1, 28)).date(),
                "transaction_type": "DEBIT",
                "category": cat,
                "is_recurring": cat in ["moradia", "educacao", "saude"],
                "is_installment": False,
                "context_type": "PF",
                "context_confidence": 0.9,
                "context_override_by_user": False,
                "pj_subcategory": None
            })
            tx_id_counter += 1

        # 4. Despesas PJ
        for subcat, min_val, max_val in pj_subcategories:
            amount = round(random.uniform(min_val, max_val), 2)
            data.append({
                "transaction_id": f"seed_{tx_id_counter}",
                "description": f"PG COMPRA {subcat.upper()[:10]}",
                "amount": -amount,
                "date": current_date.replace(day=random.randint(1, 28)).date(),
                "transaction_type": "DEBIT",
                "category": "despesa_pj", # Categoria root para PJ
                "is_recurring": subcat in ["software e assinaturas", "impostos"],
                "is_installment": False,
                "context_type": "PJ",
                "context_confidence": 0.95,
                "context_override_by_user": False,
                "pj_subcategory": subcat
            })
            tx_id_counter += 1
            
        current_date += relativedelta(months=1)
        
    df = pl.DataFrame(data)
    print(f"Registros gerados: {len(df)}")
    
    rows = save_transactions_clean(
        db=db,
        df=df,
        user_id=user_id,
        account_id="acc_seed_999"
    )
    print(f"Sucesso! {rows} linhas inseridas em transactions_clean para o {user_id}.")
    db.close()

if __name__ == "__main__":
    generate_mock_data("golden_user_777", num_months=12)
