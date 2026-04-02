#!/usr/bin/env python3
"""
Script para verificar se os dados foram inseridos corretamente no banco.
"""

import sys
from sqlalchemy import create_engine, text

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

    try:
        with engine.connect() as conn:
            print(f"\n📊 VERIFICANDO DADOS NO BANCO:")
            print("=" * 60)

            # Verificar metas
            print("\n💰 METAS FINANCEIRAS:")
            goals_result = conn.execute(text("""
                SELECT goal_id, name, target_amount, current_amount, status
                FROM financial_goals
                WHERE user_id = :user_id
            """), {"user_id": user_id})

            goals = goals_result.fetchall()
            if goals:
                for goal in goals:
                    print(f"  ✅ {goal[1]} | Target: R${goal[2]:,.2f} | Current: R${goal[3]:,.2f} | Status: {goal[4]}")
            else:
                print("  ❌ Nenhuma meta encontrada!")

            # Verificar assinaturas
            print("\n📱 ASSINATURAS:")
            # Primeiro verificar se a tabela existe
            check_subs_table = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'subscriptions'
                );
            """))
            subs_table_exists = check_subs_table.fetchone()[0]

            if subs_table_exists:
                subs_result = conn.execute(text("""
                    SELECT subscription_id, name, amount, billing_cycle, status
                    FROM subscriptions
                    WHERE user_id = :user_id
                """), {"user_id": user_id})

                subs = subs_result.fetchall()
                if subs:
                    for sub in subs:
                        print(f"  ✅ {sub[1]} | R${sub[2]:,.2f}/{sub[3]} | Status: {sub[4]}")
                else:
                    print("  ❌ Nenhuma assinatura encontrada!")
            else:
                print("  ❌ Tabela 'subscriptions' não existe!")

            # Verificar transações
            print("\n💳 TRANSAÇÕES:")
            trans_result = conn.execute(text("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as receitas,
                       SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as despesas
                FROM transactions_clean
                WHERE user_id = :user_id
            """), {"user_id": user_id})

            trans_stats = trans_result.fetchone()
            print(f"  ✅ {trans_stats[0]} transações | Receitas: R${trans_stats[1]:,.2f} | Despesas: R${trans_stats[2]:,.2f}")

            print("\n" + "=" * 60)

    except Exception as e:
        print(f"\n❌ Erro ao executar: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()