"""
demo/seed_full.py — Enriquece o banco com o FOOTPRINT COMPLETO de um usuário
real: tudo que a Nexa armazena de fato para quem usa o app há meses.

Roda DEPOIS de demo.seed (que cria usuário, plano, transações via ETL, metas).
Aqui adicionamos as demais tabelas de produção:

  account_balances       — múltiplas contas (corrente + poupança + investimento + cartão)
  health_score_history   — série mensal do score (evolução ao longo do tempo)
  bank_fee_history       — tarifas pagas por mês (alimenta D2/D4 e o Raio-X)
  negotiation_history     — negociações passadas COM DESFECHO (alimenta a calibração!)
  recommendation_feedback — recomendações aceitas/rejeitadas (alimenta acceptance_rate)
  chat_messages          — histórico de conversa com o agente
  user_challenges/badges  — desafios ativos e badges conquistados (via ChallengeService)
  context_overrides       — correção manual PF/PJ que o usuário fez (Bruno)
  architect_simulations   — uma simulação F3 salva (Ana simulou um carro)

Uso:
    python3 -m demo.seed        # base (obrigatório antes)
    python3 -m demo.seed_full   # enriquecimento
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("demo.seed_full")


# Tabelas "raw" (criadas por migração, não por ORM Base). Em ambientes com
# drift de Alembic elas podem faltar; o demo as garante de forma idempotente
# para funcionar em qualquer máquina.
_RAW_TABLES_DDL = [
    """CREATE TABLE IF NOT EXISTS negotiation_history (
        id VARCHAR(36) PRIMARY KEY, user_id VARCHAR NOT NULL, bank_name VARCHAR NOT NULL,
        trigger_type VARCHAR NOT NULL, potential_gain NUMERIC(10,2),
        generated_at TIMESTAMPTZ NOT NULL, result_status VARCHAR,
        result_gain NUMERIC(10,2), resolved_at TIMESTAMPTZ)""",
    """CREATE TABLE IF NOT EXISTS bank_fee_history (
        id VARCHAR(36) PRIMARY KEY, user_id VARCHAR NOT NULL, month VARCHAR(7) NOT NULL,
        bank_name VARCHAR NOT NULL, fee_type VARCHAR NOT NULL, amount NUMERIC(10,2) NOT NULL,
        description VARCHAR,
        CONSTRAINT uq_bank_fee_history UNIQUE (user_id, month, bank_name, fee_type))""",
    """CREATE TABLE IF NOT EXISTS bank_fee_trends (
        id VARCHAR(36) PRIMARY KEY, bank_name VARCHAR NOT NULL, fee_type VARCHAR NOT NULL,
        month VARCHAR(7) NOT NULL, market_avg NUMERIC(10,2), market_p25 NUMERIC(10,2),
        market_p75 NUMERIC(10,2), sample_size INTEGER,
        CONSTRAINT uq_bank_fee_trends UNIQUE (bank_name, fee_type, month))""",
    """CREATE TABLE IF NOT EXISTS user_challenges (
        id VARCHAR(36) PRIMARY KEY, user_id VARCHAR NOT NULL, challenge_type VARCHAR NOT NULL,
        month VARCHAR(7) NOT NULL, title VARCHAR NOT NULL, target_label VARCHAR,
        target_value NUMERIC(12,2), progress_value NUMERIC(12,2) DEFAULT 0,
        pct_progress NUMERIC(5,1) DEFAULT 0, status VARCHAR NOT NULL DEFAULT 'ACTIVE',
        metadata TEXT, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        CONSTRAINT uq_user_challenges UNIQUE (user_id, challenge_type, month))""",
    """CREATE TABLE IF NOT EXISTS user_badges (
        id VARCHAR(36) PRIMARY KEY, user_id VARCHAR NOT NULL, badge_type VARCHAR NOT NULL,
        earned_at TIMESTAMPTZ NOT NULL, metadata TEXT,
        CONSTRAINT uq_user_badges UNIQUE (user_id, badge_type))""",
    """CREATE TABLE IF NOT EXISTS opportunity_snapshots (
        id VARCHAR(36) PRIMARY KEY, user_id VARCHAR NOT NULL, captured_at TIMESTAMPTZ NOT NULL,
        idle_amount NUMERIC(10,2), monthly_loss NUMERIC(10,2), top_opportunity VARCHAR,
        top_gain_brl NUMERIC(10,2), cdi_at_capture NUMERIC(5,4))""",
]


def ensure_schema() -> None:
    """Cria as tabelas raw que o demo toca, caso faltem (idempotente)."""
    from sqlalchemy import text
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        for ddl in _RAW_TABLES_DDL:
            try:
                db.execute(text(ddl))
                db.commit()
            except Exception as exc:
                logger.debug("ensure_schema: %s", exc)
                db.rollback()


def _months_back(n: int) -> list[str]:
    today = date.today()
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(out))


# ── contas e saldos (múltiplas contas por usuário) ───────────────────────

def seed_balances(persona) -> int:
    """Saldos de TODAS as contas em TODOS os bancos conectados da persona."""
    from app.core.database import SessionLocal
    from app.core.models.account_balance import AccountBalance

    now = datetime.now(timezone.utc)
    n = 0
    with SessionLocal() as db:
        db.query(AccountBalance).filter(AccountBalance.user_id == persona.user_id).delete()
        for bank in persona.banks:
            for acc in bank.accounts:
                db.add(AccountBalance(
                    id=str(uuid.uuid4()), user_id=persona.user_id,
                    item_id=f"demo-item-{persona.user_id}-{bank.institution}",
                    account_id=f"acc-{bank.institution}-{acc.type.lower()}",
                    bank_name=bank.name, account_type=acc.type, balance=acc.balance,
                    currency="BRL", captured_at=now,
                ))
                n += 1
        db.commit()
    return n


# ── histórico de health score (evolução mensal) ──────────────────────────

def seed_score_history(persona) -> int:
    from app.core.database import SessionLocal
    from app.health_score.models import HealthScoreHistory

    # trajetórias diferentes: Ana estável-alta, Bruno oscilando, Carla caindo
    trajectories = {
        "demo-ana":   [78, 80, 82, 85, 88, 90],
        "demo-bruno": [55, 48, 60, 42, 58, 50],
        "demo-carla": [62, 55, 48, 40, 33, 28],
    }
    scores = trajectories.get(persona.user_id, [60] * 6)
    profile = {"demo-ana": "EQUILIBRADO", "demo-bruno": "GASTADOR",
               "demo-carla": "ALERTA"}.get(persona.user_id, "EQUILIBRADO")
    n = 0
    with SessionLocal() as db:
        db.query(HealthScoreHistory).filter(
            HealthScoreHistory.user_id == persona.user_id
        ).delete()
        for month, score in zip(_months_back(6), scores):
            db.add(HealthScoreHistory(
                user_id=persona.user_id, date=month, health_score=score,
                savings_rate=round((score - 40) * 0.6, 1), profile_type=profile,
                safe_to_spend=round(score * 4.5, 2),
            ))
            n += 1
        db.commit()
    return n


# ── tarifas pagas por mês (alimenta D2/D4/Raio-X) ────────────────────────

def seed_fee_history(persona) -> int:
    from sqlalchemy import text
    from app.core.database import SessionLocal

    bank = {"nubank": "Nubank", "inter": "Banco Inter",
            "bradesco": "Bradesco"}.get(persona.institution, persona.institution.title())
    # Carla paga muitas tarifas; Ana só pacote; Bruno intermediário
    fee_plan = {
        "demo-ana":   [("manutencao_conta", 34.90)],
        "demo-bruno": [("manutencao_conta", 19.90), ("ted", 12.50)],
        "demo-carla": [("manutencao_conta", 29.90), ("juros_rotativo", 180.00),
                       ("cheque_especial", 95.00)],
    }.get(persona.user_id, [])
    n = 0
    with SessionLocal() as db:
        for month in _months_back(4):
            for ftype, amount in fee_plan:
                # tarifa cresce nos meses recentes para Carla (mudança unilateral)
                mult = 1.0
                if persona.user_id == "demo-carla" and ftype != "manutencao_conta":
                    mult = 1.0 + _months_back(4).index(month) * 0.15
                try:
                    db.execute(text(
                        "INSERT INTO bank_fee_history"
                        " (id, user_id, month, bank_name, fee_type, amount, description)"
                        " VALUES (:id, :uid, :month, :bank, :ftype, :amount, :desc)"
                        " ON CONFLICT DO NOTHING"
                    ), {"id": str(uuid.uuid4()), "uid": persona.user_id, "month": month,
                        "bank": bank, "ftype": ftype, "amount": round(amount * mult, 2),
                        "desc": f"{ftype} {month}"})
                    n += 1
                except Exception as exc:
                    logger.debug("fee_history %s: %s", persona.user_id, exc)
                    db.rollback()
                    return n
        db.commit()
    return n


# ── negociações passadas COM desfecho (alimenta a calibração F13) ────────

def seed_negotiations(persona) -> int:
    from sqlalchemy import text
    from app.core.database import SessionLocal

    bank = {"nubank": "Nubank", "inter": "Banco Inter",
            "bradesco": "Bradesco"}.get(persona.institution, persona.institution.title())
    # desfechos variados para o loop de calibração ter o que aprender
    negs = {
        "demo-ana": [
            ("ANUIDADE_ALTA", 456.0, "sucesso", 380.0, 90),
            ("ANUIDADE_ALTA", 456.0, "parcial", 200.0, 60),
        ],
        "demo-bruno": [
            ("ANUIDADE_ALTA", 300.0, "recusado", None, 45),
        ],
        "demo-carla": [
            ("JUROS_ROTATIVO_ALTO", 220.0, "sucesso", 150.0, 150),
            ("JUROS_ROTATIVO_ALTO", 260.0, "parcial", 90.0, 120),
            ("JUROS_ROTATIVO_ALTO", 300.0, "recusado", None, 95),
            ("JUROS_ROTATIVO_ALTO", 240.0, "sucesso", 160.0, 70),
            ("JUROS_ROTATIVO_ALTO", 280.0, "parcial", 110.0, 45),
            ("JUROS_ROTATIVO_ALTO", 210.0, "sucesso", 140.0, 20),
        ],
    }.get(persona.user_id, [])
    now = datetime.now(timezone.utc)
    n = 0
    with SessionLocal() as db:
        db.execute(text("DELETE FROM negotiation_history WHERE user_id = :uid"),
                   {"uid": persona.user_id})
        for trigger, potential, status, gain, days_ago in negs:
            gen = now - timedelta(days=days_ago)
            resolved = gen + timedelta(days=7)
            try:
                db.execute(text(
                    "INSERT INTO negotiation_history"
                    " (id, user_id, bank_name, trigger_type, potential_gain,"
                    "  generated_at, result_status, result_gain, resolved_at)"
                    " VALUES (:id, :uid, :bank, :trig, :pot, :gen, :st, :gain, :res)"
                ), {"id": str(uuid.uuid4()), "uid": persona.user_id, "bank": bank,
                    "trig": trigger, "pot": potential, "gen": gen, "st": status,
                    "gain": gain, "res": resolved})
                n += 1
            except Exception as exc:
                logger.debug("negotiation %s: %s", persona.user_id, exc)
                db.rollback()
                return n
        db.commit()
    return n


# ── feedback de recomendações (alimenta acceptance_rate) ─────────────────

def seed_feedback(persona) -> int:
    from app.optimizer.queries import save_recommendation_feedback

    fb = {
        "demo-ana": [("CARD_SWITCH", "ACCEPTED"), ("CARD_SWITCH", "ACCEPTED"),
                     ("MUDAR_CATEGORIA", "REJECTED"), ("WAIVER_ALERT", "ACCEPTED")],
        "demo-bruno": [("CARD_SWITCH", "ACCEPTED"), ("MUDAR_CATEGORIA", "IGNORED")],
        "demo-carla": [("MUDAR_CATEGORIA", "ACCEPTED"), ("CARD_SWITCH", "REJECTED")],
    }.get(persona.user_id, [])
    n = 0
    for insight, outcome in fb:
        try:
            save_recommendation_feedback(
                recommendation_id=str(uuid.uuid4()), user_id=persona.user_id,
                insight_id=str(uuid.uuid4()), insight_type=insight, outcome=outcome,
                reason=None, insight_data={"demo": True},
            )
            n += 1
        except Exception as exc:
            logger.debug("feedback %s: %s", persona.user_id, exc)
    return n


# ── histórico de chat com o agente ───────────────────────────────────────

def seed_chat(persona) -> int:
    from app.core.database import SessionLocal
    from app.agent.models import ChatMessage

    convos = {
        "demo-ana": [
            ("human", "Quanto posso gastar esse mês sem me apertar?"),
            ("assistant", "Sua margem segura é de cerca de R$ 380/dia. Você está com o "
                          "score em 90/100 e sobra de caixa saudável — pode manter o padrão."),
            ("human", "Vale trocar meu cartão?"),
            ("assistant", "Pelo seu perfil (foodie), um cartão com cashback alto em "
                          "alimentação recuperaria cerca de R$ 90/mês frente ao atual."),
        ],
        "demo-bruno": [
            ("human", "Quanto vou pagar de DAS esse ano?"),
            ("assistant", "Seu faturamento acumulado está em ~52% do teto MEI. O DAS "
                          "mensal está em dia (R$ 76,90). Margem confortável até o limite."),
        ],
        "demo-carla": [
            ("human", "Meu banco tá cobrando juros abusivos?"),
            ("assistant", "Há forte indício: seu rotativo está bem acima da média BACEN "
                          "para a modalidade. Você pode contestar e pedir portabilidade "
                          "gratuita. Preparei os próximos passos."),
        ],
    }.get(persona.user_id, [])
    now = datetime.now(timezone.utc)
    n = 0
    with SessionLocal() as db:
        db.query(ChatMessage).filter(ChatMessage.user_id == persona.user_id).delete()
        for i, (role, content) in enumerate(convos):
            msg = ChatMessage(user_id=persona.user_id, role=role, content=content)
            msg.created_at = now - timedelta(hours=len(convos) - i)
            db.add(msg)
            n += 1
        db.commit()
    return n


# ── desafios e badges (via serviço real) ─────────────────────────────────

def seed_challenges(persona) -> dict:
    from app.core.db.queries import get_transactions_for_user
    from app.health_score.challenge_service import ChallengeService

    try:
        df = get_transactions_for_user(persona.user_id)
        challenges = ChallengeService().sync(persona.user_id)
        return {"challenges": len(challenges)}
    except Exception as exc:
        logger.debug("challenges %s: %s", persona.user_id, exc)
        return {"challenges": 0}


# ── correção manual PF/PJ (Bruno) ────────────────────────────────────────

def seed_context_override(persona) -> int:
    if persona.user_id != "demo-bruno":
        return 0
    from app.core.database import SessionLocal
    from app.core.models.transaction import Transaction
    from app.divider.models import ContextOverride

    with SessionLocal() as db:
        tx = (
            db.query(Transaction)
            .filter(Transaction.user_id == persona.user_id,
                    Transaction.description.ilike("%ATACADAO%"))
            .first()
        )
        if tx is None:
            return 0
        db.add(ContextOverride(
            id=str(uuid.uuid4()), transaction_id=tx.transaction_id,
            user_id=persona.user_id, original_context="PF",
            corrected_context="PJ", reason="Compra de estoque do negócio",
        ))
        tx.context_type = "PJ"
        tx.context_override_by_user = True
        db.commit()
    return 1


# ── orquestração ─────────────────────────────────────────────────────────

def enrich_persona(persona) -> dict:
    return {
        "contas": seed_balances(persona),
        "score_hist": seed_score_history(persona),
        "tarifas": seed_fee_history(persona),
        "negociações": seed_negotiations(persona),
        "feedback": seed_feedback(persona),
        "chat": seed_chat(persona),
        "override": seed_context_override(persona),
        **seed_challenges(persona),
    }


def enrich_all() -> None:
    from demo.personas import PERSONAS

    ensure_schema()
    for key, persona in PERSONAS.items():
        r = enrich_persona(persona)
        print(
            f"✅ {persona.full_name:<22} contas={r['contas']} score_hist={r['score_hist']} "
            f"tarifas={r['tarifas']} negoc={r['negociações']} feedback={r['feedback']} "
            f"chat={r['chat']} desafios={r['challenges']}"
        )


if __name__ == "__main__":
    print("Enriquecendo o banco com o footprint completo de cada persona...\n")
    enrich_all()
    print("\n✨ Pronto — o banco agora parece uma conta usada há meses.")
