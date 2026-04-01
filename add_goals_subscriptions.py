#!/usr/bin/env python3
"""
Script para adicionar Metas e Assinaturas de teste ao banco do Railway.
Uso: python add_goals_subscriptions.py
"""

import sys
from sqlalchemy import create_engine, text
from datetime import datetime, date, timedelta

def main():
    # DATABASE_URL do Railway
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

    # ========================================
    # METAS FINANCEIRAS
    # ========================================

    print("\n💰 Adicionando Metas Financeiras...")

    goals = [
        {
            'goal_id': 'goal-europe-trip',
            'user_id': user_id,
            'name': 'Viagem para Europa',
            'goal_type': 'travel',
            'target_amount': 15000.00,
            'current_amount': 2500.00,
            'target_date': '2026-12-31',
            'monthly_contribution_needed': 1389.00,
            'monthly_contribution_actual': 1000.00,
            'status': 'ACTIVE',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        },
        {
            'goal_id': 'goal-car',
            'user_id': user_id,
            'name': 'Comprar Carro Novo',
            'goal_type': 'purchase',
            'target_amount': 80000.00,
            'current_amount': 15000.00,
            'target_date': '2027-06-30',
            'monthly_contribution_needed': 4333.00,
            'monthly_contribution_actual': 3500.00,
            'status': 'ACTIVE',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        },
        {
            'goal_id': 'goal-emergency',
            'user_id': user_id,
            'name': 'Fundo de Emergência',
            'goal_type': 'emergency_fund',
            'target_amount': 30000.00,
            'current_amount': 8000.00,
            'target_date': '2026-09-30',
            'monthly_contribution_needed': 3667.00,
            'monthly_contribution_actual': 2000.00,
            'status': 'ACTIVE',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        },
        {
            'goal_id': 'goal-house',
            'user_id': user_id,
            'name': 'Entrada Apartamento',
            'goal_type': 'real_estate',
            'target_amount': 120000.00,
            'current_amount': 25000.00,
            'target_date': '2028-12-31',
            'monthly_contribution_needed': 2917.00,
            'monthly_contribution_actual': 2500.00,
            'status': 'ACTIVE',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
    ]

    # ========================================
    # ASSINATURAS (SUBSCRIPTIONS)
    # ========================================

    print("\n📱 Adicionando Assinaturas...")

    subscriptions = [
        {
            'subscription_id': 'sub-netflix',
            'user_id': user_id,
            'name': 'Netflix Premium',
            'category': 'Entretenimento',
            'amount': 55.90,
            'billing_cycle': 'monthly',
            'next_billing_date': (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
            'status': 'active',
            'auto_renew': True
        },
        {
            'subscription_id': 'sub-spotify',
            'user_id': user_id,
            'name': 'Spotify Premium',
            'category': 'Entretenimento',
            'amount': 21.90,
            'billing_cycle': 'monthly',
            'next_billing_date': (date.today() + timedelta(days=8)).strftime('%Y-%m-%d'),
            'status': 'active',
            'auto_renew': True
        },
        {
            'subscription_id': 'sub-adobe',
            'user_id': user_id,
            'name': 'Adobe Creative Cloud',
            'category': 'Trabalho',
            'amount': 145.00,
            'billing_cycle': 'monthly',
            'next_billing_date': (date.today() + timedelta(days=3)).strftime('%Y-%m-%d'),
            'status': 'active',
            'auto_renew': True
        },
        {
            'subscription_id': 'sub-github',
            'user_id': user_id,
            'name': 'GitHub Pro',
            'category': 'Trabalho',
            'amount': 35.00,
            'billing_cycle': 'monthly',
            'next_billing_date': (date.today() + timedelta(days=10)).strftime('%Y-%m-%d'),
            'status': 'active',
            'auto_renew': True
        },
        {
            'subscription_id': 'sub-gym',
            'user_id': user_id,
            'name': 'Smart Fit',
            'category': 'Saúde',
            'amount': 89.90,
            'billing_cycle': 'monthly',
            'next_billing_date': (date.today() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'status': 'active',
            'auto_renew': True
        },
        {
            'subscription_id': 'sub-amazon',
            'user_id': user_id,
            'name': 'Amazon Prime',
            'category': 'Entretenimento',
            'amount': 14.90,
            'billing_cycle': 'monthly',
            'next_billing_date': (date.today() + timedelta(days=15)).strftime('%Y-%m-%d'),
            'status': 'active',
            'auto_renew': True
        }
    ]

    try:
        with engine.connect() as conn:
            # ========================================
            # INSERIR METAS
            # ========================================

            # Limpar metas existentes
            print("  🧹 Limpando metas antigas...")
            conn.execute(text("DELETE FROM financial_goals WHERE user_id = :user_id"), {"user_id": user_id})
            conn.commit()

            # Inserir novas metas
            insert_goal_sql = """
            INSERT INTO financial_goals (
                goal_id, user_id, name, goal_type, target_amount, current_amount,
                target_date, monthly_contribution_needed, monthly_contribution_actual,
                status, created_at, updated_at
            ) VALUES (
                :goal_id, :user_id, :name, :goal_type, :target_amount, :current_amount,
                :target_date, :monthly_contribution_needed, :monthly_contribution_actual,
                :status, :created_at, :updated_at
            )
            """

            for i, goal in enumerate(goals):
                conn.execute(text(insert_goal_sql), goal)
                print(f"  ✅ {i+1}/4 - {goal['name']}")

            conn.commit()

            # ========================================
            # INSERIR ASSINATURAS
            # ========================================

            # Verificar se a tabela existe
            check_table = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'subscriptions'
                );
            """))
            table_exists = check_table.fetchone()[0]

            if not table_exists:
                print("\n  ⚠️  Tabela 'subscriptions' não existe. Criando...")
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        subscription_id VARCHAR PRIMARY KEY,
                        user_id VARCHAR NOT NULL,
                        name VARCHAR NOT NULL,
                        category VARCHAR,
                        amount FLOAT NOT NULL,
                        billing_cycle VARCHAR NOT NULL,
                        next_billing_date DATE NOT NULL,
                        status VARCHAR NOT NULL,
                        auto_renew BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
                """))
                conn.commit()
                print("  ✅ Tabela criada!")

            # Limpar assinaturas existentes
            print("  🧹 Limpando assinaturas antigas...")
            conn.execute(text("DELETE FROM subscriptions WHERE user_id = :user_id"), {"user_id": user_id})
            conn.commit()

            # Inserir novas assinaturas
            insert_sub_sql = """
            INSERT INTO subscriptions (
                subscription_id, user_id, name, category, amount, billing_cycle,
                next_billing_date, status, auto_renew
            ) VALUES (
                :subscription_id, :user_id, :name, :category, :amount, :billing_cycle,
                :next_billing_date, :status, :auto_renew
            )
            """

            for i, sub in enumerate(subscriptions):
                conn.execute(text(insert_sub_sql), sub)
                print(f"  ✅ {i+1}/6 - {sub['name']}")

            conn.commit()

            # ========================================
            # VERIFICAR RESULTADO
            # ========================================

            result_goals = conn.execute(text("""
                SELECT COUNT(*) as total,
                       SUM(target_amount) as total_target,
                       SUM(current_amount) as total_current
                FROM financial_goals
                WHERE user_id = :user_id
            """), {"user_id": user_id})

            goal_stats = result_goals.fetchone()

            result_subs = conn.execute(text("""
                SELECT COUNT(*) as total,
                       SUM(amount) as monthly_cost
                FROM subscriptions
                WHERE user_id = :user_id AND status = 'active'
            """), {"user_id": user_id})

            sub_stats = result_subs.fetchone()

            print("\n" + "="*60)
            print("✅ DADOS INSERIDOS COM SUCESSO!")
            print("="*60)
            print(f"\n💰 METAS FINANCEIRAS:")
            print(f"   Total de metas: {goal_stats[0]}")
            print(f"   Meta total: R$ {goal_stats[1]:,.2f}")
            print(f"   Já economizado: R$ {goal_stats[2]:,.2f}")
            print(f"   Falta economizar: R$ {(goal_stats[1] - goal_stats[2]):,.2f}")

            print(f"\n📱 ASSINATURAS:")
            print(f"   Total de assinaturas: {sub_stats[0]}")
            print(f"   Custo mensal: R$ {sub_stats[1]:,.2f}")
            print(f"   Custo anual: R$ {(sub_stats[1] * 12):,.2f}")
            print("="*60)

    except Exception as e:
        print(f"\n❌ Erro ao executar: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"\n🎉 Pronto! Teste no frontend em http://localhost:3000")

if __name__ == "__main__":
    main()
