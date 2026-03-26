"""
seed_mock_data.py — Popula o DuckDB com dados mock realistas para test_user_nexa

Recria transactions_clean com o schema correto do ETL e insere 3 meses
de transacoes (Jan-Mar 2026) para um usuario ficticio com renda ~R$8.500/mes.

Uso:
    cd backend
    python seed_mock_data.py
"""

import uuid
import duckdb
from datetime import date, timedelta
from pathlib import Path

DB_PATH = str(Path(__file__).parent / "finance.duckdb")
USER_ID = "test_user_nexa"
ACCOUNT_ID = "acc_mock_001"

# ─── Transacoes mock (descricao, valor, categoria, context_type, recorrente) ─
# Valores negativos = debito, positivos = credito
MONTHLY_TEMPLATE = [
    # Receitas
    ("Salario Empresa XYZ",        8500.00, "salario",       "PF", False),
    # Moradia
    ("Aluguel",                   -2200.00, "moradia",       "PF", True),
    ("Condominio",                 -450.00, "moradia",       "PF", True),
    ("Energia Eletrica",           -180.00, "moradia",       "PF", True),
    ("Internet Vivo",               -99.90, "moradia",       "PF", True),
    # Alimentacao
    ("Supermercado Extra",         -420.00, "alimentacao",   "PF", False),
    ("iFood - Delivery",           -145.00, "alimentacao",   "PF", False),
    ("Padaria do Bairro",           -85.00, "alimentacao",   "PF", False),
    ("Restaurante Almoco",         -220.00, "alimentacao",   "PF", False),
    # Transporte
    ("Uber",                       -180.00, "transporte",    "PF", False),
    ("Posto Shell - Combustivel",  -280.00, "transporte",    "PF", False),
    ("IPVA Parcelado",             -110.00, "transporte",    "PF", True),
    # Saude
    ("Plano de Saude Amil",        -320.00, "saude",         "PF", True),
    ("Farmacia Drogasil",           -95.00, "saude",         "PF", False),
    # Lazer
    ("Netflix",                     -45.90, "lazer",         "PF", True),
    ("Spotify",                     -21.90, "lazer",         "PF", True),
    ("Cinema Shopping",             -70.00, "lazer",         "PF", False),
    # Educacao
    ("Udemy Curso",                 -89.00, "educacao",      "PF", False),
    # PJ — receitas de freelance (para testar fiscal report)
    ("TED Cliente ABC LTDA",       2000.00, "receita_pj",    "PJ", False),
    ("PIX Projeto Website",        1500.00, "receita_pj",    "PJ", False),
    # PJ — despesas profissionais
    ("Adobe Creative Cloud",       -179.90, "software",      "PJ", True),
    ("Coworking WeWork",           -350.00, "escritorio",    "PJ", True),
]

# Variacao de data (dia do mes) por transacao
DAY_OFFSETS = [5, 1, 2, 10, 10, 12, 14, 18, 20, 8, 15, 1, 1, 22, 1, 1, 16, 23, 7, 20, 1, 1]


def drop_and_recreate(con: duckdb.DuckDBPyConnection) -> None:
    """Dropa transactions_clean (schema antigo) e recria com schema ETL correto."""
    con.execute("DROP TABLE IF EXISTS transactions_clean")
    con.execute("""
        CREATE TABLE transactions_clean (
            transaction_id           VARCHAR PRIMARY KEY,
            user_id                  VARCHAR NOT NULL,
            account_id               VARCHAR,
            description              VARCHAR,
            amount                   DOUBLE,
            date                     DATE,
            transaction_type         VARCHAR,
            category                 VARCHAR,
            is_recurring             BOOLEAN DEFAULT FALSE,
            is_installment           BOOLEAN DEFAULT FALSE,
            context_type             VARCHAR,
            context_confidence       DOUBLE,
            context_override_by_user BOOLEAN DEFAULT FALSE,
            pj_subcategory           VARCHAR,
            processed_at             TIMESTAMP DEFAULT current_timestamp
        )
    """)
    print("  transactions_clean recriada com schema ETL correto.")


def seed_transactions(con: duckdb.DuckDBPyConnection) -> int:
    """Insere 3 meses de transacoes para test_user_nexa."""
    months = [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]

    rows = []
    for month_start in months:
        for i, (desc, amount, category, ctx, is_recurring) in enumerate(MONTHLY_TEMPLATE):
            day = DAY_OFFSETS[i % len(DAY_OFFSETS)]
            # Clamp ao ultimo dia do mes
            try:
                txn_date = month_start.replace(day=day)
            except ValueError:
                txn_date = month_start.replace(day=28)

            txn_type = "credit" if amount > 0 else "debit"
            rows.append((
                str(uuid.uuid4()),   # transaction_id
                USER_ID,             # user_id
                ACCOUNT_ID,          # account_id
                desc,                # description
                amount,              # amount
                txn_date,            # date
                txn_type,            # transaction_type
                category,            # category
                is_recurring,        # is_recurring
                False,               # is_installment
                ctx,                 # context_type
                0.95,                # context_confidence
                False,               # context_override_by_user
                None,                # pj_subcategory
            ))

    con.executemany("""
        INSERT INTO transactions_clean (
            transaction_id, user_id, account_id, description, amount, date,
            transaction_type, category, is_recurring, is_installment,
            context_type, context_confidence, context_override_by_user, pj_subcategory
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    return len(rows)


def seed_health_score(con: duckdb.DuckDBPyConnection) -> None:
    """Insere historico de health score dos ultimos 6 meses."""
    # Garante que a tabela existe
    con.execute("""
        CREATE TABLE IF NOT EXISTS health_score_history (
            user_id      VARCHAR NOT NULL,
            date         VARCHAR NOT NULL,
            health_score INTEGER NOT NULL,
            savings_rate DOUBLE,
            profile_type VARCHAR,
            safe_to_spend DOUBLE,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, date)
        )
    """)
    history = [
        (USER_ID, "2025-10", 58, 0.08, "GASTADOR",      320.0),
        (USER_ID, "2025-11", 62, 0.12, "GASTADOR",      510.0),
        (USER_ID, "2025-12", 67, 0.15, "EQUILIBRADO",   640.0),
        (USER_ID, "2026-01", 72, 0.18, "EQUILIBRADO",   780.0),
        (USER_ID, "2026-02", 75, 0.21, "EQUILIBRADO",   900.0),
        (USER_ID, "2026-03", 79, 0.24, "CONSERVADOR",  1020.0),
    ]
    con.executemany("""
        INSERT OR REPLACE INTO health_score_history
            (user_id, date, health_score, savings_rate, profile_type, safe_to_spend, created_at)
        VALUES (?, ?, ?, ?, ?, ?, NOW())
    """, history)
    print(f"  health_score_history: {len(history)} snapshots inseridos.")


def main() -> None:
    print(f"Conectando em {DB_PATH} ...")
    con = duckdb.connect(DB_PATH)
    try:
        con.execute("BEGIN")

        drop_and_recreate(con)
        n = seed_transactions(con)
        print(f"  transactions_clean: {n} transacoes inseridas para user_id='{USER_ID}'.")

        seed_health_score(con)

        con.execute("COMMIT")
        print("\nSeed concluido com sucesso!")
        print(f"  user_id de teste: {USER_ID}")
        print("  3 meses de dados: Jan-Mar 2026")
        print("  Renda: R$ 8.500/mes (PF) + R$ 3.500/mes (PJ freelance)")
        print("  Health Score: tendencia crescente (58 -> 79)")

    except Exception as e:
        con.execute("ROLLBACK")
        print(f"\nErro durante o seed: {e}")
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
