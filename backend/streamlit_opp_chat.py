"""
streamlit_opp_chat.py — Chat Nexa + Feed de Oportunidades (OPP em "produção")

Como usar:
    cd backend
    streamlit run streamlit_opp_chat.py

Simula o app já funcionando para um usuário real:
- Usuário rico pré-carregado (12 meses de transações realistas, saldos reais
  de conta corrente e poupança persistidos em account_balances pelo mesmo
  caminho do sync Pluggy, tarifas mensais, assinaturas).
- Esquerda: chat com a IA (claude-haiku + tool use REAL — as 3 tools do OPP:
  get_opportunities, simulate_investment, get_best_bank).
- Direita: Feed de Oportunidades com os cards reais do pipeline de
  notificações (poupança personalizada, dinheiro parado).
- Taxas reais do dia (CDI/SELIC/TR via ANBIMA/BACEN, fallback automático).
"""

from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

_BACKEND = Path(__file__).parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import anthropic
import polars as pl
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except Exception:
    pass

st.set_page_config(page_title="Nexa — Chat + Feed (OPP)", page_icon="💬", layout="wide")

USER_ID = "opp_prod_demo"
USER_BANK = "Nubank"
# Saldos "de produção": profissional que acumulou bônus/13º na conta corrente —
# acima da reserva de emergência (~R$35k = 6× gastos), sobra ociosidade real
# para o radar detectar; poupança relevante para o card personalizado do OPP.4.
CHECKING_BALANCE = 62_000.0
SAVINGS_BALANCE = 18_500.0


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY") or None)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USUÁRIO DE "PRODUÇÃO" — 12 meses de vida financeira realista
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@st.cache_resource
def build_rich_transactions() -> pl.DataFrame:
    """12 meses: salário CLT + freelas, moradia, mercado, restaurantes,
    transporte, farmácia, assinaturas, tarifas — padrão de vida de um
    profissional de R$ 11k/mês em SP com sobra mensal real."""
    rng = random.Random(42)
    rows: list[dict] = []
    first = date.today().replace(day=1)

    def add(d: date, amount: float, desc: str, cat: str):
        rows.append({"date": d, "amount": round(amount, 2), "description": desc,
                     "category": cat, "account_id": "acc_cc_demo"})

    for m in range(1, 13):
        base = (first - timedelta(days=30 * m)).replace(day=1)
        add(base + timedelta(days=4), 11_000.0, "SALARIO TECHCORP LTDA", "salario")
        if m in (1, 7):  # 13º / bônus semestral
            add(base + timedelta(days=19), 5_500.0, "BONUS TECHCORP LTDA", "salario")
        if rng.random() < 0.4:
            add(base + timedelta(days=14), rng.uniform(800, 1_800), "PIX RECEBIDO FREELA DESIGN", "renda_extra")

        add(base + timedelta(days=9), -2_800.0, "ALUGUEL APTO PINHEIROS", "moradia")
        add(base + timedelta(days=9), -420.0, "CONDOMINIO ED SOLAR", "moradia")
        add(base + timedelta(days=11), -rng.uniform(180, 260), "ENEL ENERGIA", "contas")
        add(base + timedelta(days=11), -119.9, "VIVO FIBRA", "contas")

        for _ in range(4):
            add(base + timedelta(days=rng.randint(2, 27)),
                -rng.uniform(180, 420), "SUPERMERCADO PAO DE ACUCAR", "mercado")
        for _ in range(6):
            add(base + timedelta(days=rng.randint(2, 27)),
                -rng.uniform(45, 160), rng.choice(
                    ["IFOOD *RESTAURANTE", "RESTAURANTE CORA", "PADARIA BELLA VISTA"]), "alimentacao")
        for _ in range(8):
            add(base + timedelta(days=rng.randint(2, 27)),
                -rng.uniform(12, 45), "UBER *TRIP", "transporte")
        if rng.random() < 0.6:
            add(base + timedelta(days=rng.randint(5, 25)),
                -rng.uniform(60, 220), "DROGA RAIA", "saude")

        add(base + timedelta(days=15), -55.9, "NETFLIX.COM", "assinaturas")
        add(base + timedelta(days=15), -21.9, "SPOTIFY", "assinaturas")
        add(base + timedelta(days=16), -34.9, "AMAZON PRIME", "assinaturas")

        add(base + timedelta(days=2), -34.9, "TARIFA PACOTE DE SERVICOS", "tarifas")

    return pl.DataFrame(rows).sort("date")


@st.cache_resource
def seed_production_user() -> dict:
    """Persiste os saldos reais (mesmo caminho do sync Pluggy) e resume o perfil."""
    from app.core.database import Base, engine
    from app.core.models.account_balance import AccountBalance
    Base.metadata.create_all(bind=engine, tables=[AccountBalance.__table__])

    from sqlalchemy import text
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        db.execute(text("DELETE FROM account_balances WHERE user_id = :uid"), {"uid": USER_ID})
        db.commit()

    from app.core.db.balances import save_account_balances
    save_account_balances(USER_ID, "item_prod_demo", [
        {"id": "acc_cc_demo", "type": "BANK", "subtype": "CHECKING_ACCOUNT",
         "balance": CHECKING_BALANCE, "currencyCode": "BRL", "connector": {"name": USER_BANK}},
        {"id": "acc_pp_demo", "type": "BANK", "subtype": "SAVINGS_ACCOUNT",
         "balance": SAVINGS_BALANCE, "currencyCode": "BRL", "connector": {"name": USER_BANK}},
    ])
    df = build_rich_transactions()
    return {"transactions": len(df)}


TX_DF = build_rich_transactions()
_seed_info = seed_production_user()


def _patched_engine():
    """Engine lendo o histórico rico deste usuário (perfil comportamental é o
    REAL — ConsumptionProfiler roda sobre essas transações)."""
    from app.opportunities.services.opportunity_engine import OpportunityEngine
    return patch.object(
        OpportunityEngine, "_fetch_transactions", staticmethod(lambda user_id: TX_DF)
    )


def _patched_user_banks():
    from app.opportunities.services.bank_scorecard import BankScorecardService
    return patch.object(BankScorecardService, "_get_user_banks", return_value={USER_BANK})


def brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TOOLS — as 3 tools reais do OPP expostas ao Claude
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOOLS = [
    {
        "name": "get_opportunities",
        "description": (
            "Radar de Oportunidades: detecta dinheiro parado na conta do usuário "
            "(saldo real via Open Finance) e compara com os melhores CDB/LCI/LCA/"
            "Tesouro em rendimento líquido pós-IR, com passos práticos da troca. "
            "Use para: 'tenho dinheiro parado?', 'quanto perco sem investir?', "
            "'onde invisto minha reserva?'."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "simulate_investment",
        "description": (
            "Simula um valor/prazo específico: Tesouro SELIC vs melhor CDB vs "
            "poupança, tudo líquido (IR regressivo + custódia B3). Use quando o "
            "usuário der um valor ou prazo: 'se eu investir R$20 mil por 2 anos...'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Valor em R$"},
                "holding_months": {"type": "integer", "description": "Prazo em meses (padrão 12)"},
            },
            "required": ["amount"],
        },
    },
    {
        "name": "get_best_bank",
        "description": (
            "Bank Match: ranking de bancos pelo perfil completo do usuário — "
            "rendimento ajustado a risco, tarifas que ele paga de verdade, cartões "
            "do emissor e momento financeiro. Use para: 'qual o melhor banco pra "
            "mim?', 'vale trocar de banco?', 'meu banco é bom?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Valor de referência em R$ (opcional)"},
            },
            "required": [],
        },
    },
]


def execute_tool(name: str, tool_input: dict) -> str:
    with _patched_engine(), _patched_user_banks():
        if name == "get_opportunities":
            from app.agent.tools.get_opportunities import get_opportunities
            return get_opportunities.invoke({"user_id": USER_ID})
        if name == "simulate_investment":
            from app.agent.tools.simulate_investment import simulate_investment
            return simulate_investment.invoke({
                "amount": float(tool_input.get("amount", 10_000)),
                "holding_months": int(tool_input.get("holding_months", 12)),
            })
        if name == "get_best_bank":
            from app.agent.tools.get_best_bank import get_best_bank
            return get_best_bank.invoke({
                "user_id": USER_ID,
                "amount": float(tool_input.get("amount", 0.0)),
            })
    return f"Tool desconhecida: {name}"


SYSTEM = f"""Você é o Nexa, assistente de inteligência financeira pessoal do usuário Gabriel.

Contexto do usuário (contas conectadas via Open Finance):
- Banco principal: {USER_BANK}
- Conta corrente: {brl(CHECKING_BALANCE)} | Poupança: {brl(SAVINGS_BALANCE)}
- Renda ~R$ 11.000/mês (CLT + freelas), mora em São Paulo

Regras:
- SEMPRE use as ferramentas para responder sobre investimentos, dinheiro parado,
  poupança ou escolha de banco — nunca invente números.
- Responda em PT-BR, direto e acionável, com os números das ferramentas.
- Os valores das ferramentas já são líquidos de IR quando indicado — destaque
  sempre o ganho em R$/ano e o passo a passo quando existir.
- Nunca omita o aviso de que a Nexa não faz consultoria CVM quando recomendar troca.
"""


def run_agent(messages: list[dict], tool_log) -> tuple[str, list[dict]]:
    client = get_client()
    calls: list[str] = []
    while True:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )
        messages = messages + [{"role": "assistant", "content": resp.content}]

        if resp.stop_reason == "end_turn":
            text = next((b.text for b in resp.content if hasattr(b, "text")), "")
            return text, messages

        if resp.stop_reason == "tool_use":
            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                calls.append(block.name)
                tool_log.info("🔧 " + " → ".join(f"`{c}`" for c in calls))
                with st.spinner(f"⚙️ {block.name}..."):
                    out = execute_tool(block.name, block.input or {})
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(out, ensure_ascii=False)})
            messages = messages + [{"role": "user", "content": results}]
            continue
        break
    return "(sem resposta)", messages


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FEED — cards reais do pipeline de notificações
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@st.cache_data(ttl=300)
def build_feed() -> list[dict]:
    from app.notifications.engine import NotificationEngine
    from app.notifications.notifier import (
        IdleMoneyInput,
        NotificationContext,
        ProactiveNotifier,
    )
    from app.notifications.relevance_filter import NotificationRelevanceFilter
    from app.opportunities.services.opportunity_engine import OpportunityEngine

    ctx = NotificationContext()
    ctx.savings_below_cdi = NotificationEngine._detect_savings_below_cdi(USER_ID)

    with _patched_engine():
        radar = OpportunityEngine().analyze(USER_ID, persist_snapshot=False)
    if radar.idle_amount > 0 and radar.top_opportunity:
        top = radar.top_opportunity
        ctx.idle_money = IdleMoneyInput(
            idle_amount=radar.idle_amount,
            monthly_loss=radar.monthly_loss_in_checking,
            top_opportunity=f"{top.bank_name} {top.product_type} {top.cdi_pct:.0f}% CDI",
            top_gain_monthly_brl=top.monthly_gain_brl,
        )

    notes = ProactiveNotifier().generate(ctx)
    relevant = NotificationRelevanceFilter().filter(notes, monthly_income=11_000.0)
    return [n.to_dict() for n in relevant]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI — chat à esquerda, feed à direita
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.title("💬 Nexa — seu dinheiro trabalhando")
st.caption(f"Gabriel · {USER_BANK} conectado via Open Finance · "
           f"corrente {brl(CHECKING_BALANCE)} · poupança {brl(SAVINGS_BALANCE)} · "
           f"{_seed_info['transactions']} transações (12 meses)")

col_chat, col_feed = st.columns([0.62, 0.38], gap="large")

with col_feed:
    st.subheader("📣 Feed de Oportunidades")
    if st.button("🔄 Atualizar feed"):
        build_feed.clear()
    try:
        feed = build_feed()
    except Exception as exc:
        feed = []
        st.warning(f"Feed indisponível: {exc}")
    if not feed:
        st.info("Nenhuma oportunidade relevante agora.")
    for card in feed:
        with st.container(border=True):
            st.markdown(f"**{card['title']}**")
            st.markdown(card["message"])
            if card.get("action_hint"):
                st.caption(f"💡 {card['action_hint']}")
            badge = "👤 personalizado" if card["metadata"].get("is_personalized") else "📋 geral"
            st.caption(f"`{card['type']}` · {badge}")
    st.caption("Cards gerados pelo pipeline real (geradores → filtro de relevância). "
               "Em produção há ainda dedup por TTL de 14–30 dias.")

with col_chat:
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "display" not in st.session_state:
        st.session_state["display"] = []

    SUGESTOES = [
        "Tenho dinheiro parado na conta?",
        "Minha poupança está rendendo bem?",
        "Se eu investir R$ 20.000 por 2 anos, o que rende mais?",
        "Qual o melhor banco para mim? Vale trocar?",
        "Onde coloco minha reserva de emergência?",
    ]
    if not st.session_state["display"]:
        st.markdown("##### Experimente perguntar:")
        cols = st.columns(2)
        for i, s in enumerate(SUGESTOES):
            if cols[i % 2].button(s, key=f"sug_{i}", use_container_width=True):
                st.session_state["pending"] = s
                st.rerun()

    for role, text in st.session_state["display"]:
        with st.chat_message(role):
            st.markdown(text)

    prompt = st.chat_input("Pergunte sobre seu dinheiro...")
    if not prompt and st.session_state.get("pending"):
        prompt = st.session_state.pop("pending")

    if prompt:
        st.session_state["display"].append(("user", prompt))
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state["messages"].append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            tool_log = st.empty()
            try:
                answer, st.session_state["messages"] = run_agent(
                    st.session_state["messages"], tool_log
                )
            except anthropic.AuthenticationError:
                answer = ("⚠️ ANTHROPIC_API_KEY ausente/inválida — configure no .env "
                          "da raiz do projeto para usar o chat.")
            except Exception as exc:
                answer = f"⚠️ Erro no agente: {exc}"
            st.markdown(answer)
        st.session_state["display"].append(("assistant", answer))

    if st.session_state["display"] and st.button("🗑️ Limpar conversa"):
        st.session_state.pop("messages", None)
        st.session_state.pop("display", None)
        st.rerun()
