"""
streamlit_nexa_completo.py — Testador Completo Nexa (Inteligencia Direta + HTTP)

Importa e chama TODOS os modulos de inteligencia do projeto diretamente em Python,
alem de cobrir todos os endpoints REST.

Uso:
    cd backend && streamlit run streamlit_nexa_completo.py
"""
import dataclasses
import json
import logging
import sys
import time
import uuid
from datetime import date, timedelta
from typing import Any

import requests
import streamlit as st

# ─── garante que o backend esta no PYTHONPATH ────────────────────────────────
from pathlib import Path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(level=logging.WARNING)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.set_page_config(
    page_title="Nexa — Inteligencia Completa",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

_DEFS: dict[str, Any] = {
    "token": None,
    "user_id": None,
    "user_email": None,
    "chat_messages": [],
    "session_id": str(uuid.uuid4()),
    "api_url": "http://localhost:8000",
}
for _k, _v in _DEFS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS HTTP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _base() -> str:
    return st.session_state.api_url.rstrip("/")

def _hdr() -> dict:
    t = st.session_state.token
    return {"Authorization": f"Bearer {t}"} if t else {}

def _call(method: str, path: str, *, auth: bool = True, timeout: int = 60, **kw):
    t0 = time.time()
    url = f"{_base()}/api/v1{path}"
    headers = kw.pop("headers", {})
    if auth:
        headers.update(_hdr())
    try:
        r = getattr(requests, method)(url, headers=headers, timeout=timeout, **kw)
        lat = (time.time() - t0) * 1000
        try:
            return r.json(), lat, r.status_code
        except Exception:
            return r.text, lat, r.status_code
    except requests.exceptions.ConnectionError:
        return {"error": f"Backend offline em {_base()}"}, (time.time()-t0)*1000, 0
    except requests.exceptions.Timeout:
        return {"error": "Timeout"}, (time.time()-t0)*1000, 0
    except Exception as exc:
        return {"error": str(exc)}, (time.time()-t0)*1000, 0

def _show(body, latency: float, sc: int) -> None:
    color = "green" if 200 <= sc < 300 else ("orange" if 0 < sc < 500 else "red")
    st.markdown(f"**Status:** :{color}[{sc}]  |  ⏱ {latency:.0f} ms")
    if isinstance(body, (dict, list)):
        st.json(body)
    else:
        st.code(str(body))

# ─── helper: renderiza qualquer objeto Python ────────────────────────────────
def _render(obj: Any, label: str = "") -> None:
    if label:
        st.caption(label)
    if obj is None:
        st.info("Nenhum resultado.")
        return
    if isinstance(obj, list):
        st.json([_to_dict(x) for x in obj])
    elif isinstance(obj, dict):
        st.json(obj)
    else:
        try:
            import polars as pl
            if isinstance(obj, pl.DataFrame):
                if obj.is_empty():
                    st.info("DataFrame vazio.")
                else:
                    st.dataframe(obj.to_pandas(), use_container_width=True)
                return
        except ImportError:
            pass
        st.json(_to_dict(obj))

def _to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if hasattr(obj, "model_dump"):
        return _to_dict(obj.model_dump())
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _to_dict(dataclasses.asdict(obj))
    if hasattr(obj, "__dict__"):
        return _to_dict(obj.__dict__)
    return str(obj)

# ─── helper: carrega transactions_df via NexaRunner ─────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _load_txns(user_id: str):
    """Retorna (result_dict, transactions_df, income_profile) ou (None, empty_df, None)."""
    import polars as pl
    try:
        from app.runner import get_runner
        result = get_runner().run_from_db(user_id=user_id, horizon_days=30)
        if result and result.get("status") == "success":
            txns = result.get("transactions", {})
            df = txns.get("pf_pj_classified_df") or txns.get("clean_df") or pl.DataFrame()
            income = result.get("analysis", {}).get("income_profile")
            return result, df, income
    except Exception as exc:
        st.warning(f"Runner error: {exc}")
    return None, pl.DataFrame(), None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TOOL SCENARIOS (originais do projeto — todas as 14 ferramentas)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL_SCENARIOS = {
    "0. get_user_profile_context": {
        "icon": "🧠",
        "descricao": "Perfil comportamental, cluster de estilo de vida, FSS e eventos de vida",
        "mensagens": [
            "Qual meu perfil financeiro?",
            "Como voce me ve financeiramente?",
            "Tenho algum evento de vida recente que devo considerar nas minhas financas?",
        ],
    },
    "1. get_financial_forecast": {
        "icon": "📊",
        "descricao": "Resumo financeiro, safe-to-spend, health score, cashflow 30 dias",
        "mensagens": [
            "Como estao minhas financas este mes?",
            "Quanto posso gastar hoje com seguranca?",
            "Qual minha saude financeira atual?",
        ],
    },
    "2. get_budget_advice": {
        "icon": "📋",
        "descricao": "Plano 50/30/20, analise de gastos por categoria",
        "mensagens": [
            "Minha renda e R$ 8.500. Como devo organizar meu orcamento?",
            "Estou gastando bem para quem ganha R$ 6.000 por mes?",
            "Me explica a regra 50/30/20 para uma renda de R$ 10.000.",
        ],
    },
    "3. get_card_optimization": {
        "icon": "💳",
        "descricao": "Melhor cartao de credito para o perfil do usuario",
        "mensagens": [
            "Minha renda e R$ 8.500. Qual cartao de credito devo pedir?",
            "Vale a pena pagar anuidade de cartao premium para quem ganha R$ 15.000?",
            "Quero maximizar minhas milhas. Qual cartao me indica?",
        ],
    },
    "4. get_spending_alerts": {
        "icon": "🔔",
        "descricao": "Alertas ativos, anomalias, notificacoes proativas",
        "mensagens": [
            "Tem algum alerta nas minhas financas?",
            "Algum gasto estranho ou anormal este mes?",
            "O que devo me preocupar financeiramente agora?",
        ],
    },
    "5. get_goals_summary": {
        "icon": "🎯",
        "descricao": "Metas financeiras e progresso de poupanca",
        "mensagens": [
            "Como estao minhas metas financeiras?",
            "Quanto falta para minha reserva de emergencia?",
            "Consigo poupar R$ 700 por mes. Quando vou atingir minhas metas?",
        ],
    },
    "6. get_financing_simulation": {
        "icon": "🏠",
        "descricao": "Simula financiamento vs. poupanca vs. consorcio (F3)",
        "mensagens": [
            "Quero comprar um carro de R$ 60.000. Vale a pena financiar ou poupar?",
            "Estou pensando em comprar um apartamento de R$ 400.000 com R$ 80.000 de entrada. O que fazer?",
            "Quero reformar minha casa por R$ 25.000. Financiamento ou consorcio?",
        ],
    },
    "7. get_timing_scenarios": {
        "icon": "⏰",
        "descricao": "E se eu esperar X meses para ter mais entrada? (F3 M3.4)",
        "mensagens": [
            "Vale a pena esperar 6 meses para ter mais entrada no carro de R$ 60.000? Consigo poupar R$ 1.500/mes.",
            "Se eu esperar 12 meses juntando R$ 2.000/mes, quanto economizo no financiamento do apartamento de R$ 300.000?",
            "Compro o imovel agora com R$ 50.000 de entrada ou espero 6 meses para ter R$ 60.000?",
        ],
    },
    "8. get_leverage_simulation": {
        "icon": "🏗️",
        "descricao": "Alavancagem imobiliaria via consorcio: aluguel + SELIC pagam parcelas (F3.5)",
        "mensagens": [
            "Consigo comprar um imovel sem gastar nada por mes com consorcio?",
            "Quero um ape de 70m2 no Buritis em BH. O aluguel paga as parcelas do consorcio?",
            "Vale a pena fazer consorcio maior e investir o surplus? Tenho R$ 2.000/mes disponivel.",
        ],
    },
    "9. get_fiscal_report": {
        "icon": "📑",
        "descricao": "Relatorio fiscal MEI/PJ com DAS estimado (M4.1)",
        "mensagens": [
            "Quanto vou pagar de DAS esse mes como MEI?",
            "Me da um relatorio das receitas e despesas do meu negocio de 2026.",
            "Qual meu faturamento PJ e o imposto estimado no Simples Nacional?",
        ],
    },
    "10. get_peer_comparison": {
        "icon": "👥",
        "descricao": "Compara gastos com benchmarks IBGE/POF (MX.4)",
        "mensagens": [
            "Minha renda e R$ 8.000. Estou gastando mais que a media em moradia?",
            "Comparado a pessoas com renda de R$ 5.000, como estou em alimentacao e lazer?",
            "Qual meu percentil de poupanca para quem ganha R$ 12.000 por mes?",
        ],
    },
    "11. get_purchase_recommendation": {
        "icon": "🛒",
        "descricao": "Melhor forma de pagar: PIX, cartao a vista, parcelado ou CDC (F7)",
        "mensagens": [
            "Qual a melhor forma de pagar R$ 3.000 em eletronicos em 12x?",
            "Vale mais a pena parcelar uma TV de R$ 4.500 em 10x ou pagar no PIX?",
            "Vou comprar uma moto de R$ 12.000. Devo pegar CDC ou parcelar no cartao?",
        ],
    },
    "12. get_bank_cost_analysis": {
        "icon": "🏦",
        "descricao": "Raio-X de custos e tarifas bancarias (F5)",
        "mensagens": [
            "Quanto estou pagando de tarifas e anuidades bancarias?",
            "Meu banco esta me cobrando muito? Quanto economizo trocando para um banco digital?",
            "Quais sao meus custos bancarios mensais?",
        ],
    },
    "13. get_negotiation_script": {
        "icon": "🤝",
        "descricao": "Detecta oportunidades e gera roteiro de negociacao bancaria (F13)",
        "mensagens": [
            "Como negocio a isencao da minha anuidade de cartao?",
            "Meu banco esta me cobrando juros altos. Me da um script para falar com o gerente.",
            "Tenho poder de barganha com meu banco? Quero renegociar minhas tarifas.",
        ],
    },
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SIDEBAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with st.sidebar:
    st.title("Nexa — Inteligencia Completa")

    st.subheader("Backend")
    _api = st.text_input("URL", value=st.session_state.api_url, key="api_input")
    st.session_state.api_url = _api.rstrip("/")
    if st.button("Ping", key="ping_btn"):
        try:
            r = requests.get(f"{_base()}/health", timeout=3)
            st.success("Online") if r.status_code == 200 else st.warning(f"HTTP {r.status_code}")
        except Exception:
            st.error("Offline")

    st.divider()

    if st.session_state.token:
        st.success(f"Logado: {st.session_state.user_email}")
        st.caption(f"`{st.session_state.user_id}`")
        if st.button("Logout"):
            _call("post", "/auth/logout")
            st.session_state.token = None
            st.session_state.user_id = None
            st.session_state.user_email = None
            st.session_state.chat_messages = []
            st.session_state.session_id = str(uuid.uuid4())
            _load_txns.clear()
            st.rerun()
    else:
        at, rt = st.tabs(["Login", "Registro"])
        with at:
            le = st.text_input("E-mail", key="le")
            lp = st.text_input("Senha", type="password", key="lp")
            if st.button("Entrar", use_container_width=True):
                try:
                    r = requests.post(f"{_base()}/api/v1/auth/token",
                                      data={"username": le, "password": lp}, timeout=10)
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
                    r = requests.post(f"{_base()}/api/v1/auth/register",
                                      json={"full_name": rn, "email": re, "password": rp}, timeout=10)
                    if r.status_code in (200, 201):
                        st.success("Conta criada! Faca login.")
                    else:
                        st.error(r.json().get("detail", r.text))
                except Exception as exc:
                    st.error(str(exc))

    st.divider()
    st.subheader("Cenarios de Teste (14 ferramentas)")
    st.caption("Clique para enviar ao chat do agente.")
    for tool_name, cfg in TOOL_SCENARIOS.items():
        with st.expander(f"{cfg['icon']} {tool_name}"):
            st.caption(cfg["descricao"])
            for msg in cfg["mensagens"]:
                lbl = msg[:65] + ("..." if len(msg) > 65 else "")
                if st.button(lbl, key=f"ts_{tool_name}_{msg[:20]}"):
                    st.session_state["_pending_chat"] = msg

    st.divider()
    st.caption("Nexa Testador v3.0 — inteligencia direta + HTTP")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TITULO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.title("Nexa — Testador de Inteligencia Completo")
if not st.session_state.token:
    st.info("Faca login na barra lateral para habilitar todos os modulos.")

uid = st.session_state.user_id or "SEU_USER_ID"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
(
    tab_chat,
    tab_runner,
    tab_profiler,
    tab_cashflow,
    tab_budget,
    tab_optimizer,
    tab_architect,
    tab_purchase,
    tab_costs,
    tab_negotiator,
    tab_subs,
    tab_goals,
    tab_fiscal,
    tab_peers,
    tab_notifier,
    tab_divider,
    tab_predictor,
    tab_http,
    tab_server,
) = st.tabs([
    "Chat IA",
    "NexaRunner",
    "Profiler / Cluster / Eventos",
    "Cashflow / Burn / Anomalias",
    "Orcamento 50/30/20",
    "Otimizador de Cartoes",
    "Arquiteto F3",
    "Compra Inteligente F7",
    "Custos Bancarios F5",
    "Negociador F13",
    "Assinaturas M1.5",
    "Metas MX.2",
    "Fiscal M4.1",
    "Pares IBGE/POF",
    "Notificacoes MX.3",
    "Divider PF/PJ",
    "ML Spend Predictor",
    "Endpoints HTTP",
    "Servidor",
])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 1 — CHAT IA (Bearer token real)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_chat:
    st.subheader("Chat com Agente Nexa — 14 ferramentas de inteligencia")
    st.caption("`POST /api/v1/chat/`  — autenticado via Bearer token JWT")

    if not st.session_state.token:
        st.warning("Faca login para usar o chat autenticado.")
    else:
        c1, c2, c3 = st.columns([4, 1, 1])
        with c2:
            if st.button("Nova sessao"):
                st.session_state.chat_messages = []
                st.session_state.session_id = str(uuid.uuid4())
                st.rerun()
        with c3:
            if st.button("Limpar historico DB"):
                _call("delete", "/chat/history", params={"user_id": uid})
                st.success("Historico removido.")

        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg["role"] == "assistant" and msg.get("latency_ms"):
                    st.caption(f"⏱ {msg['latency_ms']:.0f} ms")

        pending = st.session_state.pop("_pending_chat", None)
        user_input = st.chat_input("Digite sua mensagem ou clique em um cenario no menu lateral...")
        msg_to_send = pending or (user_input if user_input else None)

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
                            json={"user_id": uid, "message": msg_to_send,
                                  "session_id": st.session_state.session_id},
                            headers=_hdr(), timeout=120,
                        )
                        lat = (time.time() - t0) * 1000
                        resp_text = r.json().get("response", "(sem resposta)") if r.status_code == 200 \
                            else f"Erro {r.status_code}: {r.json().get('detail', r.text)}"
                    except Exception as exc:
                        lat = (time.time() - t0) * 1000
                        resp_text = f"Erro: {exc}"
                st.markdown(resp_text)
                st.caption(f"⏱ {lat:.0f} ms  |  session `{st.session_state.session_id[:8]}...`")

            st.session_state.chat_messages.append(
                {"role": "assistant", "content": resp_text, "latency_ms": lat}
            )
            st.rerun()

    with st.expander("Historico persistido no banco"):
        if st.button("Buscar historico", key="btn_chat_hist"):
            body, lat, sc = _call("get", "/chat/history", params={"user_id": uid})
            _show(body, lat, sc)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 2 — NEXARUNNER (direto Python)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_runner:
    st.subheader("NexaRunner — Orquestrador Central (F1)")
    st.code("from app.runner import get_runner\nresult = get_runner().run_from_db(user_id, horizon_days)")
    st.caption(
        "run_from_db: le transacoes do Postgres para o user_id informado. "
        "run: usa DuckDB mock (dados sinteticos, nao precisa de user_id)."
    )

    c1, c2 = st.columns(2)
    run_uid = c1.text_input("user_id", value=uid, key="run_uid")
    run_days = c2.number_input("horizon_days", value=30, min_value=7, max_value=90, key="run_days")

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("run_from_db (Postgres — dados reais)", use_container_width=True):
            with st.spinner("Executando NexaRunner..."):
                t0 = time.time()
                try:
                    from app.runner import get_runner
                    result = get_runner().run_from_db(user_id=run_uid, horizon_days=run_days)
                    lat = (time.time() - t0) * 1000
                    st.success(f"Concluido em {lat:.0f} ms")
                    if result:
                        st.metric("Status", result.get("status", "?"))
                        proj = result.get("projections", {})
                        sts = proj.get("safe_to_spend")
                        if sts:
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Safe-to-Spend total", f"R$ {sts.safe_to_spend_total:,.0f}")
                            c2.metric("Safe-to-Spend diario", f"R$ {sts.safe_to_spend_daily:,.2f}")
                            c3.metric("Risco", sts.risk_level)
                        income = result.get("analysis", {}).get("income_profile")
                        if income:
                            st.metric("Renda estimada", f"R$ {income.monthly_net_income:,.0f}/mes "
                                      f"({income.income_pattern.value} | conf {income.confidence:.0%})")
                        txns = result.get("transactions", {})
                        df = txns.get("pf_pj_classified_df") or txns.get("clean_df")
                        if df is not None and not df.is_empty():
                            st.write(f"**Transacoes carregadas:** {len(df)} linhas")
                            st.dataframe(df.to_pandas().head(20), use_container_width=True)
                        else:
                            st.warning("Nenhuma transacao encontrada para este user_id.")
                        with st.expander("Resultado completo"):
                            _render(result)
                    else:
                        st.warning("Runner retornou None — sem dados para este usuario.")
                except Exception as exc:
                    st.error(f"Erro: {exc}")

    with col_b:
        if st.button("run (DuckDB mock — dados sinteticos)", use_container_width=True):
            with st.spinner("Executando NexaRunner mock..."):
                t0 = time.time()
                try:
                    from app.runner import get_runner
                    result = get_runner().run(horizon_days=run_days)
                    lat = (time.time() - t0) * 1000
                    st.success(f"Concluido em {lat:.0f} ms")
                    with st.expander("Resultado completo", expanded=True):
                        _render(result)
                except Exception as exc:
                    st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 3 — PROFILER / CLUSTER / EVENTOS DE VIDA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_profiler:
    st.subheader("Profiler Pack — Cluster, FSS, Health Score, Eventos de Vida")

    prof_uid = st.text_input("user_id", value=uid, key="prof_uid")

    # ── ConsumptionProfiler ──────────────────────────────────────────
    st.markdown("### ConsumptionProfiler (Cluster + FSS)")
    st.code(
        "from app.optimizer.profiler import ConsumptionProfiler\n"
        "profile = ConsumptionProfiler().build(transactions_df)"
    )
    if st.button("Executar ConsumptionProfiler", key="btn_cp"):
        with st.spinner("Carregando transacoes e calculando perfil..."):
            try:
                _, df, _ = _load_txns(prof_uid)
                if df.is_empty():
                    st.warning("Nenhuma transacao encontrada. Execute o webhook primeiro.")
                else:
                    from app.optimizer.profiler import ConsumptionProfiler
                    profile = ConsumptionProfiler().build(df)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Cluster", profile.lifestyle_cluster)
                    c2.metric("FSS", f"{profile.fss:.0f}/100")
                    c3.metric("Nivel FSS", profile.fss_level)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Gasto medio/mes", f"R$ {profile.monthly_avg_spend:,.0f}")
                    c2.metric("Taxa poupanca", f"{getattr(profile,'savings_rate',0):.1f}%")
                    c3.metric("Assinaturas/mes", f"R$ {getattr(profile,'subscription_burn_monthly',0):,.0f}")
                    with st.expander("Objeto completo"):
                        _render(profile)
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    # ── UserProfileAnalyzer (Health Score) ───────────────────────────
    st.markdown("### UserProfileAnalyzer (Health Score, ProfileType, BehaviorTier)")
    st.code(
        "from app.forecast.etl.profiles import UserProfileAnalyzer\n"
        "profile = UserProfileAnalyzer().analyze(transactions_df, income_profile=income)"
    )
    if st.button("Executar UserProfileAnalyzer", key="btn_upa"):
        with st.spinner():
            try:
                _, df, income = _load_txns(prof_uid)
                if df.is_empty():
                    st.warning("Sem transacoes.")
                else:
                    from app.forecast.etl.profiles import UserProfileAnalyzer
                    profile = UserProfileAnalyzer().analyze(df, income_profile=income)
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Health Score", f"{profile.financial_health_score}/100")
                    c2.metric("Tendencia", profile.trend)
                    c3.metric("Perfil", getattr(profile, "profile_type", "?"))
                    c4.metric("Behavior Tier", getattr(profile, "behavior_tier", "?"))
                    with st.expander("Objeto completo"):
                        _render(profile)
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    # ── LifeEventsDetector ───────────────────────────────────────────
    st.markdown("### LifeEventsDetector — Eventos de vida recentes")
    st.code(
        "from app.optimizer.detectors.life_events_detector import LifeEventsDetector\n"
        "events = LifeEventsDetector().detect_all(txns_recent, txns_history, income_recent, income_hist)"
    )
    if st.button("Detectar eventos de vida", key="btn_led"):
        with st.spinner():
            try:
                import polars as pl
                _, df, income = _load_txns(prof_uid)
                if df.is_empty():
                    st.warning("Sem transacoes.")
                else:
                    from app.optimizer.detectors.life_events_detector import LifeEventsDetector
                    date_col = "date" if "date" in df.columns else "transaction_date"
                    today = date.today()
                    recent = df.filter(pl.col(date_col).cast(pl.Date) >= today - timedelta(days=60))
                    history = df.filter(pl.col(date_col).cast(pl.Date) < today - timedelta(days=180))
                    inc = income.monthly_net_income if income else 0.0
                    events = LifeEventsDetector().detect_all(
                        txns_recent=recent, txns_history=history,
                        income_recent=inc, income_historical=inc,
                    )
                    if events:
                        st.success(f"{len(events)} evento(s) detectado(s):")
                        for e in events:
                            st.write(f"**{e.event}** (conf {e.confidence:.0%}) → {e.trigger_action}")
                    else:
                        st.info("Nenhum evento de vida detectado no periodo analisado.")
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    # ── IncomeProfiler ───────────────────────────────────────────────
    st.markdown("### IncomeProfiler — Renda, padrao CLT/PJ/MIXED")
    st.code(
        "from app.forecast.etl.income_profiler import IncomeProfiler\n"
        "income = IncomeProfiler().build(transactions_df)"
    )
    if st.button("Executar IncomeProfiler", key="btn_ip"):
        with st.spinner():
            try:
                _, df, _ = _load_txns(prof_uid)
                if df.is_empty():
                    st.warning("Sem transacoes.")
                else:
                    from app.forecast.etl.income_profiler import IncomeProfiler
                    income = IncomeProfiler().build(df)
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Renda estimada", f"R$ {income.monthly_net_income:,.0f}")
                    c2.metric("Padrao", income.income_pattern.value)
                    c3.metric("Confianca", f"{income.confidence:.0%}")
                    c4.metric("Estabilidade", f"{income.income_stability:.2f}")
                    with st.expander("Objeto completo"):
                        _render(income)
            except Exception as exc:
                st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 4 — CASHFLOW / BURN RATE / ANOMALIAS / SAFE-TO-SPEND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_cashflow:
    st.subheader("Cashflow Pack — Burn Rate, Anomalias, Safe-to-Spend")
    cf_uid = st.text_input("user_id", value=uid, key="cf_uid")

    # ── BurnRateAnalyzer ─────────────────────────────────────────────
    st.markdown("### BurnRateAnalyzer")
    st.code(
        "from app.forecast.cashflow.burn_rate import BurnRateAnalyzer\n"
        "report = BurnRateAnalyzer(history_months=3).analyze(transactions_df, monthly_income=X)"
    )
    c1, c2 = st.columns(2)
    br_months = c1.number_input("history_months", value=3, min_value=1, max_value=6, key="br_months")
    br_income = c2.number_input("monthly_income (0=auto)", value=0.0, min_value=0.0, key="br_income")
    if st.button("Analisar Burn Rate", key="btn_br"):
        with st.spinner():
            try:
                _, df, income = _load_txns(cf_uid)
                if df.is_empty():
                    st.warning("Sem transacoes.")
                else:
                    from app.forecast.cashflow.burn_rate import BurnRateAnalyzer
                    inc = br_income if br_income > 0 else (income.monthly_net_income if income else None)
                    report = BurnRateAnalyzer(history_months=br_months).analyze(df, monthly_income=inc)
                    st.metric("Nivel de alerta", report.alert_level if hasattr(report, "alert_level") else "?")
                    with st.expander("Relatorio completo", expanded=True):
                        _render(report)
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    # ── SpendingAnomalyDetector ──────────────────────────────────────
    st.markdown("### SpendingAnomalyDetector")
    st.code(
        "from app.forecast.etl.spending_anomaly_detector import SpendingAnomalyDetector\n"
        "anomalies = SpendingAnomalyDetector().detect(transactions_df, history_df)"
    )
    sad_lookback = st.number_input("lookback_months (meses de historico)", value=3, min_value=1, max_value=6, key="sad_lb")
    if st.button("Detectar Anomalias", key="btn_sad"):
        with st.spinner():
            try:
                import polars as pl
                _, df, income = _load_txns(cf_uid)
                if df.is_empty():
                    st.warning("Sem transacoes.")
                else:
                    from app.forecast.etl.spending_anomaly_detector import SpendingAnomalyDetector
                    date_col = "date" if "date" in df.columns else "transaction_date"
                    cutoff = date.today() - timedelta(days=sad_lookback * 30)
                    recent = df.filter(pl.col(date_col).cast(pl.Date) >= cutoff)
                    history = df.filter(pl.col(date_col).cast(pl.Date) < cutoff)
                    anomalies = SpendingAnomalyDetector(lookback_months=sad_lookback).detect(
                        recent, history, income_profile=income
                    )
                    if anomalies:
                        st.warning(f"{len(anomalies)} anomalia(s) detectada(s):")
                        for a in anomalies:
                            st.write(f"**{a.anomaly_type}** [{a.severity}] — {a.description}")
                    else:
                        st.success("Nenhuma anomalia detectada.")
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    # ── SafeToSpendCalculator ────────────────────────────────────────
    st.markdown("### SafeToSpendCalculator")
    st.code(
        "from app.forecast.cashflow.safe_to_spend import SafeToSpendCalculator\n"
        "result = SafeToSpendCalculator().calculate(projection_df, horizon_days=30)"
    )
    sts_days = st.number_input("horizon_days", value=30, min_value=7, max_value=90, key="sts_days")
    if st.button("Calcular Safe-to-Spend direto", key="btn_sts"):
        with st.spinner():
            try:
                result, df, income = _load_txns(cf_uid)
                if result is None:
                    st.warning("Sem dados do runner. Use o endpoint HTTP para este calculo.")
                else:
                    sts = result.get("projections", {}).get("safe_to_spend")
                    if sts:
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Safe-to-Spend (total)", f"R$ {sts.safe_to_spend_total:,.2f}")
                        c2.metric("Safe-to-Spend (diario)", f"R$ {sts.safe_to_spend_daily:,.2f}")
                        c3.metric("Nivel de risco", sts.risk_level)
                        _render(sts)
                    else:
                        st.info("Sem dados de projecao no resultado do runner.")
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    # ── RecurringDetector ────────────────────────────────────────────
    st.markdown("### RecurringDetector — transacoes recorrentes")
    st.code(
        "from app.forecast.etl.recurring_detector import RecurringDetector\n"
        "recurring = RecurringDetector().detect(transactions_df)"
    )
    if st.button("Detectar recorrencias", key="btn_rd"):
        with st.spinner():
            try:
                _, df, _ = _load_txns(cf_uid)
                if df.is_empty():
                    st.warning("Sem transacoes.")
                else:
                    from app.forecast.etl.recurring_detector import RecurringDetector
                    result = RecurringDetector().detect(df)
                    _render(result, "Transacoes recorrentes detectadas")
            except Exception as exc:
                st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 5 — BUDGET ADVISOR 50/30/20
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_budget:
    st.subheader("BudgetAdvisor — Plano 50/30/20 (M1.3)")
    st.code(
        "from app.budget.budget_advisor import BudgetAdvisor\n"
        "suggestion = BudgetAdvisor(history_months=3).suggest(transactions_df, monthly_income)"
    )
    c1, c2, c3 = st.columns(3)
    bud_uid = c1.text_input("user_id", value=uid, key="bud_uid")
    bud_income = c2.number_input("monthly_income (R$)", value=8500.0, step=500.0, key="bud_inc")
    bud_months = c3.number_input("history_months", value=3, min_value=1, max_value=6, key="bud_m")
    bud_cluster = st.selectbox(
        "lifestyle_cluster (opcional)",
        ["NAO_CLASSIFICADO", "EXPLORADOR_GLOBAL", "URBANO_FOODIE", "INVESTIDOR_CAUTELOSO",
         "FAMILIA_ESTRUTURADA", "DIGITAL_NATIVO", "ESTRESSE_FINANCEIRO", "MICROEMPREENDEDOR"],
        key="bud_cluster",
    )

    if st.button("Calcular orcamento 50/30/20", use_container_width=True):
        with st.spinner():
            try:
                _, df, _ = _load_txns(bud_uid)
                from app.budget.budget_advisor import BudgetAdvisor
                suggestion = BudgetAdvisor(history_months=bud_months).suggest(
                    transactions_df=df,
                    monthly_income=bud_income,
                    lifestyle_cluster=bud_cluster,
                )
                st.markdown(f"**Resumo:** {suggestion.summary_text}")
                st.markdown(f"**Regra aplicada:** {suggestion.rule_applied}")
                st.markdown(f"**Confianca:** {suggestion.confidence:.0%}")
                st.markdown(f"**Cluster:** {suggestion.lifestyle_cluster}")
                if suggestion.cluster_note:
                    st.info(suggestion.cluster_note)

                st.markdown("#### Grupos 50/30/20")
                for g in suggestion.group_summary:
                    status_icon = "✅" if g.status == "OK" else "⚠️"
                    st.write(
                        f"{status_icon} **{g.group.title()}** — "
                        f"atual: R$ {g.current_amount:,.0f} ({g.current_pct:.0%}) | "
                        f"recomendado: R$ {g.suggested_amount:,.0f} ({g.target_pct:.0%})"
                    )

                if suggestion.actionable_cuts:
                    st.markdown("#### Cortes sugeridos")
                    for cut in suggestion.actionable_cuts:
                        st.write(
                            f"• **{cut.category}** [{cut.group}]: "
                            f"R$ {cut.current:,.0f} → R$ {cut.suggested:,.0f} "
                            f"(economia R$ {cut.saving:,.0f}/mes) — {cut.reasoning}"
                        )

                with st.expander("Objeto completo"):
                    _render(suggestion)
            except Exception as exc:
                st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 6 — OTIMIZADOR DE CARTOES (F2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_optimizer:
    st.subheader("Otimizador de Cartoes (F2) — OptimizerService + MultiCardStrategist + OpportunityCost")
    opt_uid = st.text_input("user_id", value=uid, key="opt_uid")

    # ── OptimizerService ─────────────────────────────────────────────
    st.markdown("### OptimizerService.analyze()")
    st.code(
        "from app.optimizer.services.optimizer_service import OptimizerService\n"
        "from app.optimizer.models import OptimizationRequest\n"
        "report = OptimizerService().analyze(request, transactions_df)"
    )
    c1, c2 = st.columns(2)
    opt_income = c1.number_input("monthly_income (R$)", value=8500.0, step=500.0, key="opt_inc")
    opt_sts = c2.number_input("safe_to_spend (0=auto)", value=0.0, min_value=0.0, key="opt_sts")

    if st.button("Analisar cartoes (OptimizerService)", use_container_width=True, key="btn_opt_svc"):
        with st.spinner():
            try:
                _, df, income = _load_txns(opt_uid)
                inc = opt_income or (income.monthly_net_income if income else 0)
                sts_val = opt_sts if opt_sts > 0 else None

                from app.optimizer.models import OptimizationRequest
                from app.optimizer.services.optimizer_service import OptimizerService

                req = OptimizationRequest(
                    user_id=opt_uid,
                    monthly_income=inc,
                    safe_to_spend=sts_val,
                    current_cards=[],
                )
                report = OptimizerService().analyze(request=req, transactions_df=df)

                st.metric("Recomendacao", report.recommendation_type.value)
                st.write(f"**Estrategia:** {report.strategy_text}")
                if report.best_card:
                    bc = report.best_card
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Card vencedor", bc.card_name)
                    c2.metric("Lucro liquido anual", f"R$ {bc.net_gain_expected:,.0f}")
                    c3.metric("Anuidade efetiva", f"R$ {bc.annuity_effective:,.0f}")

                if report.all_cards:
                    st.markdown("#### Top cartoes analisados")
                    for c in report.all_cards[:5]:
                        st.write(
                            f"**{c.card_name}** — lucro: R$ {c.net_gain_expected:,.0f} | "
                            f"beneficios: R$ {c.points_value_expected:,.0f}"
                        )

                if report.warnings:
                    for w in report.warnings:
                        st.warning(w)

                with st.expander("Objeto completo"):
                    _render(report)
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    # ── MultiCardStrategist ──────────────────────────────────────────
    st.markdown("### MultiCardStrategist.optimize_portfolio()")
    st.code(
        "from app.optimizer.multi_card_strategy import MultiCardStrategist\n"
        "from app.optimizer.card_loader import CardKnowledgeBase\n"
        "portfolio = MultiCardStrategist().optimize_portfolio(profile, eligible_cards, max_cards=3)"
    )
    c1, c2 = st.columns(2)
    mcs_income = c1.number_input("monthly_income (R$)", value=8500.0, key="mcs_income")
    mcs_max = c2.number_input("max_cards", value=3, min_value=1, max_value=5, key="mcs_max")
    if st.button("Otimizar portfolio multi-cartao", key="btn_mcs"):
        with st.spinner():
            try:
                _, df, income = _load_txns(opt_uid)
                from app.optimizer.profiler import ConsumptionProfiler
                from app.optimizer.multi_card_strategy import MultiCardStrategist
                from app.optimizer.card_loader import CardKnowledgeBase

                profile = ConsumptionProfiler().build(df)
                cards = CardKnowledgeBase().get_all_cards()
                portfolio = MultiCardStrategist().optimize_portfolio(
                    profile=profile, eligible_cards=cards, max_cards=mcs_max
                )
                _render(portfolio, "Portfolio otimizado multi-cartao")
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    # ── OpportunityCostCalculator ────────────────────────────────────
    st.markdown("### OpportunityCostCalculator — custo de oportunidade do cartao atual")
    st.code(
        "from app.optimizer.opportunity_cost import OpportunityCostCalculator\n"
        "report = OpportunityCostCalculator().calculate(profile, current_card, candidate_cards, months=3)"
    )
    c1, c2 = st.columns(2)
    oc_card = c1.text_input("current_card_id", value="nubank_roxinho", key="oc_card_dir")
    oc_months = c2.number_input("months", value=3, min_value=1, max_value=12, key="oc_months_dir")
    if st.button("Calcular opportunity cost", key="btn_oc_dir"):
        with st.spinner():
            try:
                _, df, income = _load_txns(opt_uid)
                from app.optimizer.profiler import ConsumptionProfiler
                from app.optimizer.opportunity_cost import OpportunityCostCalculator
                from app.optimizer.card_loader import CardKnowledgeBase

                profile = ConsumptionProfiler().build(df)
                kb = CardKnowledgeBase()
                all_cards = kb.get_all_cards()
                current = next((c for c in all_cards if c.card_id == oc_card), all_cards[0] if all_cards else None)
                if current is None:
                    st.error(f"card_id '{oc_card}' nao encontrado.")
                else:
                    report = OpportunityCostCalculator().calculate(
                        profile=profile,
                        current_card=current,
                        candidate_cards=[c for c in all_cards if c.card_id != oc_card],
                        months=oc_months,
                    )
                    _render(report)
            except Exception as exc:
                st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 7 — ARQUITETO FINANCEIRO (F3)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_architect:
    st.subheader("ArchitectService — Simulacao de Aquisicao (F3)")
    st.code(
        "from app.architect.services.architect_service import ArchitectService\n"
        "from app.architect.models import SimulationRequest, AssetType, RiskProfile\n"
        "response = ArchitectService().simulate(request)"
    )

    with st.form("form_arch_dir"):
        c1, c2 = st.columns(2)
        arc_uid = c1.text_input("user_id", value=uid)
        arc_amount = c2.number_input("target_amount (R$)", value=60000.0, step=1000.0)
        c3, c4 = st.columns(2)
        arc_down = c3.number_input("down_payment (R$)", value=10000.0, step=1000.0)
        arc_budget = c4.number_input("max_monthly_budget (R$, 0=sem limite)", value=0.0, step=100.0)
        c5, c6 = st.columns(2)
        arc_months = c5.number_input("financing_months", value=48, min_value=6, max_value=360)
        arc_asset = c6.selectbox("asset_type", ["VEICULO", "IMOVEL", "REFORMA", "VIAGEM", "OUTRO"])
        c7, c8 = st.columns(2)
        arc_risk = c7.selectbox("risk_profile", ["moderado", "conservador", "agressivo"])
        arc_rental = c8.number_input("expected_rental_income (R$/mes, so IMOVEL)", value=0.0, min_value=0.0)
        arc_consortium = st.checkbox("include_consortium", value=True)
        submitted_arc = st.form_submit_button("Simular aquisicao (ArchitectService direto)", use_container_width=True)

    if submitted_arc:
        with st.spinner("Consultando BACEN, ANBIMA, IPCA..."):
            try:
                from app.architect.models import SimulationRequest, AssetType, RiskProfile
                from app.architect.services.architect_service import ArchitectService

                asset_map = {
                    "IMOVEL": AssetType.IMOVEL, "VEICULO": AssetType.VEICULO,
                    "REFORMA": AssetType.REFORMA, "VIAGEM": AssetType.VIAGEM,
                }
                risk_map = {"conservador": RiskProfile.CONSERVADOR, "agressivo": RiskProfile.AGRESSIVO}
                kw = dict(
                    user_id=arc_uid,
                    target_amount=arc_amount,
                    down_payment=arc_down,
                    financing_months=arc_months,
                    asset_type=asset_map.get(arc_asset, AssetType.OUTRO),
                    risk_profile=risk_map.get(arc_risk, RiskProfile.MODERADO),
                    include_consortium=arc_consortium,
                )
                if arc_budget > 0:
                    kw["max_monthly_budget"] = arc_budget
                if arc_rental > 0 and arc_asset == "IMOVEL":
                    kw["expected_rental_income"] = arc_rental

                req = SimulationRequest(**kw)
                _, df, _ = _load_txns(arc_uid)
                response = ArchitectService().simulate(req, transactions_df=df if not df.is_empty() else None)

                st.metric("Estrategia recomendada", response.recommended_strategy)
                if hasattr(response, "confidence_score"):
                    st.metric("Confianca", f"{response.confidence_score:.0%}")
                if response.warnings:
                    for w in response.warnings:
                        st.warning(w)
                with st.expander("Resposta completa", expanded=True):
                    _render(response)
            except Exception as exc:
                st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 8 — COMPRA INTELIGENTE (F7)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_purchase:
    st.subheader("PurchaseAdvisor — Compra Inteligente (F7)")
    st.code(
        "from app.purchase.purchase_advisor import PurchaseAdvisor\n"
        "from app.purchase.models import PurchaseRequest\n"
        "result = PurchaseAdvisor().analyze(request)"
    )

    with st.form("form_pur_dir"):
        c1, c2 = st.columns(2)
        pur_uid = c1.text_input("user_id", value=uid)
        pur_amount = c2.number_input("amount (R$)", value=3000.0, min_value=1.0)
        c3, c4 = st.columns(2)
        pur_cat = c3.text_input("category", value="Eletronicos")
        pur_inst = c4.number_input("installments", value=12, min_value=1, max_value=48)
        pur_income = st.number_input("monthly_income (0=sem renda declarada)", value=8500.0, min_value=0.0)
        submitted_pur = st.form_submit_button("Analisar compra (PurchaseAdvisor direto)", use_container_width=True)

    if submitted_pur:
        with st.spinner():
            try:
                from app.purchase.models import PurchaseRequest
                from app.purchase.purchase_advisor import PurchaseAdvisor

                req = PurchaseRequest(
                    user_id=pur_uid,
                    amount=pur_amount,
                    category=pur_cat,
                    installments=pur_inst,
                    monthly_income=pur_income if pur_income > 0 else None,
                )
                result = PurchaseAdvisor().analyze(req)
                st.success(f"Recomendacao: **{result.recommended_label}**")
                c1, c2 = st.columns(2)
                c1.metric("Custo liquido recomendado", f"R$ {result.recommended_net_cost:,.2f}")

                st.markdown("#### Todas as opcoes comparadas")
                for opt in result.options:
                    icon = "✅" if opt.payment_method == result.recommended_method else "  "
                    st.write(
                        f"{icon} **{opt.label}** — custo total: R$ {opt.total_cost:,.2f} | "
                        f"recompensa: R$ {opt.reward_value:,.2f} | liquido: R$ {opt.net_cost:,.2f}"
                    )
                with st.expander("Objeto completo"):
                    _render(result)
            except Exception as exc:
                st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 9 — CUSTOS BANCARIOS (F5)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_costs:
    st.subheader("BankFeeAnalyzer — Raio-X de Custos Bancarios (F5)")
    st.code(
        "from app.costs.bank_fee_analyzer import BankFeeAnalyzer\n"
        "report = BankFeeAnalyzer().analyze(transactions_df, user_id)"
    )
    costs_uid = st.text_input("user_id", value=uid, key="costs_uid")

    if st.button("Analisar custos bancarios (direto)", use_container_width=True, key="btn_costs_dir"):
        with st.spinner():
            try:
                _, df, _ = _load_txns(costs_uid)
                if df.is_empty():
                    st.warning("Sem transacoes.")
                else:
                    from app.costs.bank_fee_analyzer import BankFeeAnalyzer
                    report = BankFeeAnalyzer().analyze(transactions_df=df, user_id=costs_uid)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total pago", f"R$ {report.total_paid:,.2f}")
                    c2.metric("Media mensal", f"R$ {report.monthly_avg:,.2f}")
                    c3.metric("Projecao anual", f"R$ {report.annual_projection:,.2f}")
                    if report.savings_opportunity:
                        st.success(f"Economia potencial: R$ {report.savings_opportunity:,.2f}/ano trocando de banco")
                    if report.by_bank:
                        st.markdown("#### Por banco")
                        for b in report.by_bank:
                            st.write(f"**{b.bank_name}** — R$ {b.total_paid:,.2f} "
                                     f"| media/mes: R$ {b.monthly_avg:,.2f}")
                    with st.expander("Objeto completo"):
                        _render(report)
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    st.markdown("### FeeDetector — detecta tarifas individuais nas transacoes")
    st.code(
        "from app.costs.fee_detector import FeeDetector\n"
        "fees = FeeDetector().detect(transactions_df)"
    )
    if st.button("Detectar tarifas (FeeDetector)", key="btn_fd"):
        with st.spinner():
            try:
                _, df, _ = _load_txns(costs_uid)
                if df.is_empty():
                    st.warning("Sem transacoes.")
                else:
                    from app.costs.fee_detector import FeeDetector
                    fees = FeeDetector().detect(df)
                    if fees:
                        st.write(f"**{len(fees)} tarifa(s) detectada(s):**")
                        for f in fees:
                            st.write(f"• {f.bank_name} | {f.fee_type} | R$ {f.amount:,.2f} em {f.transaction_date}")
                    else:
                        st.info("Nenhuma tarifa detectada nas transacoes.")
            except Exception as exc:
                st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 10 — NEGOCIADOR (F13)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_negotiator:
    st.subheader("Negociador Bot (F13) — Detector + ScriptGenerator")
    neg_uid = st.text_input("user_id", value=uid, key="neg_uid")

    # ── NegotiationOpportunityDetector ──────────────────────────────
    st.markdown("### NegotiationOpportunityDetector")
    st.code(
        "from app.negotiator.opportunity_detector import NegotiationOpportunityDetector\n"
        "opportunities = NegotiationOpportunityDetector().detect(transactions_df, health_score=75)"
    )
    neg_health = st.number_input("health_score (para barganha)", value=75, min_value=0, max_value=100, key="neg_hs")

    if st.button("Detectar oportunidades de negociacao", key="btn_neg_detect"):
        with st.spinner():
            try:
                _, df, _ = _load_txns(neg_uid)
                if df.is_empty():
                    st.warning("Sem transacoes.")
                else:
                    from app.negotiator.opportunity_detector import NegotiationOpportunityDetector
                    opps = NegotiationOpportunityDetector().detect(df, health_score=neg_health)
                    if opps:
                        st.success(f"{len(opps)} oportunidade(s) detectada(s):")
                        for o in opps:
                            st.write(
                                f"**{o.trigger}** | banco: {o.bank_name} | produto: {o.product} | "
                                f"economia potencial: R$ {o.potential_saving_monthly:,.2f}/mes"
                            )
                        st.session_state["_neg_opps"] = opps
                    else:
                        st.info("Nenhuma oportunidade de negociacao detectada.")
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    # ── NegotiationScriptGenerator ───────────────────────────────────
    st.markdown("### NegotiationScriptGenerator — gera roteiro via LLM")
    st.code(
        "from app.negotiator.script_generator import NegotiationScriptGenerator\n"
        "script = NegotiationScriptGenerator().generate(opportunity)"
    )
    st.caption("Requer LLM configurado (OPENAI_API_KEY ou ANTHROPIC_API_KEY no .env).")

    if st.button("Gerar scripts para todas as oportunidades", key="btn_neg_script"):
        opps = st.session_state.get("_neg_opps")
        if not opps:
            st.warning("Execute a deteccao de oportunidades primeiro.")
        else:
            with st.spinner("Gerando scripts via LLM..."):
                try:
                    from app.negotiator.script_generator import NegotiationScriptGenerator
                    gen = NegotiationScriptGenerator()
                    for opp in opps:
                        script = gen.generate(opp)
                        st.markdown(f"#### {opp.bank_name} — {opp.trigger}")
                        _render(script)
                except Exception as exc:
                    st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 11 — ASSINATURAS RECORRENTES (M1.5)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_subs:
    st.subheader("SubscriptionDetector — Assinaturas Recorrentes (M1.5)")
    st.code(
        "from app.subscriptions.subscription_detector import SubscriptionDetector\n"
        "report = SubscriptionDetector().detect(transactions_df, user_id)"
    )
    subs_uid = st.text_input("user_id", value=uid, key="subs_uid_dir")
    subs_months = st.number_input("janela de analise (meses)", value=6, min_value=2, max_value=24, key="subs_m")

    if st.button("Detectar assinaturas (direto)", use_container_width=True, key="btn_subs_dir"):
        with st.spinner():
            try:
                import polars as pl
                _, df, _ = _load_txns(subs_uid)
                if df.is_empty():
                    st.warning("Sem transacoes.")
                else:
                    date_col = "date" if "date" in df.columns else "transaction_date"
                    cutoff = date.today() - timedelta(days=subs_months * 30)
                    df_filtered = df.filter(pl.col(date_col).cast(pl.Date) >= cutoff)

                    from app.subscriptions.subscription_detector import SubscriptionDetector
                    report = SubscriptionDetector().detect(df_filtered, user_id=subs_uid)

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total assinaturas", report.total_subscriptions)
                    c2.metric("Custo mensal total", f"R$ {report.total_monthly_cost:,.2f}")
                    c3.metric("Alertas", report.alerted_count)

                    st.write(f"**Resumo:** {report.summary_text}")

                    if report.subscriptions:
                        st.markdown("#### Assinaturas detectadas")
                        for s in report.subscriptions:
                            st.write(
                                f"• **{s.merchant}** [{s.subscription_category}] — "
                                f"R$ {s.monthly_amount:,.2f}/mes | "
                                f"{s.occurrences} ocorrencias"
                            )
                    if report.alerted:
                        st.markdown("#### Alertas")
                        for a in report.alerted:
                            for alert_msg in a.alert_messages:
                                st.warning(alert_msg)

                    with st.expander("Objeto completo"):
                        _render(report)
            except Exception as exc:
                st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 12 — METAS FINANCEIRAS (MX.2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_goals:
    st.subheader("GoalTracker + GoalProfileAdvisor (MX.2)")
    goals_uid = st.text_input("user_id", value=uid, key="goals_uid_dir")

    # ── GoalTracker.list_goals ───────────────────────────────────────
    st.markdown("### GoalTracker — listar metas")
    st.code(
        "from app.goals.tracker import GoalTracker\n"
        "result = GoalTracker().list_goals(user_id)"
    )
    if st.button("Listar metas (GoalTracker)", key="btn_gt_list"):
        with st.spinner():
            try:
                from app.goals.tracker import GoalTracker
                data = GoalTracker().list_goals(user_id=goals_uid)
                goals = data.get("goals", [])
                st.metric("Total de metas", len(goals))
                for g in goals:
                    pct = (g.get("current_amount", 0) / g["target_amount"] * 100) if g.get("target_amount") else 0
                    st.write(
                        f"**{g['name']}** [{g.get('goal_type','?')}] — "
                        f"R$ {g.get('current_amount',0):,.0f} / R$ {g['target_amount']:,.0f} "
                        f"({pct:.0f}%) | status: {g.get('status','?')}"
                    )
                with st.expander("Dados completos"):
                    _render(data)
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    # ── GoalTracker.create_goal ──────────────────────────────────────
    st.markdown("### GoalTracker — criar meta")
    st.code(
        "goal = GoalTracker().create_goal(user_id, name, target_amount, target_date, current_amount, goal_type)"
    )
    with st.form("form_gt_create"):
        c1, c2 = st.columns(2)
        gt_name = c1.text_input("name", value="Reserva de Emergencia")
        gt_type = c2.selectbox("goal_type", ["reserva_emergencia", "imovel", "veiculo", "viagem", "educacao", "outros"])
        c3, c4 = st.columns(2)
        gt_target = c3.number_input("target_amount (R$)", value=30000.0, min_value=1.0)
        gt_current = c4.number_input("current_amount (R$)", value=5000.0, min_value=0.0)
        gt_date = st.text_input("target_date (YYYY-MM-DD, opcional)", value="2027-12-31")
        submitted_gt = st.form_submit_button("Criar meta")
    if submitted_gt:
        with st.spinner():
            try:
                from app.goals.tracker import GoalTracker
                goal = GoalTracker().create_goal(
                    user_id=goals_uid,
                    name=gt_name,
                    target_amount=gt_target,
                    target_date=gt_date.strip() if gt_date.strip() else None,
                    current_amount=gt_current,
                    goal_type=gt_type,
                )
                st.success(f"Meta criada: `{goal.goal_id}`")
                st.session_state["_last_goal_id"] = goal.goal_id
                _render(goal)
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    # ── GoalProfileAdvisor ───────────────────────────────────────────
    st.markdown("### GoalProfileAdvisor — analisa metas vs. perfil financeiro")
    st.code(
        "from app.goals.profile_advisor import GoalProfileAdvisor\n"
        "context = GoalProfileAdvisor().analyze(profile, active_goals)"
    )
    if st.button("Analisar metas vs. perfil (GoalProfileAdvisor)", key="btn_gpa"):
        with st.spinner():
            try:
                _, df, income = _load_txns(goals_uid)
                from app.forecast.etl.profiles import UserProfileAnalyzer
                from app.goals.tracker import GoalTracker
                from app.goals.profile_advisor import GoalProfileAdvisor

                user_profile = UserProfileAnalyzer().analyze(df, income_profile=income)
                goals_data = GoalTracker().list_goals(user_id=goals_uid)
                active_goals = goals_data.get("goals", [])

                context = GoalProfileAdvisor().analyze(user_profile, active_goals)
                _render(context, "Contexto de metas vs. perfil")
            except Exception as exc:
                st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 13 — RELATORIO FISCAL (M4.1)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_fiscal:
    st.subheader("FiscalReportService — Relatorio Fiscal MEI/PJ (M4.1)")
    st.code(
        "from app.fiscal.fiscal_report import FiscalReportService\n"
        "report = FiscalReportService().generate(user_id, year, month)"
    )
    c1, c2, c3 = st.columns(3)
    fis_uid = c1.text_input("user_id", value=uid, key="fis_uid_dir")
    fis_year = c2.number_input("year", value=date.today().year, min_value=2020, max_value=2030, key="fis_year_dir")
    fis_month = c3.number_input("month (0=todos)", value=0, min_value=0, max_value=12, key="fis_month_dir")

    if st.button("Gerar relatorio fiscal (direto)", use_container_width=True, key="btn_fis_dir"):
        with st.spinner():
            try:
                from app.fiscal.fiscal_report import FiscalReportService
                report = FiscalReportService().generate(
                    user_id=fis_uid,
                    year=fis_year,
                    month=fis_month if fis_month > 0 else None,
                )
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total Receita PJ", f"R$ {report.total_receita:,.2f}")
                c2.metric("Total Despesa PJ", f"R$ {report.total_despesa:,.2f}")
                c3.metric("Lucro estimado", f"R$ {report.lucro_estimado:,.2f}")
                c4.metric("DAS estimado", f"R$ {report.das_estimado:,.2f}")
                st.write(f"**Faixa DAS:** {report.das_faixa} | **Aliquota efetiva:** {report.das_aliquota_efetiva:.1%}")
                with st.expander("Relatorio completo"):
                    _render(report)
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    st.markdown("### MixedUseDetector — detecta transacoes com uso misto PF/PJ")
    st.code(
        "from app.forecast.etl.mixed_use_detector import MixedUseDetector\n"
        "result = MixedUseDetector().detect(transactions_df)"
    )
    if st.button("Detectar uso misto PF/PJ", key="btn_mud"):
        with st.spinner():
            try:
                _, df, _ = _load_txns(fis_uid)
                if df.is_empty():
                    st.warning("Sem transacoes.")
                else:
                    from app.forecast.etl.mixed_use_detector import MixedUseDetector
                    result = MixedUseDetector().detect(df)
                    _render(result, "Transacoes com uso misto detectadas")
            except Exception as exc:
                st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 14 — COMPARACAO COM PARES IBGE/POF (MX.4)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_peers:
    st.subheader("PeerComparator — Benchmarks IBGE/POF (MX.4)")
    st.code(
        "from app.peers.peer_comparison import PeerComparator\n"
        "report = PeerComparator().compare(monthly_income, category_spending)"
    )
    c1, c2, c3 = st.columns(3)
    peers_uid = c1.text_input("user_id", value=uid, key="peers_uid_dir")
    peers_income = c2.number_input("monthly_income (R$)", value=8000.0, step=500.0, key="peers_inc")
    peers_months = c3.number_input("history_months", value=3, min_value=1, max_value=12, key="peers_m")

    if st.button("Comparar com pares IBGE/POF (direto)", use_container_width=True, key="btn_peers_dir"):
        with st.spinner():
            try:
                import polars as pl
                _, df, _ = _load_txns(peers_uid)

                # Montar category_spending do df real
                category_spending: dict[str, float] = {}
                if not df.is_empty():
                    date_col = "date" if "date" in df.columns else "transaction_date"
                    cutoff = date.today() - timedelta(days=peers_months * 30)
                    df_period = df.filter(pl.col(date_col).cast(pl.Date) >= cutoff)
                    debits = df_period.filter(pl.col("amount") < 0)
                    if not debits.is_empty() and "category" in debits.columns:
                        for row in debits.select(["amount", "category"]).to_dicts():
                            cat = (row.get("category") or "outros").lower().strip()
                            category_spending[cat] = category_spending.get(cat, 0) + abs(row["amount"])
                        # media mensal
                        category_spending = {k: v / peers_months for k, v in category_spending.items()}

                from app.peers.peer_comparison import PeerComparator
                report = PeerComparator().compare(
                    monthly_income=peers_income,
                    category_spending=category_spending,
                )
                st.write(f"**Faixa:** {report.bracket_label}")
                c1, c2 = st.columns(2)
                c1.metric("Poupanca usuario", f"{report.user_savings_rate:.1%}")
                c2.metric("Poupanca benchmark", f"{report.benchmark_savings_rate:.1%}")
                st.write(f"**Percentil poupanca:** {report.savings_percentile_label}")
                st.write(f"**Resumo:** {report.summary_text}")

                if report.highlights_above:
                    st.warning("Acima da media: " + ", ".join(report.highlights_above))
                if report.highlights_below:
                    st.success("Abaixo da media: " + ", ".join(report.highlights_below))

                st.markdown("#### Por categoria")
                for c in report.categories:
                    icon = "🔴" if c.status == "acima" else ("🟢" if c.status == "abaixo" else "⚪")
                    st.write(
                        f"{icon} **{c.label}** — voce: {c.user_pct:.1%} | media: {c.benchmark_pct:.1%} | "
                        f"delta: {c.delta_pct:+.1f} p.p."
                    )
                with st.expander("Objeto completo"):
                    _render(report)
            except Exception as exc:
                st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 15 — NOTIFICACOES PROATIVAS (MX.3)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_notifier:
    st.subheader("ProactiveNotifier — Notificacoes Proativas (MX.3)")
    st.code(
        "from app.notifications.notifier import ProactiveNotifier, NotificationContext\n"
        "notifications = ProactiveNotifier().generate(ctx)"
    )
    notif_uid = st.text_input("user_id", value=uid, key="notif_uid_dir")

    if st.button("Gerar notificacoes proativas (direto)", use_container_width=True, key="btn_notif_dir"):
        with st.spinner():
            try:
                from app.notifications.notifier import ProactiveNotifier, NotificationContext

                # Tentar construir contexto com dados reais
                ctx = NotificationContext()
                result, df, income = _load_txns(notif_uid)
                if result:
                    alerts = result.get("alerts", [])
                    # Passa alertas como burn_rate_categories se disponivel
                    # (NotificationContext aceita listas vazias sem problema)

                notifs = ProactiveNotifier().generate(ctx)
                if notifs:
                    st.success(f"{len(notifs)} notificacao(oes) gerada(s):")
                    for n in notifs:
                        priority_color = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(n.priority, "⚪")
                        st.write(f"{priority_color} **[{n.type}]** {n.title}")
                        st.caption(n.message)
                        if n.action_hint:
                            st.caption(f"Acao sugerida: {n.action_hint}")
                else:
                    st.info("Nenhuma notificacao proativa gerada com o contexto atual.")
                with st.expander("Todas as notificacoes (JSON)"):
                    _render(notifs)
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()
    st.markdown("### Generators individuais do ProactiveNotifier")
    st.caption("Cada funcao gera um tipo especifico de notificacao.")
    with st.expander("Ver generators disponíveis"):
        st.code("""
from app.notifications.notifier import (
    generate_burn_rate_notifications,       # burn_rate_categories: list[BurnRateCategoryInput]
    generate_anomaly_notifications,          # anomalies: list[AnomalyInput]
    generate_subscription_increase_notifications,  # changes: list[SubscriptionChangeInput]
    generate_card_opportunity_notifications, # opportunities: list[CardOpportunityInput]
    generate_waiver_alert_notifications,     # waiver_alerts: list[WaiverAlertInput]
    generate_transfer_promo_notifications,   # promos: list[TransferPromoInput]
    generate_score_improved_notification,    # change: Optional[ScoreChangeInput]
    generate_goal_progress_notifications,    # goals: list[GoalProgressInput]
    generate_safe_to_spend_low_notification, # sts: Optional[SafeToSpendInput]
    generate_life_event_notifications,       # events: list[LifeEventInput]
)
""")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 16 — DIVIDER PF/PJ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_divider:
    st.subheader("PFPJClassifier + SubcategoryClassifier — Divider (F4)")
    div_uid = st.text_input("user_id", value=uid, key="div_uid")

    # ── PFPJClassifier ───────────────────────────────────────────────
    st.markdown("### PFPJClassifier.classify_batch()")
    st.code(
        "from app.divider.classifier import PFPJClassifier\n"
        "df_classified = PFPJClassifier().classify_batch(transactions_df)"
    )
    if st.button("Classificar PF/PJ (direto)", key="btn_div"):
        with st.spinner():
            try:
                _, df, _ = _load_txns(div_uid)
                if df.is_empty():
                    st.warning("Sem transacoes.")
                else:
                    from app.divider.classifier import PFPJClassifier
                    df_out = PFPJClassifier().classify_batch(df)
                    if "context_type" in df_out.columns or "pf_pj_label" in df_out.columns:
                        label_col = "pf_pj_label" if "pf_pj_label" in df_out.columns else "context_type"
                        counts = df_out[label_col].value_counts()
                        st.dataframe(counts.to_pandas())
                    st.dataframe(df_out.to_pandas().head(30), use_container_width=True)
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()

    # ── SubcategoryClassifier ────────────────────────────────────────
    st.markdown("### SubcategoryClassifier — subcategoria PJ")
    st.code(
        "from app.divider.subcategory_classifier import SubcategoryClassifier\n"
        "subcategory = SubcategoryClassifier().classify(description)"
    )
    sub_desc = st.text_input("description da transacao", value="AWS Cloud Services Amazon", key="sub_desc")
    if st.button("Classificar subcategoria PJ", key="btn_sub_cls"):
        try:
            from app.divider.subcategory_classifier import SubcategoryClassifier
            subcategory = SubcategoryClassifier().classify(sub_desc)
            st.success(f"Subcategoria PJ: **{subcategory}**")
        except Exception as exc:
            st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 17 — ML SPEND PREDICTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_predictor:
    st.subheader("SpendPredictor — ML de Previsao de Gastos")
    st.code(
        "from app.ml.spend_predictor import SpendPredictor\n"
        "pred = SpendPredictor().predict_next_30d(transactions_df, category='Alimentacao')\n"
        "by_cat = SpendPredictor().predict_by_category(transactions_df)"
    )
    st.caption(
        "Usa Prophet (se >= 6 meses de historico) ou moving average como fallback. "
        "Retorna SpendPrediction com predicted_spend, confidence_interval e method."
    )
    pred_uid = st.text_input("user_id", value=uid, key="pred_uid")

    c1, c2 = st.columns(2)

    with c1:
        pred_cat = st.text_input("category (vazio = total)", value="", key="pred_cat")
        if st.button("predict_next_30d", use_container_width=True, key="btn_pred30"):
            with st.spinner():
                try:
                    _, df, _ = _load_txns(pred_uid)
                    if df.is_empty():
                        st.warning("Sem transacoes.")
                    else:
                        from app.ml.spend_predictor import SpendPredictor
                        pred = SpendPredictor().predict_next_30d(
                            df, category=pred_cat.strip() if pred_cat.strip() else None
                        )
                        c1m, c2m, c3m = st.columns(3)
                        c1m.metric("Gasto previsto (30d)", f"R$ {pred.predicted_spend:,.2f}")
                        c2m.metric("Intervalo inferior", f"R$ {pred.confidence_interval[0]:,.2f}")
                        c3m.metric("Intervalo superior", f"R$ {pred.confidence_interval[1]:,.2f}")
                        st.caption(f"Metodo: {pred.method}")
                        _render(pred)
                except Exception as exc:
                    st.error(f"Erro: {exc}")

    with c2:
        pred_min = st.number_input("min_monthly_spend (R$)", value=50.0, key="pred_min")
        if st.button("predict_by_category (todas)", use_container_width=True, key="btn_pred_cat"):
            with st.spinner():
                try:
                    _, df, _ = _load_txns(pred_uid)
                    if df.is_empty():
                        st.warning("Sem transacoes.")
                    else:
                        from app.ml.spend_predictor import SpendPredictor
                        by_cat = SpendPredictor().predict_by_category(df, min_monthly_spend=pred_min)
                        st.write(f"**{len(by_cat)} categoria(s) com previsao:**")
                        for cat, pred in by_cat.items():
                            st.write(
                                f"• **{cat}** — R$ {pred.predicted_spend:,.2f} "
                                f"[{pred.confidence_interval[0]:,.0f} – {pred.confidence_interval[1]:,.0f}] "
                                f"({pred.method})"
                            )
                except Exception as exc:
                    st.error(f"Erro: {exc}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 18 — TODOS OS ENDPOINTS HTTP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_http:
    st.subheader("Endpoints REST — chamadas HTTP para todos os modulos")

    # ── Transacoes ───────────────────────────────────────────────────
    with st.expander("Transacoes — GET + POST webhook Pluggy"):
        c1, c2, c3 = st.columns(3)
        tx_uid = c1.text_input("user_id", value=uid, key="tx_uid")
        tx_cat = c2.text_input("category", key="tx_cat")
        tx_limit = c3.number_input("limit", value=20, min_value=1, key="tx_lim")
        if st.button("GET /transactions/{uid}", key="btn_tx"):
            params = {"limit": tx_limit}
            if tx_cat:
                params["category"] = tx_cat
            _show(*_call("get", f"/transactions/{tx_uid}", params=params))

        st.markdown("**POST /transactions/webhook**")
        wh_uid = st.text_input("user_id webhook", value=uid, key="wh_uid")
        wh_payload = st.text_area("Payload JSON (lista Pluggy)", height=160, key="wh_payload",
            value=json.dumps([
                {"id": str(uuid.uuid4()), "description": "Salario", "amount": 8500.0,
                 "date": str(date.today()), "type": "CREDIT", "category": "Salario", "accountId": "acc_1"},
                {"id": str(uuid.uuid4()), "description": "Supermercado", "amount": -350.0,
                 "date": str(date.today()), "type": "DEBIT", "category": "Alimentacao", "accountId": "acc_1"},
            ], indent=2, ensure_ascii=False))
        if st.button("Enviar webhook", key="btn_wh"):
            try:
                _show(*_call("post", "/transactions/webhook", params={"user_id": wh_uid},
                             json=json.loads(wh_payload), auth=False))
            except Exception as exc:
                st.error(str(exc))

    # ── Health Score ─────────────────────────────────────────────────
    with st.expander("Health Score (MX.1)"):
        c1, c2 = st.columns(2)
        hs_uid = c1.text_input("user_id", value=uid, key="hs_uid2")
        hs_m = c2.number_input("months", value=6, min_value=1, max_value=24, key="hs_m2")
        if st.button("GET /health-score/history/{uid}", key="btn_hs2"):
            _show(*_call("get", f"/health-score/history/{hs_uid}", params={"months": hs_m}))

    # ── Metas ────────────────────────────────────────────────────────
    with st.expander("Metas (MX.2) — CRUD HTTP"):
        g_uid = st.text_input("user_id", value=uid, key="g_uid2")
        if st.button("GET /goals/{uid}", key="btn_g2"):
            _show(*_call("get", f"/goals/{g_uid}"))
        with st.form("form_g_create2"):
            gn2 = st.text_input("name", value="Viagem Europa")
            gt2 = st.number_input("target_amount", value=20000.0)
            submitted_g2 = st.form_submit_button("POST /goals/{uid}")
        if submitted_g2:
            _show(*_call("post", f"/goals/{g_uid}", json={"name": gn2, "target_amount": gt2, "goal_type": "viagem"}))

    # ── Orcamento ────────────────────────────────────────────────────
    with st.expander("Orcamento 50/30/20 (M1.3)"):
        c1, c2 = st.columns(2)
        b_uid = c1.text_input("user_id", value=uid, key="b_uid2")
        b_inc = c2.number_input("monthly_income", value=8500.0, key="b_inc2")
        if st.button("GET /budget/{uid}", key="btn_b2"):
            _show(*_call("get", f"/budget/{b_uid}", params={"monthly_income": b_inc}))

    # ── Assinaturas ──────────────────────────────────────────────────
    with st.expander("Assinaturas (M1.5)"):
        s_uid = st.text_input("user_id", value=uid, key="s_uid2")
        s_m = st.number_input("months", value=6, min_value=2, max_value=24, key="s_m2")
        if st.button("GET /subscriptions/{uid}", key="btn_s2"):
            _show(*_call("get", f"/subscriptions/{s_uid}", params={"months": s_m}, auth=False))

    # ── Contexto PF/PJ ───────────────────────────────────────────────
    with st.expander("Contexto PF/PJ — Divider (F4)"):
        ctx_uid2 = st.text_input("user_id (query param)", value=uid, key="ctx_uid2")
        if st.button("GET /context/overrides", key="btn_ctx2"):
            _show(*_call("get", "/context/overrides", params={"user_id": ctx_uid2}))
        if st.button("GET /context/stats", key="btn_ctx_stats2"):
            _show(*_call("get", "/context/stats", params={"user_id": ctx_uid2}))

    # ── Otimizador ───────────────────────────────────────────────────
    with st.expander("Otimizador de Cartoes (F2)"):
        o_uid2 = st.text_input("user_id", value=uid, key="o_uid2")
        if st.button("GET /optimizer/cards", key="btn_oc2"):
            _show(*_call("get", "/optimizer/cards", auth=False))
        if st.button("GET /optimizer/promotions", key="btn_op2"):
            _show(*_call("get", "/optimizer/promotions", auth=False))
        o_inc2 = st.number_input("monthly_income para analyze", value=8500.0, key="o_inc2")
        if st.button("POST /optimizer/analyze", key="btn_oa2"):
            _show(*_call("post", "/optimizer/analyze",
                         json={"user_id": o_uid2, "monthly_income": o_inc2}))

    # ── Arquiteto ────────────────────────────────────────────────────
    with st.expander("Arquiteto Financeiro (F3)"):
        if st.button("GET /architect/simulations", key="btn_arch2"):
            _show(*_call("get", "/architect/simulations", params={"user_id": uid}))
        if st.button("GET /architect/metrics", key="btn_arch_m2"):
            _show(*_call("get", "/architect/metrics", params={"user_id": uid}))

    # ── Compra Inteligente ───────────────────────────────────────────
    with st.expander("Compra Inteligente (F7)"):
        c1, c2, c3 = st.columns(3)
        pu_uid2 = c1.text_input("user_id", value=uid, key="pu_uid2")
        pu_amt = c2.number_input("amount", value=3000.0, key="pu_amt")
        pu_inst = c3.number_input("installments", value=12, key="pu_inst")
        if st.button("POST /purchase/analyze", key="btn_pu2"):
            _show(*_call("post", "/purchase/analyze",
                         json={"user_id": pu_uid2, "amount": pu_amt,
                               "category": "Eletronicos", "installments": pu_inst}))

    # ── Custos Bancarios ─────────────────────────────────────────────
    with st.expander("Custos Bancarios (F5)"):
        co_uid = st.text_input("user_id", value=uid, key="co_uid2")
        if st.button("GET /costs/raio-x/{uid}", key="btn_co2"):
            _show(*_call("get", f"/costs/raio-x/{co_uid}"))

    # ── Negociador ───────────────────────────────────────────────────
    with st.expander("Negociador Bot (F13)"):
        ne_uid = st.text_input("user_id", value=uid, key="ne_uid2")
        ne_bank = st.text_input("bank_name (opcional)", key="ne_bank2")
        if st.button("POST /negotiator/generate-script", key="btn_ne2"):
            payload = {"user_id": ne_uid}
            if ne_bank.strip():
                payload["bank_name"] = ne_bank.strip()
            _show(*_call("post", "/negotiator/generate-script", json=payload))

    # ── Fiscal ───────────────────────────────────────────────────────
    with st.expander("Relatorio Fiscal (M4.1)"):
        fi_uid = st.text_input("user_id", value=uid, key="fi_uid2")
        c1, c2 = st.columns(2)
        fi_year = c1.number_input("year", value=date.today().year, key="fi_year2")
        fi_month = c2.number_input("month (0=todos)", value=0, min_value=0, max_value=12, key="fi_month2")
        if st.button("GET /fiscal-report/{uid}", key="btn_fi2"):
            params = {"year": fi_year}
            if fi_month > 0:
                params["month"] = fi_month
            _show(*_call("get", f"/fiscal-report/{fi_uid}", params=params))
        if st.button("GET /fiscal-report/{uid}/mixed-use", key="btn_fi_mu"):
            _show(*_call("get", f"/fiscal-report/{fi_uid}/mixed-use"))

    # ── Pares ────────────────────────────────────────────────────────
    with st.expander("Comparacao Pares IBGE/POF (MX.4)"):
        c1, c2 = st.columns(2)
        pe_uid = c1.text_input("user_id", value=uid, key="pe_uid2")
        pe_inc = c2.number_input("monthly_income", value=8000.0, key="pe_inc2")
        if st.button("GET /peers/compare/{uid}", key="btn_pe2"):
            _show(*_call("get", f"/peers/compare/{pe_uid}", params={"monthly_income": pe_inc}))

    # ── Forecast + Safe-to-Spend ─────────────────────────────────────
    with st.expander("Forecast + Safe-to-Spend (F1)"):
        fc_uid = st.text_input("user_id", value=uid, key="fc_uid2")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("GET /forecast/{uid}", key="btn_fc2"):
                _show(*_call("get", f"/forecast/{fc_uid}"))
        with c2:
            if st.button("GET /safe-to-spend/{uid}", key="btn_sts2"):
                _show(*_call("get", f"/safe-to-spend/{fc_uid}"))

    # ── Alertas + Notificacoes ───────────────────────────────────────
    with st.expander("Alertas (MX.3) + Notificacoes"):
        al_uid2 = st.text_input("user_id", value=uid, key="al_uid2")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("GET /alerts/{uid}", key="btn_al2"):
                _show(*_call("get", f"/alerts/{al_uid2}"))
        with c2:
            if st.button("GET /notifications/{uid}", key="btn_nf2"):
                _show(*_call("get", f"/notifications/{al_uid2}"))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 19 — SERVIDOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_server:
    st.subheader("Saude do Servidor")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("GET /health", key="btn_hc"):
            try:
                r = requests.get(f"{_base()}/health", timeout=5)
                _show(r.json(), 0, r.status_code)
            except Exception as exc:
                st.error(str(exc))
    with c2:
        st.markdown(f"[Swagger UI]({_base()}/docs)")
        st.markdown(f"[ReDoc]({_base()}/redoc)")
    with c3:
        if st.button("Limpar cache de transacoes"):
            _load_txns.clear()
            st.success("Cache limpo.")

    st.divider()
    st.json({
        "api_url": _base(),
        "autenticado": bool(st.session_state.token),
        "user_id": st.session_state.user_id,
        "email": st.session_state.user_email,
        "session_id": st.session_state.session_id,
        "msgs_chat": len(st.session_state.chat_messages),
    })
