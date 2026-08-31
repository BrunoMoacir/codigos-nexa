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
    "bradesco": "Bradesco", "caixa": "Caixa Econômica", "pagbank": "PagBank",
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


def _persist_transactions(user_id: str, df, clear_existing: bool = False) -> int:
    """Mapeia o DataFrame do ETL para o ORM transactions_clean e persiste.
    O account_id vem de CADA transação (preserva o banco de origem)."""
    from app.core.database import SessionLocal
    from app.core.models.transaction import Transaction

    date_col = "transaction_date" if "transaction_date" in df.columns else "date"
    cat_col = next((c for c in ("predicted_category", "category") if c in df.columns), None)
    pfpj_col = next((c for c in ("pf_pj_label", "context_type") if c in df.columns), None)
    inst_col = "installment_total" if "installment_total" in df.columns else None
    acc_col = next((c for c in ("account_id", "accountId") if c in df.columns), None)

    rows = df.to_dicts()
    n = 0
    with SessionLocal() as db:
        if clear_existing:
            db.query(Transaction).filter(Transaction.user_id == user_id).delete()
        for r in rows:
            raw_date = r.get(date_col)
            d = raw_date.date() if hasattr(raw_date, "date") else raw_date
            category = r.get(cat_col) if cat_col else None
            pf_pj = (r.get(pfpj_col) or "PF") if pfpj_col else "PF"
            installments = int(r.get(inst_col) or 1) if inst_col else 1
            account_id = str(r.get(acc_col) or f"acc-{user_id}") if acc_col else f"acc-{user_id}"
            db.add(Transaction(
                transaction_id=str(r.get("transaction_id") or f"{user_id}-{n}-{uuid_hex()}"),
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


def uuid_hex() -> str:
    import uuid
    return uuid.uuid4().hex[:8]


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


def _ensure_pluggy_items(persona) -> int:
    """Registra UMA conexão Open Finance por banco conectado da persona."""
    import uuid

    from app.core.database import SessionLocal
    from app.core.models.pluggy_item import PluggyItem

    n = 0
    with SessionLocal() as db:
        db.query(PluggyItem).filter(PluggyItem.user_id == persona.user_id).delete()
        for bank in persona.banks:
            db.add(PluggyItem(
                id=str(uuid.uuid4()),
                user_id=persona.user_id,
                item_id=f"demo-item-{persona.user_id}-{bank.institution}",
                connector_name=bank.name,
            ))
            n += 1
        db.commit()
    return n


def _ensure_goals(persona) -> int:
    """
    Cria as metas da persona.

    `GoalTracker` recebe a sessão por injeção e levanta
    `RuntimeError("requires a database session")` sem ela. Construído vazio,
    TODA criação caía no `except` e o seed seguia dizendo que tinha semeado —
    nenhuma das personas tinha meta, e `get_goals_summary` respondia "você
    ainda não tem metas cadastradas" para as três. É o tratamento de erro mudo
    que o relatório do projeto lista como risco: o log de warning existia e
    ninguém lia.
    """
    from app.core.database import SessionLocal
    from app.goals.tracker import GoalTracker

    criadas = 0
    with SessionLocal() as db:
        tracker = GoalTracker(db)
        existentes = {g.name for g in tracker.list_goals(user_id=persona.user_id)}
        for meta in persona.goals:
            if meta["name"] in existentes:
                continue
            tracker.create_goal(
                user_id=persona.user_id,
                name=meta["name"],
                target_amount=float(meta["target"]),
                current_amount=float(meta.get("current", 0)),
                goal_type=meta.get("type", "outros"),
                target_date=meta.get("target_date"),
            )
            criadas += 1
    return criadas


def seed_persona(persona) -> dict:
    from demo.personas import generate_raw_transactions

    _ensure_user(persona)
    _ensure_plan(persona)
    n_banks = _ensure_pluggy_items(persona)

    # Roda o ETL SEPARADAMENTE por banco (BankStrategy por instituição, como
    # em produção) e persiste tudo sob o mesmo usuário — várias contas.
    by_bank = generate_raw_transactions(persona)
    total_raw = total_valid = total_rej = total_persisted = 0
    first = True
    for institution, raw in by_bank.items():
        if not raw:
            continue
        df, valid, rejected = _run_etl(raw, institution)
        total_raw += len(raw)
        total_valid += valid
        total_rej += rejected
        # limpa as transações do usuário só na primeira instituição
        total_persisted += _persist_transactions(
            persona.user_id, df, clear_existing=first
        )
        first = False

    _ensure_goals(persona)

    return {
        "user_id": persona.user_id,
        "banks": n_banks,
        "raw": total_raw,
        "etl_valid": total_valid,
        "etl_rejected": total_rej,
        "persisted": total_persisted,
    }


def seed_all(reset: bool = False) -> list[dict]:
    from demo.personas import PERSONAS

    results = []
    for key, persona in PERSONAS.items():
        r = seed_persona(persona)
        r["persona"] = key
        results.append(r)
        print(
            f"✅ {persona.full_name:<22} {r['banks']} bancos · raw={r['raw']:>3} → "
            f"ETL válidas={r['etl_valid']:>3} → persistidas={r['persisted']:>3}  [{persona.plan}]"
        )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="repopula do zero")
    parser.add_argument("--base-only", action="store_true",
                        help="só transações (pula o footprint completo)")
    args = parser.parse_args()
    print("Semeando personas pelo ETL real...\n")
    seed_all(reset=args.reset)
    if not args.base_only:
        print("\nEnriquecendo com o footprint completo (contas, score, negociações...)...\n")
        from demo.seed_full import enrich_all
        enrich_all()
    print("\n✨ Pronto. Rode:  streamlit run demo/streamlit_app.py")
