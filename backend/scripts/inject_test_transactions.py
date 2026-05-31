"""
Injeta transações de teste diretamente via ORM (compatível com SQLite e Postgres).

Convenção de valores:
  - amount < 0 → despesa (padrão extrato bancário — profiler usa amount < 0 para gastos)
  - amount > 0 → crédito/receita (salário, transferências recebidas)
"""
import sys
import os
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.core.models.transaction import Transaction

USER_ID = "054b2734-bf06-4acb-8720-65096d980d68"
ACCOUNT_ID = "acc-test-01"

# Despesas mensais: amount negativo, 3 meses de histórico
EXPENSES = [
    # (categoria, amount, description, transaction_type)
    # Mês 1 (fevereiro)
    ("Alimentação",  -120.0, "iFood almoço",          "CREDIT"),
    ("Alimentação",  -85.0,  "McDonald's",             "CREDIT"),
    ("Alimentação",  -200.0, "Restaurante Silva",      "CREDIT"),
    ("Alimentação",  -60.0,  "Jantar La Trattoria",   "CREDIT"),
    ("Supermercado", -350.0, "Pão de Açúcar",         "CREDIT"),
    ("Supermercado", -410.0, "Carrefour",              "CREDIT"),
    ("Transporte",   -45.0,  "Uber",                   "CREDIT"),
    # Mês 2 (março)
    ("Alimentação",  -150.0, "iFood jantar",           "CREDIT"),
    ("Alimentação",  -95.0,  "Sushi Barão",            "CREDIT"),
    ("Supermercado", -380.0, "Supermercado Extra",     "CREDIT"),
    ("Transporte",   -180.0, "Posto Shell",            "CREDIT"),
    ("Transporte",   -30.0,  "99 Táxi",                "CREDIT"),
    ("Lazer",        -800.0, "Passagem TAM",           "CREDIT"),
    ("Lazer",        -650.0, "Hotel Ibis",             "CREDIT"),
    # Mês 3 (abril)
    ("Alimentação",  -110.0, "iFood almoço",           "CREDIT"),
    ("Saúde",        -200.0, "Farmácia Drogasil",      "CREDIT"),
    ("Educação",     -150.0, "Udemy curso Python",     "CREDIT"),
    ("Lazer",        -100.0, "Cinema Cinemark",        "CREDIT"),
    ("Assinatura",   -70.0,  "Netflix",                "CREDIT"),
    ("Assinatura",   -50.0,  "Spotify",                "CREDIT"),
    ("Compras",      -300.0, "Amazon compra",          "CREDIT"),
    ("Compras",      -220.0, "Mercado Livre",          "CREDIT"),
    ("Supermercado", -290.0, "Pão de Açúcar",         "CREDIT"),
]

# Receitas mensais: amount positivo, 3 meses
INCOME = [
    ("Salário", 8500.0, "Salário empresa XYZ",   "CREDIT"),
    ("Salário", 8500.0, "Salário empresa XYZ",   "CREDIT"),
    ("Salário", 8500.0, "Salário empresa XYZ",   "CREDIT"),
]


def inject():
    db = SessionLocal()
    try:
        deleted = db.query(Transaction).filter(Transaction.user_id == USER_ID).delete()
        db.commit()
        print(f"Removidas {deleted} transações antigas.")

        records = []

        # Despesas distribuídas ao longo de 3 meses
        base_expense = date(2026, 2, 1)
        for i, (cat, amt, desc, ttype) in enumerate(EXPENSES):
            d = base_expense + timedelta(days=(i * 4))
            records.append(Transaction(
                transaction_id=str(uuid.uuid4()),
                user_id=USER_ID,
                account_id=ACCOUNT_ID,
                description=desc,
                amount=amt,
                date=d,
                transaction_type=ttype,
                category=cat,
                is_recurring=False,
                is_installment=False,
                context_type="PF",
                context_confidence=0.95,
                context_override_by_user=False,
                pj_subcategory=None,
            ))

        # Salários: dias 5 de cada mês
        for i, (cat, amt, desc, ttype) in enumerate(INCOME):
            d = date(2026, 2 + i, 5)
            records.append(Transaction(
                transaction_id=str(uuid.uuid4()),
                user_id=USER_ID,
                account_id=ACCOUNT_ID,
                description=desc,
                amount=amt,
                date=d,
                transaction_type="CREDIT",
                category=cat,
                is_recurring=True,
                is_installment=False,
                context_type="PF",
                context_confidence=0.98,
                context_override_by_user=False,
                pj_subcategory=None,
            ))

        db.bulk_save_objects(records)
        db.commit()
        print(f"OK: {len(records)} transacoes inseridas para user_id={USER_ID}")
        print(f"    Despesas: {len(EXPENSES)} | Receitas: {len(INCOME)}")

        count = db.query(Transaction).filter(Transaction.user_id == USER_ID).count()
        print(f"OK: Verificacao: {count} transacoes no banco.")

        # Estimar gasto mensal (deve ser > 0 agora)
        total_expenses = sum(abs(a) for _, a, _, _ in EXPENSES)
        months = 3
        print(f"    gasto_mensal_estimado: R$ {total_expenses / months:.2f}/mes")
        print(f"    renda_mensal_estimada: R$ {sum(a for _, a, _, _ in INCOME) / months:.2f}/mes")

    except Exception as e:
        db.rollback()
        print(f"ERRO: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    inject()
