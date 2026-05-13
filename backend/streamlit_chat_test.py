"""
streamlit_chat_test.py — Testador de Chat do Agente Nexa

Testa o endpoint POST /api/v1/chat/ com todos os 14 cenarios de ferramentas.
Inclui contas mock pre-configuradas com perfil financeiro realista.

Uso:
    cd backend && streamlit run streamlit_chat_test.py
"""
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
    "active_persona": None,
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


def _do_login(email: str, password: str, persona_key: str) -> None:
    try:
        r = requests.post(
            f"{_base()}/api/v1/auth/token",
            data={"username": email, "password": password},
            timeout=10,
        )
        if r.status_code == 200:
            d = r.json()
            st.session_state.token = d["access_token"]
            st.session_state.user_id = d["user_id"]
            st.session_state.user_email = email
            st.session_state.active_persona = persona_key
            st.session_state.chat_messages = []
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.last_raw = None
            st.rerun()
        else:
            st.error(r.json().get("detail", r.text))
    except Exception as exc:
        st.error(str(exc))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PERSONAS MOCK — perfis financeiros realistas
# Baseados em seed_rich_mock_account.py e seed_golden_user.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PERSONAS = {
    "rich": {
        "label": "Conta Rica (CLT + PJ)",
        "email": "mock.teste@nexa.com",
        "password": "Mock@12345",
        "seed_script": "scripts/seed/seed_rich_mock_account.py",
        "profile": {
            "nome": "Conta Mock Nexa",
            "renda_pf": 12_500.0,
            "renda_pj": 9_200.0,
            "historico_meses": 16,
            "health_score": "Crescente (58 → 79)",
            "cluster": "INVESTIDOR_CAUTELOSO / MICROEMPREENDEDOR",
            "moradia": 2_800.0,
            "assinaturas": ["Netflix R$ 55,90", "Spotify R$ 21,90", "Notion R$ 79", "Google Workspace R$ 120"],
            "parcelamentos": [
                "Celular Pro Max 12x R$ 649,90",
                "Curso Especializacao 10x R$ 420",
                "Cadeira Ergonomica 8x R$ 290",
            ],
            "pj_despesas": ["Meta Ads ~R$ 230/mes", "Contabilidade ~R$ 425/mes", "Suprimentos ~R$ 107/mes"],
            "notas": "16 meses de historico. PJ ativo com receitas variaveis (~R$ 300-2.200 extras).",
        },
    },
    "demo": {
        "label": "Demo Golden User",
        "email": "demo@nexa.com",
        "password": "demo123",
        "seed_script": "scripts/seed/seed_golden_user.py",
        "profile": {
            "nome": "Usuario Master Demo",
            "renda_pf": 12_500.0,
            "renda_pj": 0.0,
            "historico_meses": 12,
            "health_score": "Bom",
            "cluster": "FAMILIA_ESTRUTURADA",
            "moradia": 2_500.0,
            "assinaturas": ["Netflix", "Spotify"],
            "parcelamentos": ["Sem parcelamentos recorrentes"],
            "pj_despesas": [],
            "notas": "12 meses de dados. Perfil PF puro, sem atividade PJ.",
        },
    },
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CENARIOS DAS 14 FERRAMENTAS — mensagens contextualizadas por persona
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOLS = {
    "rich": [
        {
            "id": "get_user_profile_context",
            "icon": "🧠",
            "label": "Perfil do usuario",
            "msgs": [
                "Qual e meu perfil financeiro? Tenho salario de R$ 12.500 e rendo mais R$ 9.200 como PJ.",
                "Como voce me ve financeiramente? Quais sao meus pontos fortes e fracos?",
                "Tive um aumento de renda PJ recente. Isso muda meu perfil de risco?",
            ],
        },
        {
            "id": "get_financial_forecast",
            "icon": "📊",
            "label": "Forecast financeiro",
            "msgs": [
                "Como estao minhas financas este mes? Tenho aluguel de R$ 2.800 e varios parcelamentos.",
                "Quanto posso gastar com seguranca essa semana considerando minha renda total de R$ 21.700?",
                "Meu health score esta evoluindo? Comecei em 58 e quero saber onde estou agora.",
            ],
        },
        {
            "id": "get_budget_advice",
            "icon": "📋",
            "label": "Orcamento 50/30/20",
            "msgs": [
                "Com renda total de R$ 21.700 (PF + PJ), como devo dividir meu orcamento 50/30/20?",
                "Estou gastando R$ 2.800 de aluguel mais R$ 360 de energia e R$ 140 de internet. Isso e muito?",
                "Minhas assinaturas somam quase R$ 280/mes entre PF e PJ. Onde cortar sem perder produtividade?",
            ],
        },
        {
            "id": "get_card_optimization",
            "icon": "💳",
            "label": "Cartao de credito",
            "msgs": [
                "Ganho R$ 12.500 de CLT e mais R$ 9.200 de PJ. Qual cartao premium vale a anuidade?",
                "Gasto bastante em combustivel, supermercado e restaurante. Qual cartao me da mais cashback nessas categorias?",
                "Vale a pena ter um cartao PJ separado para as despesas da empresa como Meta Ads e Contabilidade?",
            ],
        },
        {
            "id": "get_spending_alerts",
            "icon": "🔔",
            "label": "Alertas de gastos",
            "msgs": [
                "Tem alguma anomalia nos meus gastos? Gasto bastante com iFood e restaurantes.",
                "Meus gastos com marketing (Meta Ads ~R$ 230/mes) estao dentro do normal para um PJ da minha receita?",
                "Algum gasto recorrente que eu deveria revisar? Tenho 3 parcelamentos ativos alem das assinaturas.",
            ],
        },
        {
            "id": "get_goals_summary",
            "icon": "🎯",
            "label": "Metas financeiras",
            "msgs": [
                "Quero juntar R$ 80.000 de entrada para um apartamento. Com minha renda de R$ 21.700, em quanto tempo consigo?",
                "Se eu poupar R$ 3.000/mes da renda PJ, quando atinjo uma reserva de emergencia de 6 meses?",
                "Como estao minhas metas? Tenho meta de comprar imovel e tambem de reduzir custos PJ.",
            ],
        },
        {
            "id": "get_financing_simulation",
            "icon": "🏠",
            "label": "Simulacao de financiamento",
            "msgs": [
                "Quero comprar um apartamento de R$ 500.000 com R$ 80.000 de entrada. Tenho renda de R$ 21.700. Vale financiar?",
                "Pago R$ 2.800 de aluguel hoje. Se financiar um ape pelo mesmo valor de parcela, o que compro?",
                "Quero um carro de R$ 80.000 para substituir meus gastos com Uber. CDC ou consorcio?",
            ],
        },
        {
            "id": "get_timing_scenarios",
            "icon": "⏰",
            "label": "Cenarios de timing",
            "msgs": [
                "Se eu guardar R$ 3.000/mes por 8 meses, quanto ganho de entrada no apartamento de R$ 500.000?",
                "Compro o carro de R$ 80.000 agora com R$ 20.000 de entrada ou espero 6 meses para ter R$ 38.000?",
                "Vale adiar a compra do apartamento por 12 meses para aumentar minha entrada de R$ 80k para R$ 110k?",
            ],
        },
        {
            "id": "get_leverage_simulation",
            "icon": "🏗️",
            "label": "Alavancagem imobiliaria",
            "msgs": [
                "Pago R$ 2.800 de aluguel. Consigo usar esse valor para pagar parcela de consorcio imobiliario?",
                "Com renda de R$ 21.700, posso fazer um consorcio maior e usar o surplus investido para pagar as parcelas?",
                "Me simula consorcio de um ape de 90m2 no Savassi em BH: o aluguel que receberia paga as parcelas?",
            ],
        },
        {
            "id": "get_fiscal_report",
            "icon": "📑",
            "label": "Relatorio fiscal MEI/PJ",
            "msgs": [
                "Tenho faturamento PJ de R$ 9.200/mes. Pago contabilidade R$ 425 e impostos estimados. Me da o relatorio fiscal.",
                "Meu faturamento PJ em 2026 foi de aproximadamente R$ 9.200/mes. Qual meu DAS ou Simples estimado?",
                "Quais despesas PJ posso deduzir? Tenho Notion R$ 79, Google Workspace R$ 120, Meta Ads ~R$ 230 e Contabilidade R$ 425.",
            ],
        },
        {
            "id": "get_peer_comparison",
            "icon": "👥",
            "label": "Comparacao com pares",
            "msgs": [
                "Com renda PF de R$ 12.500, estou gastando R$ 2.800 de aluguel (22% da renda). E muito para minha faixa?",
                "Comparado a profissionais autonomos com faturamento PJ de R$ 9.200, meus custos operacionais sao normais?",
                "Em qual percentil de poupanca estou para quem tem renda combinada PF+PJ acima de R$ 20.000?",
            ],
        },
        {
            "id": "get_purchase_recommendation",
            "icon": "🛒",
            "label": "Compra inteligente",
            "msgs": [
                "Quero trocar meu notebook por um de R$ 8.500. Vale parcelar em 12x no cartao ou pagar no PIX e perder liquidez?",
                "Preciso de uma camera profissional de R$ 6.000 para meu trabalho PJ. CDC, parcelado ou consorcio de eletronicos?",
                "Vou comprar uma mesa de escritorio de R$ 2.200. Parcelo em 10x (R$ 220/mes) ou pago a vista com cashback?",
            ],
        },
        {
            "id": "get_bank_cost_analysis",
            "icon": "🏦",
            "label": "Custos bancarios",
            "msgs": [
                "Tenho conta PF e conta PJ separadas. Quanto estou pagando de tarifas bancarias no total?",
                "Minhas contas bancarias valem a pena? Analisa se um banco digital seria mais barato para meu perfil CLT+PJ.",
                "Quanto economizo por ano se migrar minha conta PJ para um banco digital que nao cobra mensalidade?",
            ],
        },
        {
            "id": "get_negotiation_script",
            "icon": "🤝",
            "label": "Negociador bancario",
            "msgs": [
                "Pago Google Workspace R$ 120/mes. Como negocio desconto ou migro para alternativa sem perder funcionalidade?",
                "Tenho relacionamento bancario com renda de R$ 21.700. Me da script para renegociar tarifas e pedir cartao sem anuidade.",
                "Minha contabilidade custa R$ 425/mes. Vale renegociar ou trocar de contador? Me da um roteiro.",
            ],
        },
    ],
    "demo": [
        {
            "id": "get_user_profile_context",
            "icon": "🧠",
            "label": "Perfil do usuario",
            "msgs": [
                "Qual e meu perfil financeiro atual?",
                "Como voce me classifica financeiramente?",
                "Tenho algum evento de vida recente relevante para meu planejamento?",
            ],
        },
        {
            "id": "get_financial_forecast",
            "icon": "📊",
            "label": "Forecast financeiro",
            "msgs": [
                "Como estao minhas financas este mes? Tenho salario de R$ 12.500.",
                "Quanto posso gastar com seguranca essa semana?",
                "Qual minha saude financeira atual?",
            ],
        },
        {
            "id": "get_budget_advice",
            "icon": "📋",
            "label": "Orcamento 50/30/20",
            "msgs": [
                "Com salario de R$ 12.500, como organizo meu orcamento 50/30/20?",
                "Gasto R$ 2.500 de aluguel (20% da renda). Estou dentro do ideal?",
                "Me ajuda a distribuir meu salario entre necessidades, lazer e investimentos.",
            ],
        },
        {
            "id": "get_card_optimization",
            "icon": "💳",
            "label": "Cartao de credito",
            "msgs": [
                "Ganho R$ 12.500. Qual cartao premium vale a pena para o meu perfil?",
                "Qual cartao me da mais beneficios em moradia, alimentacao e saude?",
                "Vale pagar anuidade de cartao black para quem ganha R$ 12.500?",
            ],
        },
        {
            "id": "get_spending_alerts",
            "icon": "🔔",
            "label": "Alertas de gastos",
            "msgs": [
                "Tem algum alerta ou anomalia nos meus gastos?",
                "Estou gastando demais em alguma categoria?",
                "O que devo monitorar nas minhas financas agora?",
            ],
        },
        {
            "id": "get_goals_summary",
            "icon": "🎯",
            "label": "Metas financeiras",
            "msgs": [
                "Como estao minhas metas financeiras?",
                "Quero juntar R$ 60.000 de entrada para imovel. Com R$ 12.500 de salario, em quanto tempo?",
                "Quanto preciso poupar por mes para ter uma reserva de emergencia de 6 meses?",
            ],
        },
        {
            "id": "get_financing_simulation",
            "icon": "🏠",
            "label": "Simulacao de financiamento",
            "msgs": [
                "Quero comprar um apartamento de R$ 400.000. Tenho R$ 60.000 de entrada e renda de R$ 12.500.",
                "Pago R$ 2.500 de aluguel. Vale financiar um imovel pela mesma parcela?",
                "Carro de R$ 60.000: financio, poupo ou faco consorcio?",
            ],
        },
        {
            "id": "get_timing_scenarios",
            "icon": "⏰",
            "label": "Cenarios de timing",
            "msgs": [
                "Vale esperar 12 meses guardando R$ 2.000/mes para aumentar minha entrada de R$ 60k para R$ 84k?",
                "Compro o carro de R$ 60.000 agora ou espero 6 meses para ter mais entrada?",
                "Se eu poupar R$ 1.500/mes, em quanto tempo junto R$ 60.000?",
            ],
        },
        {
            "id": "get_leverage_simulation",
            "icon": "🏗️",
            "label": "Alavancagem imobiliaria",
            "msgs": [
                "Pago R$ 2.500 de aluguel. Posso usar esse valor para pagar consorcio imobiliario?",
                "Me simula consorcio de um ape de 70m2 no Buritis em BH: o aluguel que receberia cobre as parcelas?",
                "Vale fazer consorcio maior e investir o surplus do aluguel?",
            ],
        },
        {
            "id": "get_fiscal_report",
            "icon": "📑",
            "label": "Relatorio fiscal MEI/PJ",
            "msgs": [
                "Sou CLT mas estou pensando em abrir MEI. Como ficam meus impostos?",
                "Se eu abrir um MEI para prestacao de servicos, quanto vou pagar de DAS?",
                "Qual e a diferenca de carga tributaria entre CLT e MEI para renda de R$ 12.500?",
            ],
        },
        {
            "id": "get_peer_comparison",
            "icon": "👥",
            "label": "Comparacao com pares",
            "msgs": [
                "Com salario de R$ 12.500, estou gastando R$ 2.500 de aluguel. E muito para minha faixa?",
                "Comparado a outras familias com renda de R$ 12.000, como estao meus gastos em alimentacao e lazer?",
                "Em qual percentil de poupanca estou para quem ganha R$ 12.500?",
            ],
        },
        {
            "id": "get_purchase_recommendation",
            "icon": "🛒",
            "label": "Compra inteligente",
            "msgs": [
                "Quero comprar uma TV de R$ 4.500. Parcelo em 10x ou pago no PIX com desconto?",
                "Notebook de R$ 6.000: parcelo em 12x no cartao ou pago a vista e invisto a diferenca?",
                "Vou comprar uma moto de R$ 15.000. CDC, parcelado no cartao ou consorcio?",
            ],
        },
        {
            "id": "get_bank_cost_analysis",
            "icon": "🏦",
            "label": "Custos bancarios",
            "msgs": [
                "Quanto estou pagando de tarifas bancarias por mes?",
                "Meu banco e caro para o meu perfil? Vale trocar para banco digital?",
                "Quanto economizo por ano migrando para um banco digital sem tarifas?",
            ],
        },
        {
            "id": "get_negotiation_script",
            "icon": "🤝",
            "label": "Negociador bancario",
            "msgs": [
                "Como negocio a isencao da anuidade do meu cartao de credito?",
                "Tenho renda de R$ 12.500 e sou bom pagador. Me da script para renegociar tarifas.",
                "Meu banco cobra R$ 35/mes de manutencao. Como argumento para zerar ou trocar?",
            ],
        },
    ],
}

# fallback — cenarios genericos usados quando nao ha persona ativa
TOOLS_GENERIC = TOOLS["rich"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SIDEBAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with st.sidebar:
    st.title("Nexa Chat Tester")

    # Backend
    col_url, col_ping = st.columns([3, 1])
    _api = col_url.text_input("URL do backend", value=st.session_state.api_url, label_visibility="collapsed")
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
        persona = PERSONAS.get(st.session_state.active_persona or "")
        label = persona["label"] if persona else st.session_state.user_email
        st.success(f"Logado: {label}")
        st.caption(f"`{st.session_state.user_id}`")
        if st.button("Logout", use_container_width=True):
            try:
                requests.post(f"{_base()}/api/v1/auth/logout", headers=_hdr(), timeout=5)
            except Exception:
                pass
            for k in ("token", "user_id", "user_email", "active_persona", "chat_messages", "last_raw"):
                st.session_state[k] = None if k != "chat_messages" else []
            st.session_state.session_id = str(uuid.uuid4())
            st.rerun()

        # Card do perfil mock
        if persona:
            p = persona["profile"]
            with st.expander("Perfil do cenario ativo", expanded=True):
                renda_total = p["renda_pf"] + p["renda_pj"]
                st.markdown(f"**{p['nome']}**")
                st.markdown(f"Renda PF: `R$ {p['renda_pf']:,.0f}/mes`")
                if p["renda_pj"] > 0:
                    st.markdown(f"Renda PJ: `R$ {p['renda_pj']:,.0f}/mes`")
                    st.markdown(f"Renda total: `R$ {renda_total:,.0f}/mes`")
                st.markdown(f"Moradia: `R$ {p['moradia']:,.0f}/mes`")
                st.markdown(f"Historico: `{p['historico_meses']} meses`")
                st.markdown(f"Health Score: `{p['health_score']}`")
                st.markdown(f"Cluster: `{p['cluster']}`")
                if p["assinaturas"]:
                    st.caption("Assinaturas: " + " • ".join(p["assinaturas"]))
                if p["parcelamentos"]:
                    st.caption("Parcelamentos: " + " | ".join(p["parcelamentos"]))
                if p["pj_despesas"]:
                    st.caption("Despesas PJ: " + " • ".join(p["pj_despesas"]))
                if p["notas"]:
                    st.caption(p["notas"])
    else:
        tab_mock, tab_login, tab_reg = st.tabs(["Contas de teste", "Login", "Registro"])

        with tab_mock:
            st.caption("Usuarios pre-configurados com dados mock realistas.")
            for key, persona in PERSONAS.items():
                p = persona["profile"]
                renda_str = f"R$ {p['renda_pf']:,.0f}"
                if p["renda_pj"] > 0:
                    renda_str += f" + R$ {p['renda_pj']:,.0f} PJ"
                st.markdown(f"**{persona['label']}**")
                st.caption(f"Renda: {renda_str} | {p['historico_meses']} meses de historico")
                if st.button(f"Entrar como '{persona['label']}'", key=f"mock_login_{key}", use_container_width=True):
                    _do_login(persona["email"], persona["password"], key)
                st.caption(f"`{persona['email']}` / `{persona['password']}`")
                st.divider()

        with tab_login:
            le = st.text_input("E-mail", key="le")
            lp = st.text_input("Senha", type="password", key="lp")
            if st.button("Entrar", use_container_width=True):
                _do_login(le, lp, None)

        with tab_reg:
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
    active_persona = st.session_state.active_persona or "rich"
    tools = TOOLS.get(active_persona, TOOLS_GENERIC)

    st.subheader("Cenarios de teste")
    st.caption("Clique para enviar ao chat.")

    for tool in tools:
        with st.expander(f"{tool['icon']} {tool['label']}"):
            for msg in tool["msgs"]:
                label = msg[:60] + ("..." if len(msg) > 60 else "")
                if st.button(label, key=f"sc_{tool['id']}_{active_persona}_{msg[:12]}"):
                    st.session_state["_pending"] = msg

    st.divider()
    st.caption("Chat Tester v2.0 — 14 ferramentas | 2 personas mock")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AREA PRINCIPAL
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
    st.session_state.show_debug = c3.toggle("Debug JSON", value=st.session_state.show_debug)

if not st.session_state.token:
    st.info("Faca login ou escolha uma conta de teste na barra lateral.")

    # Preview das personas disponíveis
    st.subheader("Cenarios mock disponiveis")
    cols = st.columns(len(PERSONAS))
    for col, (key, persona) in zip(cols, PERSONAS.items()):
        with col:
            p = persona["profile"]
            st.markdown(f"**{persona['label']}**")
            st.markdown(f"- Renda PF: R$ {p['renda_pf']:,.0f}/mes")
            if p["renda_pj"] > 0:
                st.markdown(f"- Renda PJ: R$ {p['renda_pj']:,.0f}/mes")
            st.markdown(f"- Moradia: R$ {p['moradia']:,.0f}/mes")
            st.markdown(f"- Historico: {p['historico_meses']} meses")
            st.markdown(f"- Health Score: {p['health_score']}")
            st.markdown(f"- Cluster: {p['cluster']}")
            if p["assinaturas"]:
                st.markdown("- Assinaturas: " + ", ".join(p["assinaturas"]))
            if p["parcelamentos"] and p["parcelamentos"] != ["Sem parcelamentos recorrentes"]:
                st.markdown("- Parcelamentos: " + ", ".join(p["parcelamentos"]))
            st.caption(p["notas"])
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
