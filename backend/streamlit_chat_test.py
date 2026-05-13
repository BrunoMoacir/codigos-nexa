"""
streamlit_chat_test.py — Testador de Chat do Agente Nexa

Testa o endpoint POST /api/v1/chat/ com todos os 14 cenarios de ferramentas.

Uso:
    cd backend && streamlit run streamlit_chat_test.py
"""
import json
import time
import uuid

import requests
import streamlit as st

st.set_page_config(
    page_title="Nexa — Chat Tester",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

_DEFS = {
    "token": None,
    "user_id": None,
    "user_email": None,
    "chat_messages": [],
    "session_id": str(uuid.uuid4()),
    "api_url": "http://localhost:8000",
    "show_debug": False,
    "last_raw": None,
}
for _k, _v in _DEFS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


def _base() -> str:
    return st.session_state.api_url.rstrip("/")


def _hdr() -> dict:
    t = st.session_state.token
    return {"Authorization": f"Bearer {t}"} if t else {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 14 FERRAMENTAS — cenarios de teste
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOLS = [
    {
        "id": "get_user_profile_context",
        "icon": "🧠",
        "label": "Perfil do usuario",
        "msgs": [
            "Qual meu perfil financeiro?",
            "Como voce me ve financeiramente?",
            "Tenho algum evento de vida recente que devo considerar?",
        ],
    },
    {
        "id": "get_financial_forecast",
        "icon": "📊",
        "label": "Forecast financeiro",
        "msgs": [
            "Como estao minhas financas este mes?",
            "Quanto posso gastar hoje com seguranca?",
            "Qual minha saude financeira atual?",
        ],
    },
    {
        "id": "get_budget_advice",
        "icon": "📋",
        "label": "Orcamento 50/30/20",
        "msgs": [
            "Minha renda e R$ 8.500. Como devo organizar meu orcamento?",
            "Estou gastando bem para quem ganha R$ 6.000 por mes?",
            "Me explica a regra 50/30/20 para uma renda de R$ 10.000.",
        ],
    },
    {
        "id": "get_card_optimization",
        "icon": "💳",
        "label": "Cartao de credito",
        "msgs": [
            "Minha renda e R$ 8.500. Qual cartao de credito devo pedir?",
            "Vale a pena pagar anuidade de cartao premium para quem ganha R$ 15.000?",
            "Quero maximizar minhas milhas. Qual cartao me indica?",
        ],
    },
    {
        "id": "get_spending_alerts",
        "icon": "🔔",
        "label": "Alertas de gastos",
        "msgs": [
            "Tem algum alerta nas minhas financas?",
            "Algum gasto estranho ou anormal este mes?",
            "O que devo me preocupar financeiramente agora?",
        ],
    },
    {
        "id": "get_goals_summary",
        "icon": "🎯",
        "label": "Metas financeiras",
        "msgs": [
            "Como estao minhas metas financeiras?",
            "Quanto falta para minha reserva de emergencia?",
            "Consigo poupar R$ 700 por mes. Quando vou atingir minhas metas?",
        ],
    },
    {
        "id": "get_financing_simulation",
        "icon": "🏠",
        "label": "Simulacao de financiamento",
        "msgs": [
            "Quero comprar um carro de R$ 60.000. Vale a pena financiar ou poupar?",
            "Estou pensando em comprar um apartamento de R$ 400.000 com R$ 80.000 de entrada.",
            "Quero reformar minha casa por R$ 25.000. Financiamento ou consorcio?",
        ],
    },
    {
        "id": "get_timing_scenarios",
        "icon": "⏰",
        "label": "Cenarios de timing",
        "msgs": [
            "Vale a pena esperar 6 meses para ter mais entrada no carro de R$ 60.000? Consigo poupar R$ 1.500/mes.",
            "Se eu esperar 12 meses juntando R$ 2.000/mes, quanto economizo no financiamento de R$ 300.000?",
            "Compro o imovel agora com R$ 50.000 de entrada ou espero 6 meses para ter R$ 60.000?",
        ],
    },
    {
        "id": "get_leverage_simulation",
        "icon": "🏗️",
        "label": "Alavancagem imobiliaria",
        "msgs": [
            "Consigo comprar um imovel sem gastar nada por mes com consorcio?",
            "Quero um ape de 70m2 no Buritis em BH. O aluguel paga as parcelas do consorcio?",
            "Vale a pena fazer consorcio maior e investir o surplus? Tenho R$ 2.000/mes disponivel.",
        ],
    },
    {
        "id": "get_fiscal_report",
        "icon": "📑",
        "label": "Relatorio fiscal MEI/PJ",
        "msgs": [
            "Quanto vou pagar de DAS esse mes como MEI?",
            "Me da um relatorio das receitas e despesas do meu negocio de 2026.",
            "Qual meu faturamento PJ e o imposto estimado no Simples Nacional?",
        ],
    },
    {
        "id": "get_peer_comparison",
        "icon": "👥",
        "label": "Comparacao com pares",
        "msgs": [
            "Minha renda e R$ 8.000. Estou gastando mais que a media em moradia?",
            "Comparado a pessoas com renda de R$ 5.000, como estou em alimentacao e lazer?",
            "Qual meu percentil de poupanca para quem ganha R$ 12.000 por mes?",
        ],
    },
    {
        "id": "get_purchase_recommendation",
        "icon": "🛒",
        "label": "Compra inteligente",
        "msgs": [
            "Qual a melhor forma de pagar R$ 3.000 em eletronicos em 12x?",
            "Vale mais a pena parcelar uma TV de R$ 4.500 em 10x ou pagar no PIX?",
            "Vou comprar uma moto de R$ 12.000. Devo pegar CDC ou parcelar no cartao?",
        ],
    },
    {
        "id": "get_bank_cost_analysis",
        "icon": "🏦",
        "label": "Custos bancarios",
        "msgs": [
            "Quanto estou pagando de tarifas e anuidades bancarias?",
            "Meu banco esta me cobrando muito? Quanto economizo trocando para um banco digital?",
            "Quais sao meus custos bancarios mensais?",
        ],
    },
    {
        "id": "get_negotiation_script",
        "icon": "🤝",
        "label": "Negociador bancario",
        "msgs": [
            "Como negocio a isencao da minha anuidade de cartao?",
            "Meu banco esta me cobrando juros altos. Me da um script para falar com o gerente.",
            "Tenho poder de barganha com meu banco? Quero renegociar minhas tarifas.",
        ],
    },
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SIDEBAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with st.sidebar:
    st.title("Nexa Chat Tester")

    # Backend
    st.subheader("Backend")
    col_url, col_ping = st.columns([3, 1])
    _api = col_url.text_input("URL", value=st.session_state.api_url, label_visibility="collapsed")
    st.session_state.api_url = _api.rstrip("/")
    if col_ping.button("Ping"):
        try:
            r = requests.get(f"{_base()}/health", timeout=3)
            st.success("Online") if r.status_code == 200 else st.warning(f"HTTP {r.status_code}")
        except Exception:
            st.error("Offline")

    st.divider()

    # Auth
    if st.session_state.token:
        st.success(f"Logado: {st.session_state.user_email}")
        st.caption(f"`{st.session_state.user_id}`")
        if st.button("Logout", use_container_width=True):
            try:
                requests.post(f"{_base()}/api/v1/auth/logout", headers=_hdr(), timeout=5)
            except Exception:
                pass
            for k in ("token", "user_id", "user_email", "chat_messages", "last_raw"):
                st.session_state[k] = None if k != "chat_messages" else []
            st.session_state.session_id = str(uuid.uuid4())
            st.rerun()
    else:
        at, rt = st.tabs(["Login", "Registro"])
        with at:
            le = st.text_input("E-mail", key="le")
            lp = st.text_input("Senha", type="password", key="lp")
            if st.button("Entrar", use_container_width=True):
                try:
                    r = requests.post(
                        f"{_base()}/api/v1/auth/token",
                        data={"username": le, "password": lp},
                        timeout=10,
                    )
                    if r.status_code == 200:
                        d = r.json()
                        st.session_state.token = d["access_token"]
                        st.session_state.user_id = d["user_id"]
                        st.session_state.user_email = le
                        st.session_state.chat_messages = []
                        st.session_state.session_id = str(uuid.uuid4())
                        st.rerun()
                    else:
                        st.error(r.json().get("detail", r.text))
                except Exception as exc:
                    st.error(str(exc))
        with rt:
            rn = st.text_input("Nome", key="rn")
            re = st.text_input("E-mail", key="re")
            rp = st.text_input("Senha", type="password", key="rp")
            if st.button("Criar conta", use_container_width=True):
                try:
                    r = requests.post(
                        f"{_base()}/api/v1/auth/register",
                        json={"full_name": rn, "email": re, "password": rp},
                        timeout=10,
                    )
                    if r.status_code in (200, 201):
                        st.success("Conta criada! Faca login.")
                    else:
                        st.error(r.json().get("detail", r.text))
                except Exception as exc:
                    st.error(str(exc))

    st.divider()

    # Cenarios das 14 ferramentas
    st.subheader("Cenarios de teste")
    st.caption("Clique para enviar ao chat.")

    for tool in TOOLS:
        with st.expander(f"{tool['icon']} {tool['label']}"):
            for msg in tool["msgs"]:
                label = msg[:60] + ("..." if len(msg) > 60 else "")
                if st.button(label, key=f"sc_{tool['id']}_{msg[:15]}"):
                    st.session_state["_pending"] = msg

    st.divider()
    st.caption("Chat Tester v1.0 — 14 ferramentas")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
uid = st.session_state.user_id or "SEU_USER_ID"

col_title, col_actions = st.columns([4, 2])
col_title.title("Nexa — Chat do Agente")
col_title.caption(f"`POST /api/v1/chat/`  |  session `{st.session_state.session_id[:8]}...`")

with col_actions:
    st.write("")
    c1, c2, c3 = st.columns(3)
    if c1.button("Nova sessao"):
        st.session_state.chat_messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.last_raw = None
        st.rerun()
    if c2.button("Limpar hist DB"):
        try:
            requests.delete(
                f"{_base()}/api/v1/chat/history",
                params={"user_id": uid},
                headers=_hdr(),
                timeout=10,
            )
            st.toast("Historico removido.")
        except Exception as exc:
            st.toast(f"Erro: {exc}")
    st.session_state.show_debug = c3.toggle("Debug", value=st.session_state.show_debug)

if not st.session_state.token:
    st.info("Faca login na barra lateral para usar o chat.")
    st.stop()

# ── historico de mensagens ────────────────────────────────────────────────────
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("lat"):
            st.caption(f"⏱ {msg['lat']:.0f} ms")

# ── input ─────────────────────────────────────────────────────────────────────
pending = st.session_state.pop("_pending", None)
user_input = st.chat_input("Digite ou escolha um cenario no menu lateral...")
msg_to_send = pending or user_input or None

if msg_to_send:
    st.session_state.chat_messages.append({"role": "user", "content": msg_to_send})
    with st.chat_message("user"):
        st.markdown(msg_to_send)

    with st.chat_message("assistant"):
        with st.spinner("Nexa pensando..."):
            t0 = time.time()
            try:
                r = requests.post(
                    f"{_base()}/api/v1/chat/",
                    json={
                        "user_id": uid,
                        "message": msg_to_send,
                        "session_id": st.session_state.session_id,
                    },
                    headers=_hdr(),
                    timeout=120,
                )
                lat = (time.time() - t0) * 1000
                raw = r.json()
                if r.status_code == 200:
                    reply = raw.get("response", "(sem resposta)")
                else:
                    reply = f"Erro {r.status_code}: {raw.get('detail', r.text)}"
            except Exception as exc:
                lat = (time.time() - t0) * 1000
                raw = None
                reply = f"Erro de conexao: {exc}"

        st.markdown(reply)
        st.caption(f"⏱ {lat:.0f} ms")
        st.session_state.last_raw = raw

    st.session_state.chat_messages.append({"role": "assistant", "content": reply, "lat": lat})
    st.rerun()

# ── debug panel ───────────────────────────────────────────────────────────────
if st.session_state.show_debug and st.session_state.last_raw:
    with st.expander("Resposta bruta do servidor", expanded=True):
        st.json(st.session_state.last_raw)

# ── historico persistido ──────────────────────────────────────────────────────
with st.expander("Historico persistido no banco"):
    if st.button("Buscar historico"):
        try:
            r = requests.get(
                f"{_base()}/api/v1/chat/history",
                params={"user_id": uid},
                headers=_hdr(),
                timeout=10,
            )
            color = "green" if r.status_code == 200 else "red"
            st.markdown(f"**Status:** :{color}[{r.status_code}]")
            try:
                st.json(r.json())
            except Exception:
                st.code(r.text)
        except Exception as exc:
            st.error(str(exc))
