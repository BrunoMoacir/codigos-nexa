"""
streamlit_nexa_completo.py — Testador de Inteligencia do Chat Nexa
Uso: cd backend && streamlit run streamlit_nexa_completo.py
"""
import sys
import time
import uuid
from pathlib import Path

import requests
import streamlit as st

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

st.set_page_config(page_title="Nexa Chat", page_icon="💬", layout="centered")

_DEFS = {
    "token": None,
    "user_id": None,
    "user_email": None,
    "messages": [],
    "session_id": str(uuid.uuid4()),
    "api_url": "http://localhost:8000",
}
for _k, _v in _DEFS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

def _base():
    return st.session_state.api_url.rstrip("/")

def _hdr():
    t = st.session_state.token
    return {"Authorization": f"Bearer {t}"} if t else {}

# ─── Cenarios de teste por ferramenta ─────────────────────────────────────────
CENARIOS = {
    "🧠 Perfil financeiro": [
        "Qual meu perfil financeiro?",
        "Como voce me ve financeiramente?",
        "Tenho algum evento de vida recente que devo considerar nas minhas financas?",
        "Qual meu cluster de estilo de vida e o que ele significa?",
    ],
    "📊 Previsao / Saude": [
        "Como estao minhas financas este mes?",
        "Quanto posso gastar hoje com seguranca?",
        "Qual minha saude financeira atual?",
        "Minha saude financeira esta melhorando ou piorando ao longo do tempo?",
    ],
    "📋 Orcamento 50/30/20": [
        "Minha renda e R$ 12.500. Como devo organizar meu orcamento?",
        "Estou gastando bem para quem ganha R$ 12.500 por mes?",
        "Me explica a regra 50/30/20 para uma renda de R$ 12.500.",
        "Quais categorias estao fora do limite ideal no meu orcamento?",
    ],
    "💳 Otimizador de Cartoes": [
        "Minha renda e R$ 12.500. Qual cartao de credito devo pedir?",
        "Vale a pena pagar anuidade de cartao premium para quem ganha R$ 15.000?",
        "Quero maximizar minhas milhas. Qual cartao me indica?",
        "Qual cartao tem melhor cashback para o meu perfil de gastos?",
    ],
    "🔔 Alertas e Anomalias": [
        "Tem algum alerta nas minhas financas?",
        "Algum gasto estranho ou anormal este mes?",
        "O que devo me preocupar financeiramente agora?",
        "Tive algum gasto muito acima da media nos ultimos meses?",
    ],
    "🎯 Metas": [
        "Como estao minhas metas financeiras?",
        "Quanto falta para minha reserva de emergencia?",
        "Consigo poupar R$ 2.500 por mes. Quando vou atingir minhas metas?",
        "Qual meta devo priorizar agora?",
    ],
    "🏠 Financiamento / Arquiteto": [
        "Quero comprar um carro de R$ 60.000. Vale a pena financiar ou poupar?",
        "Estou pensando em comprar um apartamento de R$ 400.000 com R$ 80.000 de entrada. O que fazer?",
        "Vale a pena esperar 6 meses para ter mais entrada no carro de R$ 60.000? Consigo poupar R$ 2.500/mes.",
        "Consigo comprar um imovel sem gastar nada por mes com consorcio?",
        "Se eu esperar 12 meses juntando R$ 2.500/mes, quanto economizo no financiamento de R$ 300.000?",
    ],
    "🛒 Compra Inteligente": [
        "Qual a melhor forma de pagar R$ 3.000 em eletronicos em 12x?",
        "Vale mais a pena parcelar uma TV de R$ 4.500 em 10x ou pagar no PIX?",
        "Vou comprar uma moto de R$ 12.000. Devo pegar CDC ou parcelar no cartao?",
        "Tenho R$ 5.000 disponivel. Vale a pena pagar a vista ou parcelar e investir o restante?",
    ],
    "🏦 Custos Bancarios": [
        "Quanto estou pagando de tarifas e anuidades bancarias?",
        "Meu banco esta me cobrando muito? Quanto economizo trocando para um banco digital?",
        "Quais sao meus custos bancarios mensais?",
        "Faz sentido eu manter minha conta no banco atual?",
    ],
    "🤝 Negociacao Bancaria": [
        "Como negocio a isencao da minha anuidade de cartao?",
        "Meu banco esta me cobrando juros altos. Me da um script para falar com o gerente.",
        "Tenho poder de barganha com meu banco? Quero renegociar minhas tarifas.",
        "Quais argumentos usar para conseguir limite maior no cartao?",
    ],
    "📑 Fiscal MEI/PJ": [
        "Quanto vou pagar de DAS esse mes como MEI?",
        "Me da um relatorio das receitas e despesas do meu negocio em 2026.",
        "Qual meu faturamento PJ e o imposto estimado no Simples Nacional?",
        "Quais despesas PJ posso deduzir do imposto?",
        "Estou proximo do limite do MEI? Devo migrar para ME?",
    ],
    "👥 Comparacao com Pares": [
        "Minha renda e R$ 12.500. Estou gastando mais que a media em moradia?",
        "Comparado a pessoas com renda de R$ 12.500, como estou em alimentacao e lazer?",
        "Qual meu percentil de poupanca para quem ganha R$ 12.500 por mes?",
        "Estou gastando proporcional ao que ganho comparado a media brasileira?",
    ],
    "🔄 Eventos de Vida": [
        "Tive um filho recentemente. Como isso muda meu planejamento financeiro?",
        "Estou planejando me casar em 1 ano. Como devo me preparar financeiramente?",
        "Meu salario aumentou 30%. O que devo fazer com o dinheiro extra?",
        "Vou morar sozinho pela primeira vez. Como organizar meu orcamento?",
    ],
    "📱 Assinaturas e Recorrencias": [
        "Quais assinaturas estou pagando todo mes?",
        "Tenho alguma assinatura que nao estou usando ou duplicada?",
        "Quanto gasto por mes com assinaturas e servicos recorrentes?",
        "Posso economizar cancelando alguma assinatura sem perder qualidade de vida?",
    ],
    "📈 Previsao de Gastos": [
        "Quanto vou gastar no proximo mes se continuar nesse ritmo?",
        "Em qual categoria meus gastos mais cresceram nos ultimos meses?",
        "Quando vou ficar sem margem financeira se nao mudar nada?",
        "Qual e o meu burn rate atual?",
    ],
}

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Nexa Chat")

    if st.session_state.token:
        st.success(f"✓ {st.session_state.user_email}")
        if st.button("Sair", use_container_width=True):
            try:
                requests.post(f"{_base()}/api/v1/auth/logout", headers=_hdr(), timeout=5)
            except Exception:
                pass
            st.session_state.token = None
            st.session_state.user_id = None
            st.session_state.user_email = None
            st.session_state.messages = []
            st.session_state.session_id = str(uuid.uuid4())
            st.rerun()

        st.divider()
        st.caption("Perguntas rapidas por ferramenta")
        for categoria, perguntas in CENARIOS.items():
            with st.expander(categoria):
                for p in perguntas:
                    label = p[:55] + ("..." if len(p) > 55 else "")
                    if st.button(label, key=f"q_{p}"):
                        st.session_state["_pending"] = p
    else:
        DEMO_EMAIL = "mock.teste@nexa.com"
        DEMO_SENHA = "Mock@12345"

        def _do_login(email: str, senha: str):
            try:
                r = requests.post(
                    f"{_base()}/api/v1/auth/token",
                    data={"username": email, "password": senha},
                    timeout=10,
                )
                if r.status_code == 200:
                    d = r.json()
                    st.session_state.token = d["access_token"]
                    st.session_state.user_id = d["user_id"]
                    st.session_state.user_email = email
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "Credenciais invalidas"))
            except Exception as exc:
                st.error(str(exc))

        if st.button("Entrar como demo", use_container_width=True, type="primary"):
            _do_login(DEMO_EMAIL, DEMO_SENHA)

        st.caption(f"`{DEMO_EMAIL}` / `{DEMO_SENHA}`")
        st.divider()

        with st.expander("Outra conta"):
            with st.form("login"):
                email = st.text_input("E-mail")
                senha = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", use_container_width=True):
                    _do_login(email, senha)

# ─── Area principal ───────────────────────────────────────────────────────────
if not st.session_state.token:
    st.markdown("## Nexa — Testador de Inteligencia")
    st.info("Clique em **Entrar como demo** na barra lateral para comecar.")
    st.stop()

col1, col2 = st.columns([5, 1])
with col1:
    st.caption(f"Sessao `{st.session_state.session_id[:8]}...`")
with col2:
    if st.button("Nova sessao"):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("ms"):
            st.caption(f"⏱ {msg['ms']:.0f} ms")

pending = st.session_state.pop("_pending", None)
user_input = st.chat_input("Pergunte algo...")
texto = pending or user_input

if texto:
    st.session_state.messages.append({"role": "user", "content": texto})
    with st.chat_message("user"):
        st.markdown(texto)

    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            t0 = time.time()
            try:
                r = requests.post(
                    f"{_base()}/api/v1/chat/",
                    json={
                        "user_id": st.session_state.user_id,
                        "message": texto,
                        "session_id": st.session_state.session_id,
                    },
                    headers=_hdr(),
                    timeout=120,
                )
                ms = (time.time() - t0) * 1000
                if r.status_code == 200:
                    resposta = r.json().get("response", "(sem resposta)")
                else:
                    resposta = f"Erro {r.status_code}: {r.json().get('detail', r.text)}"
            except Exception as exc:
                ms = (time.time() - t0) * 1000
                resposta = f"Erro de conexao: {exc}"

        st.markdown(resposta)
        st.caption(f"⏱ {ms:.0f} ms")

    st.session_state.messages.append({"role": "assistant", "content": resposta, "ms": ms})
    st.rerun()
