#!/usr/bin/env python3
"""
Script para popular o banco de dados do Railway com transações de teste.
Uso: python populate_db_railway.py
"""

import os
import sys
from sqlalchemy import create_engine, text
from datetime import datetime, date

def main():
    # DATABASE_URL do Railway - COLE AQUI a URL do seu banco
    DATABASE_URL = input("Cole a DATABASE_URL do Railway aqui: ").strip()

    if not DATABASE_URL:
        print("❌ DATABASE_URL não fornecida!")
        sys.exit(1)

    # Corrigir prefixo se necessário
    if DATABASE_URL.startswith("postgresql://") and "+psycopg2" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

    print(f"🔗 Conectando ao banco...")
    engine = create_engine(DATABASE_URL, echo=False)

    user_id = '4e40074b-cefa-486c-b12c-f1dde2696aea'

    # Lista de transações para inserir
    transactions = [
        # Salários
        ('txn-salary-mar-2026', user_id, 'acc-001', 'Salário Março/2026', 8500.00, '2026-03-05', 'CREDIT', 'Salário', True, False, 'PF', 0.95, False),
        ('txn-salary-fev-2026', user_id, 'acc-001', 'Salário Fevereiro/2026', 8500.00, '2026-02-05', 'CREDIT', 'Salário', True, False, 'PF', 0.95, False),
        ('txn-salary-jan-2026', user_id, 'acc-001', 'Salário Janeiro/2026', 8500.00, '2026-01-05', 'CREDIT', 'Salário', True, False, 'PF', 0.95, False),

        # Freelances
        ('txn-freelance-1', user_id, 'acc-001', 'Freela Design - Cliente XYZ', 1200.00, '2026-03-15', 'CREDIT', 'Renda Extra', False, False, 'PJ', 0.85, False),
        ('txn-freelance-2', user_id, 'acc-001', 'Consultoria TI', 2500.00, '2026-02-20', 'CREDIT', 'Renda Extra', False, False, 'PJ', 0.90, False),

        # Despesas fixas - Aluguel
        ('txn-rent-mar-2026', user_id, 'acc-001', 'Aluguel Março', -2800.00, '2026-03-10', 'DEBIT', 'Moradia', True, False, 'PF', 0.98, False),
        ('txn-rent-fev-2026', user_id, 'acc-001', 'Aluguel Fevereiro', -2800.00, '2026-02-10', 'DEBIT', 'Moradia', True, False, 'PF', 0.98, False),
        ('txn-rent-jan-2026', user_id, 'acc-001', 'Aluguel Janeiro', -2800.00, '2026-01-10', 'DEBIT', 'Moradia', True, False, 'PF', 0.98, False),

        # Supermercado
        ('txn-market-1', user_id, 'acc-001', 'Carrefour', -385.60, '2026-03-23', 'DEBIT', 'Alimentação', False, False, 'PF', 0.85, False),
        ('txn-market-2', user_id, 'acc-001', 'Extra Supermercado', -422.30, '2026-03-16', 'DEBIT', 'Alimentação', False, False, 'PF', 0.85, False),
        ('txn-market-3', user_id, 'acc-001', 'Pão de Açúcar', -156.90, '2026-03-09', 'DEBIT', 'Alimentação', False, False, 'PF', 0.85, False),

        # Transporte
        ('txn-gas-1', user_id, 'acc-001', 'Posto Shell - Gasolina', -285.00, '2026-03-25', 'DEBIT', 'Transporte', False, False, 'PF', 0.88, False),
        ('txn-uber-1', user_id, 'acc-001', 'Uber - Corrida', -28.40, '2026-03-19', 'DEBIT', 'Transporte', False, False, 'PF', 0.85, False),

        # Contas
        ('txn-energy-mar-2026', user_id, 'acc-001', 'CPFL Energia', -185.50, '2026-03-20', 'DEBIT', 'Contas', True, False, 'PF', 0.90, False),
        ('txn-internet-mar-2026', user_id, 'acc-001', 'Vivo Fibra 500MB', -119.90, '2026-03-08', 'DEBIT', 'Contas', True, False, 'PF', 0.95, False),
        ('txn-phone-mar-2026', user_id, 'acc-001', 'TIM Controle', -54.90, '2026-03-12', 'DEBIT', 'Contas', True, False, 'PF', 0.95, False),

        # Investimentos
        ('txn-invest-1', user_id, 'acc-001', 'Transferência para Poupança', -1000.00, '2026-03-06', 'DEBIT', 'Investimentos', True, False, 'PF', 0.95, False),
        ('txn-invest-2', user_id, 'acc-001', 'Transferência para Poupança', -1000.00, '2026-02-06', 'DEBIT', 'Investimentos', True, False, 'PF', 0.95, False),

        # Entretenimento
        ('txn-netflix-mar-2026', user_id, 'acc-001', 'Netflix Premium', -55.90, '2026-03-18', 'DEBIT', 'Entretenimento', True, False, 'PF', 0.90, False),
        ('txn-cinema-1', user_id, 'acc-001', 'Cinemark - Ingresso', -56.00, '2026-03-22', 'DEBIT', 'Entretenimento', False, False, 'PF', 0.82, False),

        # iFood & Restaurantes
        ('txn-ifood-1', user_id, 'acc-001', 'iFood - Pizza', -78.90, '2026-03-26', 'DEBIT', 'Alimentação', False, False, 'PF', 0.80, False),
        ('txn-ifood-2', user_id, 'acc-001', 'iFood - Burguer', -52.50, '2026-03-21', 'DEBIT', 'Alimentação', False, False, 'PF', 0.80, False),

        # Compras
        ('txn-amazon-1', user_id, 'acc-001', 'Amazon - Livros', -89.90, '2026-03-17', 'DEBIT', 'Compras', False, False, 'PF', 0.82, False),
        ('txn-laptop-1', user_id, 'acc-001', 'Notebook Dell 1/10', -350.00, '2026-03-05', 'DEBIT', 'Compras', False, True, 'PF', 0.95, False),
    ]

    try:
        with engine.connect() as conn:
            # Limpar transações existentes
            print("🧹 Limpando transações existentes...")
            conn.execute(text("DELETE FROM transactions_clean WHERE user_id = :user_id"), {"user_id": user_id})

            # Inserir novas transações
            print("💾 Inserindo transações...")

            insert_sql = """
            INSERT INTO transactions_clean (
                transaction_id, user_id, account_id, description, amount, date,
                transaction_type, category, is_recurring, is_installment,
                context_type, context_confidence, context_override_by_user
            ) VALUES (
                :transaction_id, :user_id, :account_id, :description, :amount, :date,
                :transaction_type, :category, :is_recurring, :is_installment,
                :context_type, :context_confidence, :context_override_by_user
            )
            """

            for i, txn in enumerate(transactions):
                params = {
                    'transaction_id': txn[0],
                    'user_id': txn[1],
                    'account_id': txn[2],
                    'description': txn[3],
                    'amount': txn[4],
                    'date': txn[5],
                    'transaction_type': txn[6],
                    'category': txn[7],
                    'is_recurring': txn[8],
                    'is_installment': txn[9],
                    'context_type': txn[10],
                    'context_confidence': txn[11],
                    'context_override_by_user': txn[12]
                }

                conn.execute(text(insert_sql), params)
                print(f"  ✅ {i+1:2d}/24 - {txn[3][:30]}")

            # Commit todas as transações
            conn.commit()

            # Verificar resultado
            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total_transacoes,
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_receitas,
                    SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as total_despesas,
                    SUM(amount) as saldo_liquido
                FROM transactions_clean
                WHERE user_id = :user_id
            """), {"user_id": user_id})

            row = result.fetchone()

            print("\n" + "="*60)
            print("✅ TRANSAÇÕES INSERIDAS COM SUCESSO!")
            print("="*60)
            print(f"📊 Total de transações: {row[0]}")
            print(f"💰 Total de receitas:   R$ {row[1]:,.2f}")
            print(f"💸 Total de despesas:   R$ {row[2]:,.2f}")
            print(f"📈 Saldo líquido:       R$ {row[3]:,.2f}")
            print("="*60)

    except Exception as e:
        print(f"\n❌ Erro ao executar: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"\n🎉 Pronto! Teste a API:")
    print(f"curl 'https://codigos-nexa-production-d3b3.up.railway.app/api/v1/transactions/{user_id}' | jq length")

if __name__ == "__main__":
    main()
