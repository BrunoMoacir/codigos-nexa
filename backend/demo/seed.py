"""
demo/seed.py — Popula o banco com as personas, passando pelo ETL REAL.

Fluxo idêntico ao de produção (só a origem dos dados muda de Pluggy-real
para Pluggy-gerado):

  raw dicts (personas)
    → TransactionBatchResult.from_raw_batch()   [validação Pydantic]
    → NexaRunner.ingestor.process()             [normalização + dedup + BankStrategy]
    → classifier.predict()                      [categorização ML/regras]
    → pf_pj_classifier.classify_batch()         [PF vs PJ — F4]
    → persiste em transactions_clean            [Postgres, via ORM]
  + cria usuário, plano (user_subscriptions) e metas (financial_goals)

Uso:
    python3 -m demo.seed            # popula as 3 personas
    python3 -m demo.seed --reset    # apaga e repopula
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("demo.seed")

_INSTITUTION_LABEL = {
    "nubank": "Nubank", "itau": "Itaú", "inter": "Banco Inter",
    "bradesco": "Bradesco",
}


def _run_etl(raw: list[dict], institution: str):
    """Roda o ETL real e devolve o DataFrame classificado (PF/PJ)."""
    from app.core.schemas.transaction import TransactionBatchResult
    from app.runner import get_runner

    batch = TransactionBatchResult.from_raw_batch(
        raw_data=raw,
        institution_id=institution,
        item_id=f"demo-item-{institution}",
        fetched_at=datetime.now(timezone.utc),
    )
    if not batch.valid_transactions:
        raise RuntimeError("ETL rejeitou todas as transações da persona")

    runner = get_runner("dev")
    df_clean, _metrics = runner.ingestor.process(batch.valid_transactions)
    df_cat = runner.classifier.predict(df_clean)
    df_pfpj = runner.pf_pj_classifier.classify_batch(df_cat)
    return df_pfpj, batch.total_valid, batch.total_rejected


def _persist_transactions(user_id: str, account_id: str, df) -> int:
    """Mapeia o DataFrame do ETL para o ORM transactions_clean e persiste."""
    import polars as pl

    from app.core.database import SessionLocal
    from app.core.models.transaction import Transaction

    def col(name, default=None):
        return name if name in df.columns else None

    date_col = "transaction_date" if "transaction_date" in df.columns else "date"
    cat_col = next((c for c in ("predicted_category", "category") if c in df.columns), None)
    pfpj_col = next((c for c in ("pf_pj_label", "context_type") if c in df.columns), None)
    inst_col = "installment_total" if "installment_total" in df.columns else None

    rows = df.to_dicts()
    n = 0
    with SessionLocal() as db:
        db.query(Transaction).filter(Transaction.user_id == user_id).delete()
        for r in rows:
            raw_date = r.get(date_col)
            d = raw_date.date() if hasattr(raw_date, "date") else raw_date
            category = r.get(cat_col) if cat_col else None
            pf_pj = (r.get(pfpj_col) or "PF") if pfpj_col else "PF"
            installments = int(r.get(inst_col) or 1) if inst_col else 1
            db.add(Transaction(
                transaction_id=str(r.get("transaction_id") or f"{user_id}-{n}"),
                user_id=user_id,
                account_id=account_id,
                description=str(r.get("description") or "sem descrição"),
                amount=float(r.get("amount") or 0.0),
                date=d,
                transaction_type="CREDIT" if float(r.get("amount") or 0) >= 0 else "DEBIT",
                category=(category or "outros"),
                is_recurring=bool(r.get("is_recurring", False)),
                is_installment=installments > 1,
                context_type=str(pf_pj),
                context_confidence=float(r.get("ml_confidence") or 0.7),
                context_override_by_user=False,
                pj_subcategory=r.get("pj_subcategory"),
            ))
            n += 1
        db.commit()
    return n


def _ensure_user(persona) -> None:
    from app.core.database import SessionLocal
    from app.core.models.user import User
    from app.core.security import get_password_hash

    with SessionLocal() as db:
        user = db.get(User, persona.user_id)
        if user is None:
            db.add(User(
                user_id=persona.user_id,
                email=persona.email,
                hashed_password=get_password_hash("demo1234"),
                full_name=persona.full_name,
                email_verified=True,
                email_verified_at=datetime.now(timezone.utc),
            ))
        else:
            user.full_name = persona.full_name
            user.email = persona.email
        db.commit()


def _ensure_plan(persona) -> None:
    from app.core.database import SessionLocal
    from app.billing.models_orm import UserSubscription

    with SessionLocal() as db:
        rec = db.get(UserSubscription, persona.user_id)
        if rec is None:
            rec = UserSubscription(user_id=persona.user_id, created_at=datetime.now(timezone.utc))
            db.add(rec)
        rec.plan = persona.plan
        rec.status = "active"
        rec.updated_at = datetime.now(timezone.utc)
        db.commit()


def _ensure_pluggy_item(persona) -> None:
    """Registra a instituição conectada (usado por get_transfer_promotions
    e outros que leem pluggy_items)."""
    import uuid

    from app.core.database import SessionLocal
    from app.core.models.pluggy_item import PluggyItem

    with SessionLocal() as db:
        exists = (
            db.query(PluggyItem)
            .filter(PluggyItem.user_id == persona.user_id)
            .first()
        )
        if exists is None:
            db.add(PluggyItem(
                id=str(uuid.uuid4()),
                user_id=persona.user_id,
                item_id=f"demo-item-{persona.user_id}",
                connector_name=_INSTITUTION_LABEL.get(persona.institution, persona.institution),
            ))
            db.commit()


def _ensure_goals(persona) -> None:
    from app.goals.tracker import GoalTracker

    tracker = GoalTracker()
    try:
        existing = {g.name for g in tracker.list_goals(user_id=persona.user_id)}
    except Exception:
        existing = set()
    for g in persona.goals:
        if g["name"] in existing:
            continue
        try:
            tracker.create_goal(
                user_id=persona.user_id,
                name=g["name"],
                target_amount=float(g["target"]),
                current_amount=float(g.get("current", 0)),
                goal_type=g.get("type", "outros"),
            )
        except Exception as exc:
            logger.warning("meta '%s' não criada: %s", g["name"], exc)


def seed_persona(persona) -> dict:
    from demo.personas import generate_raw_transactions

    raw = generate_raw_transactions(persona)
    df, valid, rejected = _run_etl(raw, persona.institution)
    account_id = f"acc-{persona.user_id}"

    _ensure_user(persona)
    _ensure_plan(persona)
    _ensure_pluggy_item(persona)
    n = _persist_transactions(persona.user_id, account_id, df)
    _ensure_goals(persona)

    return {
        "user_id": persona.user_id,
        "raw": len(raw),
        "etl_valid": valid,
        "etl_rejected": rejected,
        "persisted": n,
    }


def seed_all(reset: bool = False) -> list[dict]:
    from demo.personas import PERSONAS

    results = []
    for key, persona in PERSONAS.items():
        r = seed_persona(persona)
        r["persona"] = key
        results.append(r)
        print(
            f"✅ {persona.full_name:<22} raw={r['raw']:>3} → "
            f"ETL válidas={r['etl_valid']:>3} (rej {r['etl_rejected']}) → "
            f"persistidas={r['persisted']:>3}  [{persona.plan}]"
        )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="repopula do zero")
    args = parser.parse_args()
    print("Semeando personas pelo ETL real...\n")
    seed_all(reset=args.reset)
    print("\n✨ Pronto. Rode:  streamlit run demo/streamlit_app.py")
