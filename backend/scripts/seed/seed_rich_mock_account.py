from __future__ import annotations

import random
import sys
from pathlib import Path
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import polars as pl
from dateutil.relativedelta import relativedelta

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal
from app.core.db.users import create_user, get_user_by_email
from app.core.db.queries import save_transactions_clean, get_connection
from app.core.models.transaction import Transaction
from app.core.security import get_password_hash
from app.goals.models import FinancialGoal
from app.health_score.models import HealthScoreHistory


@dataclass
class SeedConfig:
    email: str = "mock.teste@nexa.com"
    password: str = "Mock@12345"
    full_name: str = "Conta Mock Nexa"
    months_back: int = 16
    avg_daily_transactions: int = 6
    seed: int = 42


def _month_days(year: int, month: int) -> int:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    this_month = date(year, month, 1)
    return (next_month - this_month).days


def _generate_monthly_recurring(user_id: str, current_month: date, tx_id_prefix: str) -> list[dict[str, Any]]:
    y, m = current_month.year, current_month.month
    # Salário com pequena variação sazonal (bônus em dez/jan, menor em jul)
    salary_multiplier = 1.0
    if m in (12, 1):
        salary_multiplier = 2.0   # 13º salário
    elif m == 7:
        salary_multiplier = 0.85  # mês fraco

    recurring = [
        ("SALARIO EMPRESA NEXA", round(12500.0 * salary_multiplier, 2), "renda", "credit", True, False, "PF", None),
        ("FATURA CLIENTE PJ", 9200.0, "receita", "credit", False, False, "PJ", "receita_servicos"),
        ("ALUGUEL APARTAMENTO", -2800.0, "moradia", "debit", True, False, "PF", None),
        ("CONTA ENERGIA", -360.0, "moradia", "debit", True, False, "PF", None),
        ("CONTA INTERNET", -140.0, "servicos", "debit", True, False, "PF", None),
        ("NETFLIX", -55.9, "assinaturas", "debit", True, False, "PF", None),
        ("SPOTIFY", -21.9, "assinaturas", "debit", True, False, "PF", None),
        ("PRIME VIDEO", -19.9, "assinaturas", "debit", True, False, "PF", None),   # assinatura extra para auditoria
        ("NOTION BUSINESS", -79.0, "despesa_pj", "debit", True, False, "PJ", "software e assinaturas"),
        ("GOOGLE WORKSPACE", -120.0, "despesa_pj", "debit", True, False, "PJ", "software e assinaturas"),
        ("TARIFA MANUTENCAO CONTA", -15.0, "taxa", "debit", True, False, "PF", None),
        ("ANUIDADE CARTAO PLATINUM", -83.25, "taxa", "debit", True, False, "PF", None),  # R$999/ano em 12x
        ("SEGURO CARTAO CREDITO", -29.9, "taxa", "debit", True, False, "PF", None),
    ]

    rows: list[dict[str, Any]] = []
    for idx, (desc, base_amount, category, tx_type, recurring_flag, installment_flag, context, pj_sub) in enumerate(recurring):
        amount = round(base_amount * random.uniform(0.97, 1.05), 2)
        day = min(5 + idx, _month_days(y, m))
        rows.append(
            {
                "transaction_id": f"{tx_id_prefix}-rec-{y}{m:02d}-{idx}",
                "user_id": user_id,
                "account_id": "acc_mock_main",
                "description": desc,
                "amount": amount,
                "date": date(y, m, day),
                "transaction_type": tx_type,
                "category": category,
                "is_recurring": recurring_flag,
                "is_installment": installment_flag,
                "context_type": context,
                "context_confidence": 0.97,
                "context_override_by_user": False,
                "pj_subcategory": pj_sub,
            }
        )

    return rows


def _generate_installments(user_id: str, current_month: date, tx_id_prefix: str) -> list[dict[str, Any]]:
    y, m = current_month.year, current_month.month
    purchases = [
        ("CELULAR PRO MAX", 12, 649.9, "tecnologia"),
        ("CURSO ESPECIALIZACAO", 10, 420.0, "educacao"),
        ("CADEIRA ERGONOMICA OFFICE", 8, 290.0, "despesa_pj"),
    ]

    rows: list[dict[str, Any]] = []
    for idx, (name, total_parts, installment_value, category) in enumerate(purchases):
        # Espalha o início do parcelamento para manter histórico mais realista
        start_offset = idx * 2
        start_month = current_month - relativedelta(months=start_offset)

        # Calcula qual parcela cai no mês atual
        month_delta = (current_month.year - start_month.year) * 12 + (current_month.month - start_month.month)
        part_number = month_delta + 1
        if part_number <= 0 or part_number > total_parts:
            continue

        context = "PJ" if category == "despesa_pj" else "PF"
        pj_sub = "material de escritorio" if context == "PJ" else None
        day = min(12 + idx, _month_days(y, m))

        rows.append(
            {
                "transaction_id": f"{tx_id_prefix}-ins-{name[:6]}-{y}{m:02d}-{idx}",
                "user_id": user_id,
                "account_id": "acc_mock_card",
                "description": f"{name} {part_number}/{total_parts}",
                "amount": -round(installment_value, 2),
                "date": date(y, m, day),
                "transaction_type": "debit",
                "category": category,
                "is_recurring": False,
                "is_installment": True,
                "context_type": context,
                "context_confidence": 0.94,
                "context_override_by_user": False,
                "pj_subcategory": pj_sub,
            }
        )

    return rows


def _generate_daily_activity(user_id: str, current_month: date, tx_id_prefix: str, avg_daily_transactions: int) -> list[dict[str, Any]]:
    y, m = current_month.year, current_month.month
    days = _month_days(y, m)

    pf_expenses = [
        ("MERCADO CENTRAL", -95, -380, "alimentacao"),
        ("UBER TRIP", -18, -90, "transporte"),
        ("FARMACIA VIDA", -35, -220, "saude"),
        ("RESTAURANTE", -45, -240, "lazer"),
        ("POSTO COMBUSTIVEL", -120, -420, "transporte"),
        ("LOJA ROUPAS", -70, -320, "vestuario"),
    ]

    pj_expenses = [
        ("META ADS", -40, -420, "despesa_pj", "marketing"),
        ("CONTABILIDADE MENSAL", -300, -550, "despesa_pj", "impostos"),
        ("SUPRIMENTOS ESCRITORIO", -35, -180, "despesa_pj", "material de escritorio"),
        ("GOOGLE ADS", -80, -350, "despesa_pj", "marketing"),
        ("IMPOSTO DAS MEI", -70, -72, "despesa_pj", "impostos"),
    ]

    credits = [
        ("PIX RECEBIDO CLIENTE", 300, 2200, "receita", "PJ", "receita_servicos"),
        ("REEMBOLSO SAUDE", 80, 450, "renda", "PF", None),
        ("CASHBACK CARTAO", 10, 120, "renda", "PF", None),
    ]

    # Anomalias pontuais — 1 por mês em dias fixos para serem detectáveis
    anomalies = []
    if m % 3 == 0:  # a cada trimestre: gasto médico alto
        anomalies.append((14, -1350.0, "CLINICA DENTARIA URGENTE", "saude", "PF"))
    if m % 4 == 0:  # a cada 4 meses: viagem/lazer atípico
        anomalies.append((20, -1800.0, "PASSAGEM AEREA GOL", "viagem", "PF"))
    if m % 6 == 0:  # semestralmente: juros rotativos do cartão
        anomalies.append((5, -420.0, "JUROS CARTAO ROTATIVO ITAU", "taxa", "PF"))

    rows: list[dict[str, Any]] = []
    tx_idx = 0

    # Injeta anomalias nos dias correspondentes
    anomaly_by_day: dict[int, list] = {}
    for (aday, aamt, adesc, acat, actx) in anomalies:
        anomaly_by_day.setdefault(aday, []).append((aamt, adesc, acat, actx))

    for day in range(1, days + 1):
        # Anomalias do dia
        for aamt, adesc, acat, actx in anomaly_by_day.get(day, []):
            tx_idx += 1
            rows.append({
                "transaction_id": f"{tx_id_prefix}-an-{y}{m:02d}{day:02d}-{tx_idx}",
                "user_id": user_id,
                "account_id": "acc_mock_main",
                "description": adesc,
                "amount": aamt,
                "date": date(y, m, day),
                "transaction_type": "debit",
                "category": acat,
                "is_recurring": False,
                "is_installment": False,
                "context_type": actx,
                "context_confidence": 0.91,
                "context_override_by_user": False,
                "pj_subcategory": None,
            })

        tx_count = max(2, int(random.gauss(avg_daily_transactions, 2)))
        for _ in range(tx_count):
            chooser = random.random()
            tx_idx += 1

            if chooser < 0.65:
                desc, min_amt, max_amt, category = random.choice(pf_expenses)
                amount = round(random.uniform(min_amt, max_amt), 2)
                rows.append(
                    {
                        "transaction_id": f"{tx_id_prefix}-pf-{y}{m:02d}{day:02d}-{tx_idx}",
                        "user_id": user_id,
                        "account_id": "acc_mock_main",
                        "description": desc,
                        "amount": amount,
                        "date": date(y, m, day),
                        "transaction_type": "debit",
                        "category": category,
                        "is_recurring": False,
                        "is_installment": False,
                        "context_type": "PF",
                        "context_confidence": 0.9,
                        "context_override_by_user": False,
                        "pj_subcategory": None,
                    }
                )
            elif chooser < 0.88:
                desc, min_amt, max_amt, category, pj_sub = random.choice(pj_expenses)
                amount = round(random.uniform(min_amt, max_amt), 2)
                rows.append(
                    {
                        "transaction_id": f"{tx_id_prefix}-pj-{y}{m:02d}{day:02d}-{tx_idx}",
                        "user_id": user_id,
                        "account_id": "acc_mock_business",
                        "description": desc,
                        "amount": amount,
                        "date": date(y, m, day),
                        "transaction_type": "debit",
                        "category": category,
                        "is_recurring": False,
                        "is_installment": False,
                        "context_type": "PJ",
                        "context_confidence": 0.93,
                        "context_override_by_user": False,
                        "pj_subcategory": pj_sub,
                    }
                )
            else:
                desc, min_amt, max_amt, category, context_type, pj_sub = random.choice(credits)
                amount = round(random.uniform(min_amt, max_amt), 2)
                rows.append(
                    {
                        "transaction_id": f"{tx_id_prefix}-cr-{y}{m:02d}{day:02d}-{tx_idx}",
                        "user_id": user_id,
                        "account_id": "acc_mock_main",
                        "description": desc,
                        "amount": amount,
                        "date": date(y, m, day),
                        "transaction_type": "credit",
                        "category": category,
                        "is_recurring": False,
                        "is_installment": False,
                        "context_type": context_type,
                        "context_confidence": 0.92,
                        "context_override_by_user": False,
                        "pj_subcategory": pj_sub,
                    }
                )

    return rows


def _clear_and_create_goals(db, user_id: str) -> int:
    db.query(FinancialGoal).filter(FinancialGoal.user_id == user_id).delete(synchronize_session=False)
    now = datetime.now().isoformat()
    goals = [
        FinancialGoal(
            goal_id=f"goal_mock_{user_id}_emergencia",
            user_id=user_id,
            name="Reserva de Emergência",
            goal_type="emergencia",
            target_amount=20000.0,
            current_amount=8500.0,
            target_date="2026-12-31",
            monthly_contribution_needed=960.0,
            monthly_contribution_actual=800.0,
            status="ACTIVE",
            version=1,
            created_at=now,
            updated_at=now,
        ),
        FinancialGoal(
            goal_id=f"goal_mock_{user_id}_viagem",
            user_id=user_id,
            name="Viagem Internacional",
            goal_type="viagem",
            target_amount=15000.0,
            current_amount=4200.0,
            target_date="2026-07-31",
            monthly_contribution_needed=1767.0,
            monthly_contribution_actual=1200.0,
            status="ACTIVE",
            version=1,
            created_at=now,
            updated_at=now,
        ),
        FinancialGoal(
            goal_id=f"goal_mock_{user_id}_imovel",
            user_id=user_id,
            name="Entrada do Imóvel",
            goal_type="imovel",
            target_amount=120000.0,
            current_amount=27000.0,
            target_date="2028-06-30",
            monthly_contribution_needed=3375.0,
            monthly_contribution_actual=2500.0,
            status="ACTIVE",
            version=1,
            created_at=now,
            updated_at=now,
        ),
        FinancialGoal(
            goal_id=f"goal_mock_{user_id}_carro",
            user_id=user_id,
            name="Troca do Carro",
            goal_type="veiculo",
            target_amount=45000.0,
            current_amount=12000.0,
            target_date="2027-03-31",
            monthly_contribution_needed=1833.0,
            monthly_contribution_actual=1500.0,
            status="ACTIVE",
            version=1,
            created_at=now,
            updated_at=now,
        ),
    ]
    db.add_all(goals)
    db.commit()
    return len(goals)


def _clear_and_create_health_scores(db, user_id: str, months_back: int) -> int:
    db.query(HealthScoreHistory).filter(HealthScoreHistory.user_id == user_id).delete(synchronize_session=False)
    end_month = date.today().replace(day=1)
    start_month = end_month - relativedelta(months=months_back - 1)

    # Score com ciclo realista: começa baixo, melhora, sofre choque, se recupera
    # Fase 1 (meses 0-4):   gastador (44-54) — período de gastos altos
    # Fase 2 (meses 5-9):   equilibrado (58-68) — controle melhorou
    # Fase 3 (meses 10-12): choque (50-55) — anomalias/emergências
    # Fase 4 (meses 13-15): recuperação (60-72) — volta ao trilho
    import math
    scores = []
    current = start_month
    i = 0
    while current <= end_month:
        if i < 5:
            score = 44 + i * 2
        elif i < 10:
            score = 54 + (i - 4) * 2
        elif i < 13:
            score = 64 - (i - 9) * 5
        else:
            score = 50 + (i - 12) * 7
        score = max(40, min(78, score))
        savings_rate = round(max(0.05, 0.08 + (score - 44) * 0.003), 3)
        profile = "GASTADOR" if score < 55 else ("EQUILIBRADO" if score < 68 else "CONSERVADOR")
        safe_to_spend = round(2800 + (score - 44) * 120, 2)
        scores.append(HealthScoreHistory(
            user_id=user_id,
            date=current.strftime("%Y-%m"),
            health_score=score,
            savings_rate=savings_rate,
            profile_type=profile,
            safe_to_spend=safe_to_spend,
        ))
        current += relativedelta(months=1)
        i += 1

    db.add_all(scores)
    db.commit()
    return len(scores)


def _ensure_user(config: SeedConfig) -> tuple[str, bool]:
    db = SessionLocal()
    try:
        existing = get_user_by_email(db, config.email)
        if existing:
            return existing["user_id"], False

        created = create_user(
            db=db,
            email=config.email,
            hashed_password=get_password_hash(config.password),
            full_name=config.full_name,
        )
        if not created:
            raise RuntimeError("Não foi possível criar usuário mock")
        return created["user_id"], True
    finally:
        db.close()


def _clear_transactions_postgres(user_id: str) -> int:
    db = SessionLocal()
    try:
        deleted = db.query(Transaction).filter(Transaction.user_id == user_id).delete(synchronize_session=False)
        db.commit()
        return int(deleted)
    except Exception:
        db.rollback()
        return 0
    finally:
        db.close()


def _clear_transactions_duckdb(user_id: str) -> int:
    try:
        con = get_connection()
        try:
            count = con.execute("SELECT COUNT(*) FROM transactions_clean WHERE user_id = ?", [user_id]).fetchone()[0]
            con.execute("DELETE FROM transactions_clean WHERE user_id = ?", [user_id])
            return int(count)
        finally:
            con.close()
    except Exception:
        return 0


def seed_rich_account(config: SeedConfig) -> None:
    random.seed(config.seed)

    user_id, created_now = _ensure_user(config)
    print(f"Conta mock: {config.email}")
    print(f"Senha mock: {config.password}")
    print(f"user_id: {user_id}")
    print("Usuário criado agora:" , "sim" if created_now else "não (já existia)")

    deleted_pg = _clear_transactions_postgres(user_id)
    deleted_duck = _clear_transactions_duckdb(user_id)
    print(f"Transações antigas removidas -> postgres={deleted_pg}, duckdb={deleted_duck}")

    end_month = date.today().replace(day=1)
    start_month = end_month - relativedelta(months=config.months_back - 1)

    tx_id_prefix = f"mock{datetime.now().strftime('%Y%m%d%H%M%S')}"
    all_rows: list[dict[str, Any]] = []

    current = start_month
    while current <= end_month:
        all_rows.extend(_generate_monthly_recurring(user_id, current, tx_id_prefix))
        all_rows.extend(_generate_installments(user_id, current, tx_id_prefix))
        all_rows.extend(
            _generate_daily_activity(
                user_id=user_id,
                current_month=current,
                tx_id_prefix=tx_id_prefix,
                avg_daily_transactions=config.avg_daily_transactions,
            )
        )
        current = current + relativedelta(months=1)

    df = pl.DataFrame(all_rows)

    db = SessionLocal()
    try:
        rows = save_transactions_clean(db=db, df=df, user_id=user_id, account_id="acc_mock_main")
    finally:
        db.close()

    if rows <= 0:
        raise RuntimeError("Falha ao salvar transações no banco (rows=0)")

    db = SessionLocal()
    try:
        n_goals = _clear_and_create_goals(db, user_id)
        n_scores = _clear_and_create_health_scores(db, user_id, config.months_back)
    finally:
        db.close()

    debit_rows = int(df.filter(pl.col("amount") < 0).height)
    credit_rows = int(df.filter(pl.col("amount") >= 0).height)
    recurrent_rows = int(df.filter(pl.col("is_recurring") == True).height)
    installment_rows = int(df.filter(pl.col("is_installment") == True).height)

    print("\nSeed concluído com sucesso.")
    print(f"Transações inseridas: {rows} (débitos={debit_rows}, créditos={credit_rows}, recorrentes={recurrent_rows}, parceladas={installment_rows})")
    print(f"Metas financeiras: {n_goals} (emergência, viagem, imóvel, carro)")
    print(f"Health score history: {n_scores} meses")
    print("Dica de login no frontend: use email e senha acima em /login")


if __name__ == "__main__":
    seed_rich_account(SeedConfig())
