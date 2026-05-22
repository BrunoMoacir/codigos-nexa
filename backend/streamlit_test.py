"""
Painel de testes Nexa — roda no navegador via Streamlit.
Sem API de banco, sem LLM. Usa dados mock do DuckDB.

Subir:
  cd backend
  streamlit run streamlit_test.py --server.port 8502
"""
import sys
import time
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

USER_ID        = "df9564fb-60f5-4202-8b47-a72f1877aba7"
MONTHLY_INCOME = 12500.0
BASE_URL       = "http://localhost:8000"
EMAIL          = "mock.teste@nexa.com"
SENHA          = "Mock@12345"

st.set_page_config(page_title="Nexa — Painel de Testes", page_icon="🧪", layout="wide")
st.title("🧪 Nexa — Painel de Testes Completo")
st.caption("Dados mock DuckDB · Chat com IA Haiku")

# ─── helpers ──────────────────────────────────────────────────────
def tool_invoke(import_path, fn_name, args):
    mod = __import__(import_path, fromlist=[fn_name])
    fn = getattr(mod, fn_name)
    return fn.invoke(args)


def run_test(nome, fn):
    t0 = time.time()
    try:
        res = fn()
        ms = int((time.time() - t0) * 1000)
        if res is not None and res != "":
            return True, str(res)[:400], ms
        return False, "retornou vazio", ms
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        return False, str(e)[:300], ms


def mostrar(nome, ok, detalhe, ms):
    icone = "✅" if ok else "❌"
    cor   = "green" if ok else "red"
    with st.expander(f"{icone} {nome}  —  {ms}ms", expanded=not ok):
        if ok:
            st.success(detalhe)
        else:
            st.error(detalhe)


# ─── abas ─────────────────────────────────────────────────────────
aba_chat, aba_tools, aba_http, aba_negocio = st.tabs([
    "💬 Chat Nexa",
    "🔧 Agent Tools",
    "🌐 Endpoints HTTP",
    "⚙️ Funções de Negócio",
])


# ══════════════════════════════════════════════════════════════════
# ABA 0 — CHAT INTERATIVO
# ══════════════════════════════════════════════════════════════════
with aba_chat:
    st.subheader("💬 Chat com a Inteligência Nexa")
    st.caption(f"Usuário: `{USER_ID}` · modelo: Claude Haiku")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "agent_instance" not in st.session_state:
        st.session_state.agent_instance = None
    if "chat_thread_id" not in st.session_state:
        import uuid
        st.session_state.chat_thread_id = str(uuid.uuid4())

    col_reset, col_info = st.columns([1, 4])
    with col_reset:
        if st.button("🗑️ Limpar conversa"):
            st.session_state.chat_history = []
            import uuid
            st.session_state.chat_thread_id = str(uuid.uuid4())
            st.session_state.agent_instance = None
            st.rerun()
    with col_info:
        st.info("O agente tem acesso aos seus dados financeiros reais do DuckDB.", icon="ℹ️")

    # Exibe histórico
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input do usuário
    prompt = st.chat_input("Pergunte sobre suas finanças...")
    if prompt:
        # Mostra mensagem do usuário
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Chama o agente
        with st.chat_message("assistant"):
            with st.spinner("Nexa está pensando..."):
                try:
                    from langchain_core.messages import HumanMessage

                    if st.session_state.agent_instance is None:
                        from app.agent.graph import build_financial_agent
                        st.session_state.agent_instance = build_financial_agent()

                    agent = st.session_state.agent_instance
                    inputs = {
                        "messages": [
                            HumanMessage(content=(
                                f"[user_id autenticado: {USER_ID}] "
                                f"Use SOMENTE este user_id em todas as ferramentas.\n\n"
                                f"{prompt}"
                            ))
                        ]
                    }
                    config = {"configurable": {"thread_id": st.session_state.chat_thread_id}}
                    result = agent.invoke(inputs, config=config)
                    msgs = result.get("messages", [])
                    resposta = msgs[-1].content if msgs else "Sem resposta."
                except Exception as e:
                    resposta = f"❌ Erro: {e}"

            st.markdown(resposta)
            st.session_state.chat_history.append({"role": "assistant", "content": resposta})


# ══════════════════════════════════════════════════════════════════
# ABA 1 — AGENT TOOLS
# ══════════════════════════════════════════════════════════════════
with aba_tools:
    st.subheader("Agent Tools — chamadas diretas (sem servidor)")

    TOOLS = [
        ("F0  · Perfil Financeiro",
         "app.agent.tools.get_user_profile_context", "get_user_profile_context",
         {"user_id": USER_ID}),

        ("F1  · Forecast + Safe-to-Spend",
         "app.agent.tools.get_financial_forecast", "get_financial_forecast",
         {"user_id": USER_ID, "monthly_income": MONTHLY_INCOME}),

        ("F1b · Alertas de Gastos",
         "app.agent.tools.get_spending_alerts", "get_spending_alerts",
         {"user_id": USER_ID, "monthly_income": MONTHLY_INCOME}),

        ("F2  · Otimizador de Cartões",
         "app.agent.tools.get_card_optimization", "get_card_optimization",
         {"user_id": USER_ID, "monthly_income": MONTHLY_INCOME}),

        ("F3  · Financiamento (veículo R$60k)",
         "app.agent.tools.get_financing_simulation", "get_financing_simulation",
         {"user_id": USER_ID, "target_amount": 60000, "down_payment": 10000,
          "asset_type": "VEICULO", "financing_months": 48}),

        ("F3  · Financiamento (imóvel R$350k)",
         "app.agent.tools.get_financing_simulation", "get_financing_simulation",
         {"user_id": USER_ID, "target_amount": 350000, "down_payment": 70000,
          "asset_type": "IMOVEL", "financing_months": 360}),

        ("F3b · Timing de Compra",
         "app.agent.tools.get_timing_scenarios", "get_timing_scenarios",
         {"user_id": USER_ID, "target_amount": 60000, "monthly_savings": 2000,
          "down_payment": 10000, "asset_type": "VEICULO"}),

        ("F3c · Alavancagem Imobiliária",
         "app.agent.tools.get_leverage_simulation", "get_leverage_simulation",
         {"user_id": USER_ID, "asset_value": 350000, "monthly_rent": 2200,
          "consortium_months": 180}),

        ("F4  · Relatório Fiscal 2025",
         "app.agent.tools.get_fiscal_report", "get_fiscal_report",
         {"user_id": USER_ID, "year": 2025}),

        ("F4  · Relatório Fiscal 2026",
         "app.agent.tools.get_fiscal_report", "get_fiscal_report",
         {"user_id": USER_ID, "year": 2026}),

        ("F5  · Raio-X Custos Bancários",
         "app.agent.tools.get_bank_cost_analysis", "get_bank_cost_analysis",
         {"user_id": USER_ID}),

        ("F7  · Compra Inteligente (R$3k/12x)",
         "app.agent.tools.get_purchase_recommendation", "get_purchase_recommendation",
         {"user_id": USER_ID, "amount": 3000, "category": "Eletronicos",
          "installments": 12, "monthly_income": MONTHLY_INCOME}),

        ("F7  · Compra Inteligente (R$500 à vista)",
         "app.agent.tools.get_purchase_recommendation", "get_purchase_recommendation",
         {"user_id": USER_ID, "amount": 500, "category": "Alimentacao",
          "installments": 1, "monthly_income": MONTHLY_INCOME}),

        ("F13 · Script Negociação (Itaú)",
         "app.agent.tools.get_negotiation_script", "get_negotiation_script",
         {"user_id": USER_ID, "bank_name": "Itau"}),

        ("F13 · Script Negociação (genérico)",
         "app.agent.tools.get_negotiation_script", "get_negotiation_script",
         {"user_id": USER_ID, "bank_name": ""}),

        ("M1.3 · Orçamento 50/30/20",
         "app.agent.tools.get_budget_advice", "get_budget_advice",
         {"user_id": USER_ID, "monthly_income": MONTHLY_INCOME}),

        ("MX.2 · Metas Financeiras",
         "app.agent.tools.get_goals_summary", "get_goals_summary",
         {"user_id": USER_ID, "monthly_savings": 2000.0}),

        ("MX.4 · Comparação com Pares",
         "app.agent.tools.get_peer_comparison", "get_peer_comparison",
         {"user_id": USER_ID, "monthly_income": MONTHLY_INCOME}),
    ]

    if st.button("▶ Rodar todas as Tools", type="primary", key="btn_tools"):
        resultados = []
        barra = st.progress(0, text="Iniciando...")
        for i, (nome, imp, fn, args) in enumerate(TOOLS):
            barra.progress((i + 1) / len(TOOLS), text=f"Testando {nome}...")
            ok, detalhe, ms = run_test(nome, lambda imp=imp, fn=fn, args=args: tool_invoke(imp, fn, args))
            resultados.append((nome, ok, detalhe, ms))

        barra.empty()
        passou = sum(1 for _, o, _, _ in resultados if o)
        st.metric("Resultado", f"{passou}/{len(resultados)} OK",
                  delta=f"{len(resultados)-passou} erros" if passou < len(resultados) else "Tudo certo!")

        for nome, ok_, detalhe, ms in resultados:
            mostrar(nome, ok_, detalhe, ms)


# ══════════════════════════════════════════════════════════════════
# ABA 2 — ENDPOINTS HTTP
# ══════════════════════════════════════════════════════════════════
with aba_http:
    st.subheader("Endpoints HTTP — precisa do uvicorn rodando em :8000")

    import requests as _req

    def http_test(metodo, path, body=None, params=None, esperado=200):
        if not st.session_state.get("token"):
            return False, "sem token de autenticacao", 0
        headers = {
            "Authorization": f"Bearer {st.session_state['token']}",
            "Content-Type": "application/json",
        }
        t0 = time.time()
        try:
            fn = getattr(_req, metodo.lower())
            kwargs = {"headers": headers, "timeout": 60}
            if body:   kwargs["json"] = body
            if params: kwargs["params"] = params
            r = fn(f"{BASE_URL}{path}", **kwargs)
            ms = int((time.time() - t0) * 1000)
            if r.status_code == esperado:
                try:    return True, str(r.json())[:400], ms
                except: return True, r.text[:400], ms
            return False, f"HTTP {r.status_code}: {r.text[:200]}", ms
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            return False, str(e)[:200], ms

    # Login
    col1, col2 = st.columns([2, 1])
    with col1:
        st.info(f"Login automático: **{EMAIL}**")
    with col2:
        if st.button("🔑 Autenticar", key="btn_auth"):
            try:
                r = _req.post(f"{BASE_URL}/api/v1/auth/token",
                    data={"username": EMAIL, "password": SENHA}, timeout=15)
                d = r.json()
                tok = d.get("access_token")
                if tok:
                    st.session_state["token"] = tok
                    st.success("Token obtido!")
                else:
                    st.error(str(d)[:200])
            except Exception as e:
                st.error(str(e))

    if not st.session_state.get("token"):
        st.warning("Clique em **Autenticar** primeiro.")
    else:
        st.success("Autenticado ✓")

    ENDPOINTS = [
        ("SYS   GET /health",                   "GET",  "/health",                               None, None, 200),
        ("SYS   GET /version",                  "GET",  "/version",                              None, None, 200),
        ("F1    GET /forecast/{user_id}",        "GET",  f"/api/v1/forecast/{USER_ID}",           None, {"horizon_days": 30}, 200),
        ("F1    GET /safe-to-spend/{user_id}",   "GET",  f"/api/v1/safe-to-spend/{USER_ID}",      None, None, 200),
        ("F1    GET /shadow-invoices",           "GET",  f"/api/v1/forecast/shadow-invoices/{USER_ID}", None, None, 200),
        ("F1    GET /alerts",                    "GET",  f"/api/v1/forecast/alerts/{USER_ID}",    None, None, 200),
        ("F2    POST /optimizer/analyze",        "POST", "/api/v1/optimizer/analyze",
         {"user_id": USER_ID, "monthly_income": MONTHLY_INCOME, "safe_to_spend": 5000,
          "current_cards": [], "monthly_goals_commitment": 0}, None, 200),
        ("F2    GET /optimizer/reports",         "GET",  f"/api/v1/optimizer/reports/{USER_ID}", None, None, 200),
        ("F3    POST /architect/simulate",       "POST", "/api/v1/architect/simulate",
         {"user_id": USER_ID, "target_amount": 60000, "down_payment": 10000,
          "asset_type": "VEICULO", "financing_months": 48, "risk_profile": "moderado",
          "include_consortium": True}, None, 200),
        ("F3    GET /architect/simulations",     "GET",  "/api/v1/architect/simulations",        None, {"user_id": USER_ID}, 200),
        ("F3    GET /architect/metrics",         "GET",  "/api/v1/architect/metrics",            None, {"user_id": USER_ID}, 200),
        ("F3    POST /architect/timing",         "POST", "/api/v1/architect/timing-scenarios",
         {"user_id": USER_ID, "target_amount": 60000, "down_payment": 10000,
          "asset_type": "VEICULO", "financing_months": 48, "risk_profile": "moderado"},
         {"monthly_savings": 2000}, 200),
        ("M1.3  GET /budget",                   "GET",  f"/api/v1/budget/{USER_ID}",            None, {"monthly_income": MONTHLY_INCOME}, 200),
        ("F5    GET /costs/raio-x",             "GET",  f"/api/v1/costs/raio-x/{USER_ID}",     None, None, 200),
        ("F4    GET /fiscal",                   "GET",  f"/api/v1/fiscal/{USER_ID}",           None, {"year": 2025}, 200),
        ("F4    GET /fiscal/mixed-use",         "GET",  f"/api/v1/fiscal/{USER_ID}/mixed-use", None, {"year": 2025}, 200),
        ("MX.2  GET /goals",                    "GET",  f"/api/v1/goals/{USER_ID}",            None, None, 200),
        ("MX.1  GET /health-score/history",     "GET",  f"/api/v1/health-score/history/{USER_ID}", None, None, 200),
        ("M1.5  GET /subscriptions",            "GET",  f"/api/v1/subscriptions/{USER_ID}",   None, None, 200),
        ("MX.4  GET /peers/compare",            "GET",  f"/api/v1/peers/compare/{USER_ID}",   None, {"monthly_income": MONTHLY_INCOME}, 200),
        ("MX.3  GET /notifications",            "GET",  f"/api/v1/notifications/{USER_ID}",   None, None, 200),
        ("F7    POST /purchase/analyze",        "POST", "/api/v1/purchase/analyze",
         {"user_id": USER_ID, "amount": 3000, "category": "Eletronicos",
          "installments": 12, "monthly_income": MONTHLY_INCOME}, None, 200),
        ("F13   POST /negotiator/generate-script","POST","/api/v1/negotiator/generate-script",
         {"user_id": USER_ID, "bank_name": "Itau"}, None, 200),
        ("F4    GET /context/overrides",        "GET",  "/api/v1/context/overrides",           None, None, 200),
        ("F4    GET /context/stats",            "GET",  "/api/v1/context/stats",               None, None, 200),
        ("CHAT  GET /chat/history",             "GET",  "/api/v1/chat/history",                None, {"user_id": USER_ID}, 200),
    ]

    if st.button("▶ Rodar todos os Endpoints", type="primary", key="btn_http",
                 disabled=not st.session_state.get("token")):
        resultados_http = []
        barra = st.progress(0, text="Iniciando...")
        for i, (nome, met, path, body, params, esp) in enumerate(ENDPOINTS):
            barra.progress((i + 1) / len(ENDPOINTS), text=f"{nome}...")
            ok_, det, ms = http_test(met, path, body, params, esp)
            resultados_http.append((nome, ok_, det, ms))

        barra.empty()
        passou = sum(1 for _, o, _, _ in resultados_http if o)
        st.metric("Resultado", f"{passou}/{len(resultados_http)} OK",
                  delta=f"{len(resultados_http)-passou} erros" if passou < len(resultados_http) else "Tudo certo!")

        for nome, ok_, detalhe, ms in resultados_http:
            mostrar(nome, ok_, detalhe, ms)

    # Goals CRUD separado
    st.divider()
    st.subheader("MX.2 Goals — CRUD completo")
    if st.button("▶ Testar CRUD de Metas", key="btn_goals",
                 disabled=not st.session_state.get("token")):
        resultados_goals = []

        ok_, det, ms = http_test("POST", f"/api/v1/goals/{USER_ID}",
            body={"name": "Meta Teste UI", "goal_type": "viagem",
                  "target_amount": 5000, "current_amount": 0,
                  "target_date": "2027-01-01"}, esperado=201)
        resultados_goals.append(("POST /goals (criar)", ok_, det, ms))
        goal_id = None
        if ok_:
            import json
            try:
                d = json.loads(det)
                goal_id = d.get("goal_id") or d.get("id")
            except: pass

        ok_, det, ms = http_test("GET", f"/api/v1/goals/{USER_ID}")
        resultados_goals.append(("GET /goals (listar)", ok_, det, ms))

        if goal_id:
            ok_, det, ms = http_test("GET", f"/api/v1/goals/{USER_ID}/{goal_id}")
            resultados_goals.append(("GET /goals/{id} (detalhe)", ok_, det, ms))

            ok_, det, ms = http_test("PATCH", f"/api/v1/goals/{USER_ID}/{goal_id}/progress",
                body={"amount_to_add": 500})
            resultados_goals.append(("PATCH /goals/{id}/progress", ok_, det, ms))

            ok_, det, ms = http_test("DELETE", f"/api/v1/goals/{USER_ID}/{goal_id}")
            resultados_goals.append(("DELETE /goals/{id}", ok_, det, ms))

        for nome, ok_, det, ms in resultados_goals:
            mostrar(nome, ok_, det, ms)


# ══════════════════════════════════════════════════════════════════
# ABA 3 — FUNÇÕES DE NEGÓCIO
# ══════════════════════════════════════════════════════════════════
with aba_negocio:
    st.subheader("Funções de Negócio — chamadas diretas aos serviços")

    def _pipeline():
        from app.runner import get_runner
        res = get_runner().run_from_db(user_id=USER_ID, horizon_days=30)
        txns = res.get("transactions", {})
        analysis = res.get("analysis", {})
        return (f"status={res.get('status')} | "
                f"txns={txns.get('total_transactions','?')} | "
                f"health_score={analysis.get('health_score')} | "
                f"perfil={analysis.get('profile_type')}")

    def _income():
        from app.runner import get_runner
        import polars as pl
        res = get_runner().run_from_db(user_id=USER_ID, horizon_days=30)
        df = res.get("transactions", {}).get("clean_df") or pl.DataFrame()
        from app.forecast.etl.income_profiler import IncomeProfiler
        p = IncomeProfiler().build(df)
        return f"renda=R${p.monthly_net_income:.0f} | padrao={p.income_pattern} | conf={p.confidence:.0%}"

    def _profiler():
        from app.runner import get_runner
        import polars as pl
        res = get_runner().run_from_db(user_id=USER_ID, horizon_days=30)
        txns = res.get("transactions", {})
        df = txns.get("pf_pj_classified_df") or txns.get("clean_df") or pl.DataFrame()
        from app.optimizer.profiler import ConsumptionProfiler
        p = ConsumptionProfiler().build(df)
        return f"cluster={p.lifestyle_cluster} | FSS={p.financial_stress_score}"

    def _bank_fee():
        from app.runner import get_runner
        import polars as pl
        res = get_runner().run_from_db(user_id=USER_ID, horizon_days=30)
        df = res.get("transactions", {}).get("clean_df") or pl.DataFrame()
        from app.costs.bank_fee_analyzer import BankFeeAnalyzer
        r = BankFeeAnalyzer().analyze(df, USER_ID)
        return str(r)[:300]

    def _peers():
        from app.peers.peer_comparison import PeerComparator
        from app.runner import get_runner
        import polars as pl
        res = get_runner().run_from_db(user_id=USER_ID, horizon_days=30)
        df = res.get("transactions", {}).get("clean_df") or pl.DataFrame()
        cat = {}
        if not df.is_empty() and "category" in df.columns:
            for row in df.filter(pl.col("amount") < 0).group_by("category").agg(pl.col("amount").sum()).to_dicts():
                cat[row["category"]] = abs(row["amount"])
        r = PeerComparator().compare(MONTHLY_INCOME, cat)
        return str(r)[:300]

    NEGOCIOS = [
        ("F1  NexaRunner pipeline completo",  _pipeline),
        ("F1  IncomeProfiler",                _income),
        ("F2  ConsumptionProfiler",           _profiler),
        ("F5  BankFeeAnalyzer",               _bank_fee),
        ("MX.4 PeerComparator",               _peers),
    ]

    if st.button("▶ Rodar Funções de Negócio", type="primary", key="btn_neg"):
        resultados_neg = []
        barra = st.progress(0, text="Iniciando...")
        for i, (nome, fn) in enumerate(NEGOCIOS):
            barra.progress((i + 1) / len(NEGOCIOS), text=f"{nome}...")
            ok_, det, ms = run_test(nome, fn)
            resultados_neg.append((nome, ok_, det, ms))

        barra.empty()
        passou = sum(1 for _, o, _, _ in resultados_neg if o)
        st.metric("Resultado", f"{passou}/{len(NEGOCIOS)} OK")
        for nome, ok_, det, ms in resultados_neg:
            mostrar(nome, ok_, det, ms)
