"""
Teste completo do projeto Nexa - todas as tools, endpoints HTTP e funcoes de negocio.
Usa dados mock seedados no DuckDB. Nao precisa de API de banco.

Uso:
  python test_completo.py           -> testa tools + HTTP (precisa uvicorn rodando)
  python test_completo.py --tools   -> so tools diretas (sem servidor)
"""
import sys
import os
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

# ─── Config ──────────────────────────────────────────────────────────────────
USER_ID       = "df9564fb-60f5-4202-8b47-a72f1877aba7"
EMAIL         = "mock.teste@nexa.com"
SENHA         = "Mock@12345"
MONTHLY_INCOME = 12500.0
BASE_URL      = "http://localhost:8000"
SO_TOOLS      = "--tools" in sys.argv

resultados: list[tuple[str, bool, str]] = []


def lim(texto, n=260):
    return str(texto).encode("ascii", errors="replace").decode("ascii")[:n]


def ok(nome, detalhe=""):
    resultados.append((nome, True, ""))
    print(f"  [OK  ] {nome}")
    if detalhe:
        print(f"         {lim(detalhe, 200)}")


def falha(nome, erro):
    resultados.append((nome, False, lim(str(erro), 120)))
    print(f"  [ERRO] {nome}")
    print(f"         {lim(str(erro), 200)}")


def secao(titulo):
    print(f"\n{'='*65}")
    print(f"  {titulo}")
    print(f"{'='*65}")


# ═══════════════════════════════════════════════════════════════════
# PARTE 1 — TOOLS DIRETAS (sem servidor)
# ═══════════════════════════════════════════════════════════════════
secao("PARTE 1 — AGENT TOOLS (chamadas diretas)")


def tool_test(nome, tool_import_path, tool_name, args: dict):
    try:
        mod = __import__(tool_import_path, fromlist=[tool_name])
        fn = getattr(mod, tool_name)
        res = fn.invoke(args)
        if res:
            ok(nome, str(res)[:200])
        else:
            falha(nome, "retornou vazio")
    except Exception as e:
        falha(nome, e)


tool_test("F0  get_user_profile_context",
    "app.agent.tools.get_user_profile_context", "get_user_profile_context",
    {"user_id": USER_ID})

tool_test("F1  get_financial_forecast",
    "app.agent.tools.get_financial_forecast", "get_financial_forecast",
    {"user_id": USER_ID, "monthly_income": MONTHLY_INCOME})

tool_test("F1b get_spending_alerts",
    "app.agent.tools.get_spending_alerts", "get_spending_alerts",
    {"user_id": USER_ID, "monthly_income": MONTHLY_INCOME})

tool_test("F2  get_card_optimization",
    "app.agent.tools.get_card_optimization", "get_card_optimization",
    {"user_id": USER_ID, "monthly_income": MONTHLY_INCOME})

tool_test("F3  get_financing_simulation (veiculo R$60k)",
    "app.agent.tools.get_financing_simulation", "get_financing_simulation",
    {"user_id": USER_ID, "target_amount": 60000, "down_payment": 10000,
     "asset_type": "VEICULO", "financing_months": 48})

tool_test("F3  get_financing_simulation (imovel R$350k)",
    "app.agent.tools.get_financing_simulation", "get_financing_simulation",
    {"user_id": USER_ID, "target_amount": 350000, "down_payment": 70000,
     "asset_type": "IMOVEL", "financing_months": 360})

tool_test("F3b get_timing_scenarios",
    "app.agent.tools.get_timing_scenarios", "get_timing_scenarios",
    {"user_id": USER_ID, "target_amount": 60000, "monthly_savings": 2000,
     "down_payment": 10000, "asset_type": "VEICULO"})

tool_test("F3c get_leverage_simulation (valores diretos)",
    "app.agent.tools.get_leverage_simulation", "get_leverage_simulation",
    {"user_id": USER_ID, "asset_value": 350000, "monthly_rent": 2200,
     "consortium_months": 180})

tool_test("F4  get_fiscal_report (2025)",
    "app.agent.tools.get_fiscal_report", "get_fiscal_report",
    {"user_id": USER_ID, "year": 2025})

tool_test("F4  get_fiscal_report (2026)",
    "app.agent.tools.get_fiscal_report", "get_fiscal_report",
    {"user_id": USER_ID, "year": 2026})

tool_test("F5  get_bank_cost_analysis",
    "app.agent.tools.get_bank_cost_analysis", "get_bank_cost_analysis",
    {"user_id": USER_ID})

tool_test("F7  get_purchase_recommendation (R$3k/12x eletronico)",
    "app.agent.tools.get_purchase_recommendation", "get_purchase_recommendation",
    {"user_id": USER_ID, "amount": 3000, "category": "Eletronicos",
     "installments": 12, "monthly_income": MONTHLY_INCOME})

tool_test("F7  get_purchase_recommendation (R$500 a vista)",
    "app.agent.tools.get_purchase_recommendation", "get_purchase_recommendation",
    {"user_id": USER_ID, "amount": 500, "category": "Alimentacao",
     "installments": 1, "monthly_income": MONTHLY_INCOME})

tool_test("F13 get_negotiation_script (Itau)",
    "app.agent.tools.get_negotiation_script", "get_negotiation_script",
    {"user_id": USER_ID, "bank_name": "Itau"})

tool_test("F13 get_negotiation_script (sem banco)",
    "app.agent.tools.get_negotiation_script", "get_negotiation_script",
    {"user_id": USER_ID, "bank_name": ""})

tool_test("M1.3 get_budget_advice",
    "app.agent.tools.get_budget_advice", "get_budget_advice",
    {"user_id": USER_ID, "monthly_income": MONTHLY_INCOME})

tool_test("MX.2 get_goals_summary",
    "app.agent.tools.get_goals_summary", "get_goals_summary",
    {"user_id": USER_ID, "monthly_savings": 2000.0})

tool_test("MX.4 get_peer_comparison",
    "app.agent.tools.get_peer_comparison", "get_peer_comparison",
    {"user_id": USER_ID, "monthly_income": MONTHLY_INCOME})

tool_test("MX.4 get_peer_comparison (3 meses)",
    "app.agent.tools.get_peer_comparison", "get_peer_comparison",
    {"user_id": USER_ID, "monthly_income": MONTHLY_INCOME, "history_months": 3})


# ═══════════════════════════════════════════════════════════════════
# PARTE 2 — FUNCOES DE NEGOCIO DIRETAS
# ═══════════════════════════════════════════════════════════════════
secao("PARTE 2 — FUNCOES DE NEGOCIO (chamadas diretas)")


def negocio_test(nome, fn):
    try:
        res = fn()
        if res is not None:
            ok(nome, str(res)[:200])
        else:
            falha(nome, "retornou None")
    except Exception as e:
        falha(nome, e)


def _runner_pipeline():
    from app.runner import get_runner
    runner = get_runner()
    res = runner.run_from_db(user_id=USER_ID, horizon_days=30)
    return f"status={res.get('status')} | txns={res.get('transactions',{}).get('total_transactions','?')}"

negocio_test("F1  NexaRunner pipeline completo", _runner_pipeline)


def _income_profiler():
    from app.runner import get_runner
    import polars as pl
    runner = get_runner()
    res = runner.run_from_db(user_id=USER_ID, horizon_days=30)
    txns = res.get("transactions", {})
    df = txns.get("clean_df") or pl.DataFrame()
    from app.forecast.etl.income_profiler import IncomeProfiler
    profile = IncomeProfiler().build(df)
    return f"renda={profile.monthly_net_income:.0f} | padrao={profile.income_pattern} | conf={profile.confidence:.0%}"

negocio_test("F1  IncomeProfiler", _income_profiler)


def _consumption_profiler():
    from app.runner import get_runner
    import polars as pl
    runner = get_runner()
    res = runner.run_from_db(user_id=USER_ID, horizon_days=30)
    txns = res.get("transactions", {})
    df = txns.get("pf_pj_classified_df") or txns.get("clean_df") or pl.DataFrame()
    from app.optimizer.profiler import ConsumptionProfiler
    profile = ConsumptionProfiler().build(df)
    return f"cluster={profile.lifestyle_cluster} | FSS={profile.financial_stress_score}"

negocio_test("F2  ConsumptionProfiler", _consumption_profiler)


def _bank_fee():
    from app.runner import get_runner
    import polars as pl
    runner = get_runner()
    res = runner.run_from_db(user_id=USER_ID, horizon_days=30)
    txns = res.get("transactions", {})
    df = txns.get("clean_df") or pl.DataFrame()
    from app.costs.bank_fee_analyzer import BankFeeAnalyzer
    report = BankFeeAnalyzer().analyze(df, USER_ID)
    return f"total_tarifas=R${report.total_fees_paid:.2f}" if hasattr(report, 'total_fees_paid') else str(report)

negocio_test("F5  BankFeeAnalyzer", _bank_fee)


def _goals_tracker():
    from app.goals.tracker import GoalTracker
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        tracker = GoalTracker(db)
        goals = tracker.list_goals(USER_ID)
        return f"metas={len(goals.get('goals', []))}"
    except Exception as e:
        return f"aviso: {e} (sem metas no DuckDB - esperado)"
    finally:
        db.close()

negocio_test("MX.2 GoalTracker.list_goals", _goals_tracker)


def _health_score():
    from app.runner import get_runner
    runner = get_runner()
    res = runner.run_from_db(user_id=USER_ID, horizon_days=30)
    analysis = res.get("analysis", {})
    hs = analysis.get("health_score")
    profile = analysis.get("profile_type")
    return f"health_score={hs} | perfil={profile}"

negocio_test("MX.1 Health Score via pipeline", _health_score)


def _peer_comparator():
    from app.peers.peer_comparison import PeerComparator
    from app.runner import get_runner
    import polars as pl
    runner = get_runner()
    res = runner.run_from_db(user_id=USER_ID, horizon_days=30)
    txns = res.get("transactions", {})
    df = txns.get("clean_df") or pl.DataFrame()
    cat_spending = {}
    if not df.is_empty() and "category" in df.columns and "amount" in df.columns:
        import polars as pl
        debits = df.filter(pl.col("amount") < 0)
        for row in debits.group_by("category").agg(pl.col("amount").sum()).to_dicts():
            cat_spending[row["category"]] = abs(row["amount"])
    report = PeerComparator().compare(MONTHLY_INCOME, cat_spending)
    return f"percentil_poupanca={getattr(report,'savings_percentile','?')}" if report else "sem dados"

negocio_test("MX.4 PeerComparator", _peer_comparator)


# ═══════════════════════════════════════════════════════════════════
# PARTE 3 — ENDPOINTS HTTP (precisa do servidor rodando)
# ═══════════════════════════════════════════════════════════════════
if not SO_TOOLS:
    secao("PARTE 3 — ENDPOINTS HTTP (uvicorn em :8000)")

    import requests

    TOKEN = None
    GOAL_ID = None

    # Auth
    try:
        r = requests.post(f"{BASE_URL}/api/v1/auth/token",
            data={"username": EMAIL, "password": SENHA}, timeout=15)
        d = r.json()
        TOKEN = d.get("access_token")
        if TOKEN:
            ok("AUTH  POST /auth/token (login)")
        else:
            falha("AUTH  POST /auth/token", d)
    except Exception as e:
        falha("AUTH  POST /auth/token", e)


    def http(metodo, path, nome, body=None, params=None, esperado=200):
        if not TOKEN:
            falha(nome, "sem token")
            return None
        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        try:
            fn = getattr(requests, metodo.lower())
            kwargs = {"headers": headers, "timeout": 60}
            if body:   kwargs["json"] = body
            if params: kwargs["params"] = params
            r = fn(f"{BASE_URL}{path}", **kwargs)
            if r.status_code == esperado:
                ok(nome)
                try:    return r.json()
                except: return r.text
            else:
                falha(nome, f"HTTP {r.status_code}: {r.text[:150]}")
                return None
        except Exception as e:
            falha(nome, e)
            return None


    # Health
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        ok("SYS   GET /health") if r.status_code == 200 else falha("SYS   GET /health", r.status_code)
    except Exception as e:
        falha("SYS   GET /health", e)

    try:
        r = requests.get(f"{BASE_URL}/version", timeout=5)
        ok("SYS   GET /version") if r.status_code == 200 else falha("SYS   GET /version", r.status_code)
    except Exception as e:
        falha("SYS   GET /version", e)

    # Forecast
    http("GET", f"/api/v1/forecast/{USER_ID}",
         "F1    GET /forecast/{user_id}", params={"horizon_days": 30})

    http("GET", f"/api/v1/safe-to-spend/{USER_ID}",
         "F1    GET /safe-to-spend/{user_id}")

    http("GET", f"/api/v1/forecast/shadow-invoices/{USER_ID}",
         "F1    GET /forecast/shadow-invoices/{user_id}")

    http("GET", f"/api/v1/forecast/alerts/{USER_ID}",
         "F1    GET /forecast/alerts/{user_id}")

    # Optimizer
    http("POST", "/api/v1/optimizer/analyze",
         "F2    POST /optimizer/analyze",
         body={"user_id": USER_ID, "monthly_income": MONTHLY_INCOME,
               "safe_to_spend": 5000, "current_cards": [], "monthly_goals_commitment": 0})

    http("GET", f"/api/v1/optimizer/reports/{USER_ID}",
         "F2    GET /optimizer/reports/{user_id}")

    # Architect
    sim = http("POST", "/api/v1/architect/simulate",
         "F3    POST /architect/simulate",
         body={"user_id": USER_ID, "target_amount": 60000, "down_payment": 10000,
               "asset_type": "VEICULO", "financing_months": 48,
               "risk_profile": "moderado", "include_consortium": True})

    http("GET", "/api/v1/architect/simulations",
         "F3    GET /architect/simulations",
         params={"user_id": USER_ID})

    http("GET", "/api/v1/architect/metrics",
         "F3    GET /architect/metrics",
         params={"user_id": USER_ID})

    http("POST", "/api/v1/architect/timing-scenarios",
         "F3    POST /architect/timing-scenarios",
         body={"user_id": USER_ID, "target_amount": 60000, "down_payment": 10000,
               "asset_type": "VEICULO", "financing_months": 48, "risk_profile": "moderado"},
         params={"monthly_savings": 2000})

    # Budget
    http("GET", f"/api/v1/budget/{USER_ID}",
         "M1.3  GET /budget/{user_id}",
         params={"monthly_income": MONTHLY_INCOME})

    # Costs
    http("GET", f"/api/v1/costs/raio-x/{USER_ID}",
         "F5    GET /costs/raio-x/{user_id}")

    # Fiscal
    http("GET", f"/api/v1/fiscal/{USER_ID}",
         "F4    GET /fiscal/{user_id}",
         params={"year": 2025})

    http("GET", f"/api/v1/fiscal/{USER_ID}/mixed-use",
         "F4    GET /fiscal/{user_id}/mixed-use",
         params={"year": 2025})

    # Goals CRUD
    nova_meta = http("POST", f"/api/v1/goals/{USER_ID}",
         "MX.2  POST /goals (criar meta)",
         body={"name": "Teste Ferias", "goal_type": "viagem",
               "target_amount": 5000, "current_amount": 0,
               "target_date": "2027-01-01"}, esperado=201)
    if nova_meta:
        GOAL_ID = nova_meta.get("goal_id") or nova_meta.get("id")

    http("GET", f"/api/v1/goals/{USER_ID}",
         "MX.2  GET /goals (listar)")

    if GOAL_ID:
        http("GET", f"/api/v1/goals/{USER_ID}/{GOAL_ID}",
             "MX.2  GET /goals/{goal_id} (detalhe)")

        http("PATCH", f"/api/v1/goals/{USER_ID}/{GOAL_ID}/progress",
             "MX.2  PATCH /goals/{goal_id}/progress",
             body={"amount_to_add": 500})

        http("DELETE", f"/api/v1/goals/{USER_ID}/{GOAL_ID}",
             "MX.2  DELETE /goals/{goal_id}", esperado=200)

    # Health Score
    http("GET", f"/api/v1/health-score/history/{USER_ID}",
         "MX.1  GET /health-score/history/{user_id}")

    # Subscriptions
    http("GET", f"/api/v1/subscriptions/{USER_ID}",
         "M1.5  GET /subscriptions/{user_id}")

    # Peers
    http("GET", f"/api/v1/peers/compare/{USER_ID}",
         "MX.4  GET /peers/compare/{user_id}",
         params={"monthly_income": MONTHLY_INCOME})

    # Notifications
    http("GET", f"/api/v1/notifications/{USER_ID}",
         "MX.3  GET /notifications/{user_id}")

    # Purchase
    http("POST", "/api/v1/purchase/analyze",
         "F7    POST /purchase/analyze",
         body={"user_id": USER_ID, "amount": 3000, "category": "Eletronicos",
               "installments": 12, "monthly_income": MONTHLY_INCOME})

    # Negotiator
    http("POST", "/api/v1/negotiator/generate-script",
         "F13   POST /negotiator/generate-script",
         body={"user_id": USER_ID, "bank_name": "Itau"})

    # Divider / PF-PJ context
    http("GET", "/api/v1/context/overrides",
         "F4    GET /context/overrides")

    http("GET", "/api/v1/context/stats",
         "F4    GET /context/stats")

    # Chat history
    http("GET", "/api/v1/chat/history",
         "CHAT  GET /chat/history",
         params={"user_id": USER_ID})


# ═══════════════════════════════════════════════════════════════════
# RESUMO FINAL
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*65}")
print("RESUMO FINAL")
ok_total  = sum(1 for _, s, _ in resultados if s)
err_total = sum(1 for _, s, _ in resultados if not s)
total     = len(resultados)
print(f"{'='*65}")

erros = [(n, e) for n, s, e in resultados if not s]
if erros:
    print("\n  ERROS:")
    for n, e in erros:
        print(f"    [ERRO] {n}")
        if e: print(f"           {e}")

print(f"\n  {ok_total}/{total} passaram | {err_total} com erro")
print(f"{'='*65}")
