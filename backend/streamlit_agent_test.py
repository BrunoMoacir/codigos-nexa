"""
streamlit_agent_test.py — Teste Completo do Agente + Endpoints Diretos Nexa

Como usar:
    # Terminal 1: subir o backend
    cd backend && uvicorn app.main:app --reload

    # Terminal 2: subir o Streamlit
    cd backend && streamlit run streamlit_agent_test.py

Abas:
    - Chat do Agente: testa as 8 ferramentas via chat (HTTP ou Direto)
    - Endpoints Diretos: chama REST endpoints que nao passam pelo agente
"""

import time
import requests
import streamlit as st

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.set_page_config(
    page_title="Nexa Agent — Teste Completo",
    page_icon="🤖",
    layout="wide",
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CENÁRIOS DE TESTE — um por tool
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOOL_SCENARIOS = {
    "1. get_financial_forecast": {
        "icon": "📊",
        "descricao": "Resumo financeiro, safe-to-spend, health score",
        "mensagens": [
            "Como estão minhas finanças este mês?",
            "Quanto posso gastar hoje com segurança?",
            "Qual minha saúde financeira atual?",
        ],
    },
    "2. get_budget_advice": {
        "icon": "📋",
        "descricao": "Plano 50/30/20, análise de gastos por categoria",
        "mensagens": [
            "Minha renda é R$ 8.500. Como devo organizar meu orçamento?",
            "Estou gastando bem para quem ganha R$ 6.000 por mês?",
            "Me explica a regra 50/30/20 para uma renda de R$ 10.000.",
        ],
    },
    "3. get_card_optimization": {
        "icon": "💳",
        "descricao": "Melhor cartão de crédito para o perfil",
        "mensagens": [
            "Minha renda é R$ 8.500. Qual cartão de crédito devo pedir?",
            "Vale a pena pagar anuidade de cartão premium para quem ganha R$ 15.000?",
            "Quero maximizar minhas milhas. Qual cartão me indica?",
        ],
    },
    "4. get_spending_alerts": {
        "icon": "🔔",
        "descricao": "Alertas ativos, anomalias, notificações proativas",
        "mensagens": [
            "Tem algum alerta nas minhas finanças?",
            "Algum gasto estranho ou anormal este mês?",
            "O que devo me preocupar financeiramente agora?",
        ],
    },
    "5. get_goals_summary": {
        "icon": "🎯",
        "descricao": "Metas financeiras e progresso",
        "mensagens": [
            "Como estão minhas metas financeiras?",
            "Quanto falta para minha reserva de emergência?",
            "Consigo poupar R$ 700 por mês. Quando vou atingir minhas metas?",
        ],
    },
    "6. get_financing_simulation": {
        "icon": "🏠",
        "descricao": "Simula financiamento vs. poupança vs. consórcio (F3)",
        "mensagens": [
            "Quero comprar um carro de R$ 60.000. Vale a pena financiar ou poupar?",
            "Estou pensando em comprar um apartamento de R$ 400.000 com R$ 80.000 de entrada. O que fazer?",
            "Quero reformar minha casa por R$ 25.000. Financiamento ou consórcio?",
        ],
    },
    "7. get_fiscal_report": {
        "icon": "📑",
        "descricao": "Relatório fiscal PJ/MEI com DAS estimado (F4)",
        "mensagens": [
            "Quanto vou pagar de DAS esse mês como MEI?",
            "Me dá um relatório das receitas e despesas do meu negócio de 2026.",
            "Qual meu faturamento PJ e o imposto estimado no Simples Nacional?",
        ],
    },
    "8. get_peer_comparison": {
        "icon": "👥",
        "descricao": "Compara gastos com benchmarks IBGE/POF (MX.4)",
        "mensagens": [
            "Minha renda é R$ 8.000. Estou gastando mais que a média em moradia?",
            "Comparado a pessoas com renda de R$ 5.000, como estou em alimentação e lazer?",
            "Qual meu percentil de poupança para quem ganha R$ 12.000 por mês?",
        ],
    },
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÕES DE CHAMADA AO AGENTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def call_agent_http(user_id: str, message: str, api_url: str) -> tuple[str, float]:
    """Chama o agente via HTTP POST /chat/. Retorna (resposta, latencia_ms)."""
    t0 = time.time()
    try:
        resp = requests.post(
            f"{api_url}/api/v1/chat/",
            json={"user_id": user_id, "message": message},
            timeout=120,
        )
        latency = (time.time() - t0) * 1000
        if resp.status_code == 200:
            return resp.json().get("response", "(sem resposta)"), latency
        return f"Erro HTTP {resp.status_code}: {resp.text[:300]}", latency
    except requests.exceptions.ConnectionError:
        return (
            "Nao foi possivel conectar ao backend. "
            "Verifique se o servidor esta rodando em " + api_url,
            (time.time() - t0) * 1000,
        )
    except Exception as e:
        return f"Erro inesperado: {e}", (time.time() - t0) * 1000


def call_agent_direct(user_id: str, message: str) -> tuple[str, float]:
    """Chama o agente diretamente via Python (sem servidor HTTP)."""
    t0 = time.time()
    try:
        from app.agent.graph import build_financial_agent
        from langchain_core.messages import HumanMessage

        agent = build_financial_agent()
        result = agent.invoke(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": user_id}},
        )
        latency = (time.time() - t0) * 1000
        return result["messages"][-1].content, latency
    except Exception as e:
        return f"Erro ao chamar agente diretamente: {e}", (time.time() - t0) * 1000


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER — inferir tool chamada pela resposta
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _infer_tool(response: str) -> str:
    """Heuristica simples para inferir qual tool gerou a resposta."""
    r = response.lower()
    if any(k in r for k in ["simulacao de aquisicao", "financiamento bancario", "consorcio", "npv"]):
        return "tool: get_financing_simulation"
    if any(k in r for k in ["relatorio fiscal", "das estimado", "simples nacional", "receita de servico"]):
        return "tool: get_fiscal_report"
    if any(k in r for k in ["comparacao com pares", "benchmarks ibge", "faixa de renda", "percentil de poupanca"]):
        return "tool: get_peer_comparison"
    if any(k in r for k in ["plano de orcamento", "50/30/20", "essenciais", "desejos"]):
        return "tool: get_budget_advice"
    if any(k in r for k in ["card vencedor", "lucro liquido anual", "anuidade efetiva", "otimizacao"]):
        return "tool: get_card_optimization"
    if any(k in r for k in ["alertas", "anomalia", "notificacoes proativas", "burn rate", "assinatura"]):
        return "tool: get_spending_alerts"
    if any(k in r for k in ["metas financeiras", "reserva de emergencia", "progresso"]):
        return "tool: get_goals_summary"
    if any(k in r for k in ["diagnostico financeiro", "margem disponivel", "health score", "safe-to-spend"]):
        return "tool: get_financial_forecast"
    return ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ESTADO DA SESSÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if "messages" not in st.session_state:
    st.session_state.messages = []      # lista de {role, content, latency_ms, tool_hint}
if "total_calls" not in st.session_state:
    st.session_state.total_calls = 0
if "total_errors" not in st.session_state:
    st.session_state.total_errors = 0

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SIDEBAR — Configuração e cenários de teste
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with st.sidebar:
    st.title("Nexa Agent Test")
    st.caption("Testador completo das 8 ferramentas")

    st.divider()

    # Configurações
    st.subheader("Configuração")

    modo = st.radio(
        "Modo de chamada",
        ["HTTP (servidor FastAPI)", "Direto (Python)"],
        help=(
            "HTTP: requer uvicorn rodando. "
            "Direto: importa o agente Python, nao precisa de servidor."
        ),
    )

    api_url = "http://localhost:8000"
    if modo == "HTTP (servidor FastAPI)":
        api_url = st.text_input("URL do backend", value="http://localhost:8000")
        # Verificar saude do servidor
        if st.button("Verificar conexao"):
            try:
                r = requests.get(f"{api_url}/health", timeout=3)
                st.success(f"Backend OK ({r.status_code})")
            except Exception:
                try:
                    r = requests.get(f"{api_url}/docs", timeout=3)
                    st.success("Backend acessivel (Swagger OK)")
                except Exception:
                    st.error("Backend nao encontrado. Suba o servidor primeiro.")

    user_id = st.text_input("user_id de teste", value="test_user_nexa")

    st.divider()

    # Estatísticas
    st.subheader("Estatisticas da sessao")
    col1, col2 = st.columns(2)
    col1.metric("Chamadas", st.session_state.total_calls)
    col2.metric("Erros", st.session_state.total_errors)

    if st.button("Limpar conversa"):
        st.session_state.messages = []
        st.session_state.total_calls = 0
        st.session_state.total_errors = 0
        st.rerun()

    st.divider()

    # Cenários de teste por tool
    st.subheader("Cenarios de Teste")
    st.caption("Clique em uma mensagem para enviar ao agente")

    for tool_name, config in TOOL_SCENARIOS.items():
        with st.expander(f"{config['icon']} {tool_name}"):
            st.caption(config["descricao"])
            for msg in config["mensagens"]:
                if st.button(msg[:60] + ("..." if len(msg) > 60 else ""), key=f"btn_{tool_name}_{msg[:20]}"):
                    st.session_state["pending_message"] = msg

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ÁREA PRINCIPAL — Abas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.title("Nexa — Testador Completo")

tab_agent, tab_direct = st.tabs(["Chat do Agente (8 tools)", "Endpoints Diretos (REST)"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 1 — Chat do Agente
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab_agent:
    st.caption(
        f"Modo: **{modo}** | user_id: `{user_id}` | 8 ferramentas disponiveis"
    )

    # Exibir histórico de mensagens
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("latency_ms"):
                meta = f"⏱ {msg['latency_ms']:.0f}ms"
                if msg.get("tool_hint"):
                    meta += f" | {msg['tool_hint']}"
                st.caption(meta)

    # Processar mensagem pendente (clicada no sidebar)
    pending = st.session_state.pop("pending_message", None)

    # Input manual
    user_input = st.chat_input("Digite sua mensagem ou clique em um cenario no menu lateral...")

    # Determinar mensagem a enviar
    message_to_send = pending or (user_input if user_input else None)

    if message_to_send:
        st.session_state.messages.append({"role": "user", "content": message_to_send})
        with st.chat_message("user"):
            st.markdown(message_to_send)

        with st.chat_message("assistant"):
            with st.spinner("Nexa pensando..."):
                if modo == "HTTP (servidor FastAPI)":
                    response, latency = call_agent_http(user_id, message_to_send, api_url)
                else:
                    response, latency = call_agent_direct(user_id, message_to_send)

            st.markdown(response)
            tool_hint = _infer_tool(response)
            st.caption(f"⏱ {latency:.0f}ms{' | ' + tool_hint if tool_hint else ''}")

        st.session_state.total_calls += 1
        is_error = any(
            kw in response.lower()
            for kw in ["erro", "nao foi possivel", "error", "exception", "traceback"]
        )
        if is_error:
            st.session_state.total_errors += 1

        st.session_state.messages.append({
            "role": "assistant",
            "content": response,
            "latency_ms": latency,
            "tool_hint": tool_hint,
        })
        st.rerun()

    with st.expander("Status das 8 Ferramentas", expanded=False):
        st.markdown("""
| # | Tool | Feature | Modulo Principal |
|---|------|---------|-----------------|
| 1 | `get_financial_forecast` | F1 — NexaRunner | `app/runner.py` |
| 2 | `get_budget_advice` | M1.3 — BudgetAdvisor | `app/cashflow/budget_advisor.py` |
| 3 | `get_card_optimization` | F2 — OptimizerService | `app/optimizer/` |
| 4 | `get_spending_alerts` | MX.3 — ProactiveNotifier | `app/notifications/notifier.py` |
| 5 | `get_goals_summary` | MX.2 — GoalTracker | `app/goals/tracker.py` |
| 6 | `get_financing_simulation` | F3 — ArchitectService + M3.3 | `app/architect/` |
| 7 | `get_fiscal_report` | F4/M4.1 — FiscalReportService | `app/etl/fiscal_report.py` |
| 8 | `get_peer_comparison` | MX.4 — PeerComparator | `app/peers/peer_comparison.py` |
""")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 2 — Endpoints Diretos
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _call(method: str, path: str, **kwargs) -> tuple[dict | list | str, float, int]:
    """Faz uma chamada HTTP ao backend. Retorna (body, latencia_ms, status_code)."""
    t0 = time.time()
    try:
        url = f"{api_url}/api/v1{path}"
        r = getattr(requests, method)(url, timeout=30, **kwargs)
        latency = (time.time() - t0) * 1000
        try:
            return r.json(), latency, r.status_code
        except Exception:
            return r.text, latency, r.status_code
    except requests.exceptions.ConnectionError:
        return {"error": f"Backend nao encontrado em {api_url}"}, (time.time() - t0) * 1000, 0
    except Exception as exc:
        return {"error": str(exc)}, (time.time() - t0) * 1000, 0


def _show_result(body, latency: float, status_code: int) -> None:
    color = "green" if 200 <= status_code < 300 else "red"
    st.markdown(f"**Status:** :{color}[{status_code}] | ⏱ {latency:.0f}ms")
    st.json(body)


with tab_direct:
    st.caption(
        "Chamadas HTTP diretas aos endpoints REST — nao passam pelo agente. "
        f"Backend: `{api_url}`"
    )

    # ── MX.1 — Health Score History ──────────────────────────────────
    st.subheader("MX.1 — Health Score History")
    st.code("GET /api/v1/health-score/history/{user_id}?months=N")
    col1, col2 = st.columns([2, 1])
    hs_uid = col1.text_input("user_id", value=user_id, key="hs_uid")
    hs_months = col2.number_input("months", value=6, min_value=1, max_value=24, key="hs_months")
    if st.button("Buscar historico de health score", key="btn_hs"):
        body, lat, sc = _call("get", f"/health-score/history/{hs_uid}", params={"months": hs_months})
        _show_result(body, lat, sc)

    st.divider()

    # ── F3 — Simulacao de Financiamento ──────────────────────────────
    st.subheader("F3 — Simulate (Financiamento / Consorcio / Poupar)")
    st.code("POST /api/v1/architect/simulate")
    with st.form("form_architect"):
        c1, c2 = st.columns(2)
        arc_uid = c1.text_input("user_id", value=user_id)
        arc_amount = c2.number_input("target_amount (R$)", value=60000.0, step=1000.0)
        c3, c4 = st.columns(2)
        arc_down = c3.number_input("down_payment (R$)", value=10000.0, step=1000.0)
        arc_budget = c4.number_input("max_monthly_budget (R$)", value=2000.0, step=100.0)
        c5, c6 = st.columns(2)
        arc_months = c5.number_input("financing_months", value=48, min_value=6, max_value=360)
        arc_asset = c6.selectbox("asset_type", ["VEICULO", "IMOVEL", "REFORMA", "OUTRO"])
        arc_consortium = st.checkbox("include_consortium", value=True)
        arc_rental = st.number_input(
            "expected_rental_income (R$/mes) — opcional, so para IMOVEL",
            value=0.0, step=100.0, min_value=0.0,
            help="Se informado e asset_type=IMOVEL, ativa o plano de alavancagem por aluguel.",
        )
        submitted_arc = st.form_submit_button("Simular")
    if submitted_arc:
        payload = {
            "user_id": arc_uid,
            "target_amount": arc_amount,
            "down_payment": arc_down,
            "max_monthly_budget": arc_budget,
            "financing_months": arc_months,
            "asset_type": arc_asset,
            "include_consortium": arc_consortium,
        }
        if arc_rental > 0 and arc_asset == "IMOVEL":
            payload["expected_rental_income"] = arc_rental
        body, lat, sc = _call("post", "/architect/simulate", json=payload)
        _show_result(body, lat, sc)

    st.divider()

    # ── F3 — Historico de Simulacoes ─────────────────────────────────
    st.subheader("F3 — Historico de Simulacoes")
    st.code("GET /api/v1/architect/simulations?user_id=X&limit=N&asset_type=T")
    c1, c2, c3 = st.columns(3)
    hist_uid = c1.text_input("user_id", value=user_id, key="hist_uid")
    hist_limit = c2.number_input("limit", value=10, min_value=1, max_value=100, key="hist_limit")
    hist_asset = c3.selectbox(
        "asset_type (vazio = todos)", ["", "IMOVEL", "VEICULO", "REFORMA", "VIAGEM", "OUTRO"],
        key="hist_asset",
    )
    if st.button("Buscar historico", key="btn_hist"):
        params: dict = {"user_id": hist_uid, "limit": hist_limit}
        if hist_asset:
            params["asset_type"] = hist_asset
        body, lat, sc = _call("get", "/architect/simulations", params=params)
        _show_result(body, lat, sc)

    st.divider()

    # ── F3 — Sensitivity Analysis ────────────────────────────────────
    st.subheader("F3 — Sensitivity Analysis (analise de sensibilidade)")
    st.code("GET /api/v1/architect/simulations/{simulation_id}/sensitivity")
    sens_id = st.text_input(
        "simulation_id (UUID da simulacao salva)",
        placeholder="Ex: 550e8400-e29b-41d4-a716-446655440000",
        key="sens_id",
    )
    if st.button("Analisar sensibilidade", key="btn_sens"):
        if not sens_id.strip():
            st.warning("Informe o simulation_id. Faca uma simulacao primeiro para obter o UUID.")
        else:
            body, lat, sc = _call("get", f"/architect/simulations/{sens_id.strip()}/sensitivity")
            _show_result(body, lat, sc)

    st.divider()

    # ── F3 — Timing Scenarios (M3.4) ─────────────────────────────────
    st.subheader("F3 — Timing Scenarios (M3.4 — e se eu esperar?)")
    st.code("POST /api/v1/architect/timing-scenarios?monthly_savings=X&wait_months=0,3,6,12")
    with st.form("form_timing"):
        c1, c2 = st.columns(2)
        tm_uid = c1.text_input("user_id", value=user_id, key="tm_uid")
        tm_amount = c2.number_input("target_amount (R$)", value=80000.0, step=1000.0, key="tm_amount")
        c3, c4 = st.columns(2)
        tm_down = c3.number_input("down_payment (R$)", value=10000.0, step=1000.0, key="tm_down")
        tm_savings = c4.number_input(
            "monthly_savings (R$/mes)", value=2000.0, step=100.0, key="tm_savings",
            help="Quanto voce pode poupar por mes durante o periodo de espera.",
        )
        c5, c6 = st.columns(2)
        tm_months = c5.number_input("financing_months", value=60, min_value=6, max_value=360, key="tm_months")
        tm_asset = c6.selectbox("asset_type", ["IMOVEL", "VEICULO", "REFORMA", "OUTRO"], key="tm_asset")
        tm_wait = st.text_input(
            "wait_months (CSV)", value="0,3,6,12",
            help="Janelas de espera separadas por virgula. Ex: 0,3,6,12",
            key="tm_wait",
        )
        submitted_tm = st.form_submit_button("Simular cenarios de timing")
    if submitted_tm:
        tm_payload = {
            "user_id": tm_uid,
            "target_amount": tm_amount,
            "down_payment": tm_down,
            "financing_months": tm_months,
            "asset_type": tm_asset,
        }
        body, lat, sc = _call(
            "post", "/architect/timing-scenarios",
            json=tm_payload,
            params={"monthly_savings": tm_savings, "wait_months": tm_wait},
        )
        _show_result(body, lat, sc)

    st.divider()

    # ── F3 — Metricas do Usuario ──────────────────────────────────────
    st.subheader("F3 — Metricas do Usuario (Architect)")
    st.code("GET /api/v1/architect/metrics?user_id=X")
    met_uid = st.text_input("user_id", value=user_id, key="met_uid")
    if st.button("Buscar metricas Architect", key="btn_met"):
        body, lat, sc = _call("get", "/architect/metrics", params={"user_id": met_uid})
        _show_result(body, lat, sc)

    st.divider()

    # ── F2 — Opportunity Cost ─────────────────────────────────────────
    st.subheader("F2 — Opportunity Cost (custo de oportunidade do cartao atual)")
    st.code("GET /api/v1/optimizer/opportunity-cost?user_id=X&current_card_id=Y&months=N")
    c1, c2, c3 = st.columns(3)
    oc_uid = c1.text_input("user_id", value=user_id, key="oc_uid")
    oc_card = c2.text_input("current_card_id", value="nubank_roxinho", key="oc_card")
    oc_months = c3.number_input("months", value=3, min_value=1, max_value=12, key="oc_months")
    if st.button("Calcular opportunity cost", key="btn_oc"):
        body, lat, sc = _call(
            "get", "/optimizer/opportunity-cost",
            params={"user_id": oc_uid, "current_card_id": oc_card, "months": oc_months},
        )
        _show_result(body, lat, sc)

    st.divider()

    # ── F2 — Current Card ROI ─────────────────────────────────────────
    st.subheader("F2 — Current Card ROI (M2.4)")
    st.code("GET /api/v1/optimizer/roi/{card_id}?user_id=X")
    c1, c2 = st.columns(2)
    roi_card = c1.text_input("card_id", value="nubank_roxinho", key="roi_card")
    roi_uid = c2.text_input("user_id", value=user_id, key="roi_uid")
    if st.button("Calcular ROI do cartao atual", key="btn_roi"):
        body, lat, sc = _call("get", f"/optimizer/roi/{roi_card}", params={"user_id": roi_uid})
        _show_result(body, lat, sc)

    st.divider()

    # ── F2 — Optimizer Analyze (multi-card) ──────────────────────────
    st.subheader("F2 — Optimizer Analyze (analise completa multi-cartao)")
    st.code("POST /api/v1/optimizer/analyze")
    with st.form("form_optimizer"):
        opt_uid = st.text_input("user_id", value=user_id, key="opt_uid")
        opt_income = st.number_input("monthly_income (R$)", value=8500.0, step=500.0)
        submitted_opt = st.form_submit_button("Analisar cartoes")
    if submitted_opt:
        body, lat, sc = _call(
            "post", "/optimizer/analyze",
            json={"user_id": opt_uid, "monthly_income": opt_income},
        )
        _show_result(body, lat, sc)

    st.divider()

    # ── MX.4 — Peers Compare ─────────────────────────────────────────
    st.subheader("MX.4 — Peers Compare (benchmarks IBGE/POF)")
    st.code("GET /api/v1/peers/compare/{user_id}?monthly_income=X&history_months=N")
    c1, c2, c3 = st.columns(3)
    peers_uid = c1.text_input("user_id", value=user_id, key="peers_uid")
    peers_income = c2.number_input("monthly_income (R$)", value=8000.0, step=500.0, key="peers_income")
    peers_months = c3.number_input("history_months", value=3, min_value=1, max_value=12, key="peers_months")
    if st.button("Comparar com pares", key="btn_peers"):
        body, lat, sc = _call(
            "get", f"/peers/compare/{peers_uid}",
            params={"monthly_income": peers_income, "history_months": peers_months},
        )
        _show_result(body, lat, sc)

    st.divider()

    # ── F4 — Fiscal Report ────────────────────────────────────────────
    st.subheader("F4 — Fiscal Report (DAS Simples Nacional)")
    st.code("GET /api/v1/fiscal-report/{user_id}?year=YYYY&month=MM")
    c1, c2, c3 = st.columns(3)
    fis_uid = c1.text_input("user_id", value=user_id, key="fis_uid")
    fis_year = c2.number_input("year", value=2026, min_value=2020, max_value=2030, key="fis_year")
    fis_month = c3.number_input("month (0=todos)", value=0, min_value=0, max_value=12, key="fis_month")
    if st.button("Gerar relatorio fiscal", key="btn_fis"):
        params: dict = {"year": fis_year}
        if fis_month > 0:
            params["month"] = fis_month
        body, lat, sc = _call("get", f"/fiscal-report/{fis_uid}", params=params)
        _show_result(body, lat, sc)

    st.divider()

    # ── F4 — Mixed-Use Detection ──────────────────────────────────────
    st.subheader("F4 — Mixed-Use Detection (PF/PJ classifier)")
    st.code("GET /api/v1/fiscal-report/{user_id}/mixed-use")
    mu_uid = st.text_input("user_id", value=user_id, key="mu_uid")
    if st.button("Detectar uso misto PF/PJ", key="btn_mu"):
        body, lat, sc = _call("get", f"/fiscal-report/{mu_uid}/mixed-use")
        _show_result(body, lat, sc)

    st.divider()

    # ── MX.1 — Forecast ───────────────────────────────────────────────
    st.subheader("F1 — Forecast (previsao de fluxo de caixa)")
    st.code("GET /api/v1/forecast/{user_id}")
    fc_uid = st.text_input("user_id", value=user_id, key="fc_uid")
    if st.button("Buscar forecast", key="btn_fc"):
        body, lat, sc = _call("get", f"/forecast/{fc_uid}")
        _show_result(body, lat, sc)

    st.divider()

    # ── MX.3 — Alerts ─────────────────────────────────────────────────
    st.subheader("MX.3 — Alerts (alertas e anomalias)")
    st.code("GET /api/v1/alerts/{user_id}")
    al_uid = st.text_input("user_id", value=user_id, key="al_uid")
    if st.button("Buscar alertas", key="btn_al"):
        body, lat, sc = _call("get", f"/alerts/{al_uid}")
        _show_result(body, lat, sc)

    st.divider()

    # ── M1.5 — Subscriptions ─────────────────────────────────────────
    st.subheader("M1.5 — Subscriptions (assinaturas detectadas)")
    st.code("GET /api/v1/subscriptions/{user_id}")
    sub_uid = st.text_input("user_id", value=user_id, key="sub_uid")
    if st.button("Buscar assinaturas", key="btn_sub"):
        body, lat, sc = _call("get", f"/subscriptions/{sub_uid}")
        _show_result(body, lat, sc)

    st.divider()

    # ── Shadow Invoice ────────────────────────────────────────────────
    st.subheader("Shadow Invoice (fatura sombra)")
    st.code("GET /api/v1/shadow_invoice/{user_id}")
    si_uid = st.text_input("user_id", value=user_id, key="si_uid")
    if st.button("Buscar shadow invoice", key="btn_si"):
        body, lat, sc = _call("get", f"/shadow_invoice/{si_uid}")
        _show_result(body, lat, sc)
