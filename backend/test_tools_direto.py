"""
Teste direto das tools/funcoes reais do projeto - sem LLM, sem API de banco.
Usa o user mock ja seedado no DuckDB.
"""
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

USER_ID = "df9564fb-60f5-4202-8b47-a72f1877aba7"
MONTHLY_INCOME = 12500.0

resultados = []


def limpar(texto):
    return str(texto).encode("ascii", errors="replace").decode("ascii")


def testar(nome, fn):
    print(f"\n{'-'*60}")
    print(f">> {nome}")
    try:
        resultado = fn()
        if resultado and resultado != "":
            trecho = limpar(str(resultado))[:280]
            print(f"OK -> {trecho}")
            resultados.append((nome, True, None))
        else:
            print(f"AVISO: retornou vazio")
            resultados.append((nome, False, "Retorno vazio"))
    except Exception as e:
        print(f"ERRO: {limpar(e)}")
        resultados.append((nome, False, limpar(str(e))[:120]))


# 1. Perfil Financeiro
def _perfil():
    from app.agent.tools.get_user_profile_context import get_user_profile_context
    return get_user_profile_context.invoke({"user_id": USER_ID})

testar("F0 - Perfil Financeiro", _perfil)


# 2. Forecast / Safe-to-Spend
def _forecast():
    from app.agent.tools.get_financial_forecast import get_financial_forecast
    return get_financial_forecast.invoke({"user_id": USER_ID, "monthly_income": MONTHLY_INCOME})

testar("F1 - Forecast + Safe-to-Spend", _forecast)


# 3. Orcamento 50/30/20
def _budget():
    from app.agent.tools.get_budget_advice import get_budget_advice
    return get_budget_advice.invoke({"user_id": USER_ID, "monthly_income": MONTHLY_INCOME})

testar("M1.3 - Orcamento 50/30/20", _budget)


# 4. Otimizador de Cartoes
def _cartao():
    from app.agent.tools.get_card_optimization import get_card_optimization
    return get_card_optimization.invoke({"user_id": USER_ID, "monthly_income": MONTHLY_INCOME})

testar("F2 - Otimizador de Cartoes", _cartao)


# 5. Alertas de Gastos
def _alertas():
    from app.agent.tools.get_spending_alerts import get_spending_alerts
    return get_spending_alerts.invoke({"user_id": USER_ID, "monthly_income": MONTHLY_INCOME})

testar("F1b - Alertas de Gastos", _alertas)


# 6. Metas Financeiras
def _metas():
    from app.agent.tools.get_goals_summary import get_goals_summary
    return get_goals_summary.invoke({"user_id": USER_ID, "monthly_savings": 2000.0})

testar("MX.2 - Metas Financeiras", _metas)


# 7. Simulacao de Financiamento
def _financiamento():
    from app.agent.tools.get_financing_simulation import get_financing_simulation
    return get_financing_simulation.invoke({
        "user_id": USER_ID, "target_amount": 60000, "down_payment": 10000,
        "asset_type": "VEICULO", "financing_months": 48
    })

testar("F3 - Arquiteto Financiamento", _financiamento)


# 8. Compra Inteligente
def _compra():
    from app.agent.tools.get_purchase_recommendation import get_purchase_recommendation
    return get_purchase_recommendation.invoke({
        "user_id": USER_ID, "amount": 3000, "category": "Eletronicos",
        "installments": 12, "monthly_income": MONTHLY_INCOME
    })

testar("F7 - Compra Inteligente", _compra)


# 9. Custos Bancarios
def _custos():
    from app.agent.tools.get_bank_cost_analysis import get_bank_cost_analysis
    return get_bank_cost_analysis.invoke({"user_id": USER_ID})

testar("F5 - Raio-X Custos Bancarios", _custos)


# 10. Negociador
def _negociacao():
    from app.agent.tools.get_negotiation_script import get_negotiation_script
    return get_negotiation_script.invoke({"user_id": USER_ID, "bank_name": "Itau"})

testar("F13 - Script de Negociacao", _negociacao)


# 11. Relatorio Fiscal PJ/MEI
def _fiscal():
    from app.agent.tools.get_fiscal_report import get_fiscal_report
    return get_fiscal_report.invoke({"user_id": USER_ID, "year": 2025})

testar("F4 - Relatorio Fiscal MEI/PJ", _fiscal)


# 12. Comparacao com Pares
def _pares():
    from app.agent.tools.get_peer_comparison import get_peer_comparison
    return get_peer_comparison.invoke({"user_id": USER_ID, "monthly_income": MONTHLY_INCOME})

testar("MX.4 - Comparacao com Pares", _pares)


# 13. Timing de Compra
def _timing():
    from app.agent.tools.get_timing_scenarios import get_timing_scenarios
    return get_timing_scenarios.invoke({
        "user_id": USER_ID, "target_amount": 60000, "monthly_savings": 2000,
        "down_payment": 10000, "asset_type": "VEICULO"
    })

testar("F3b - Timing de Compra", _timing)


# Resumo Final
print(f"\n{'='*60}")
print("RESUMO FINAL")
ok = sum(1 for _, s, _ in resultados if s)
total = len(resultados)
print(f"{'='*60}")
for nome, sucesso, erro in resultados:
    status = "OK  " if sucesso else "ERRO"
    detalhe = f" -> {erro[:70]}" if erro else ""
    print(f"  [{status}] {nome}{detalhe}")
print(f"{'='*60}")
print(f"{ok}/{total} tools funcionando")
