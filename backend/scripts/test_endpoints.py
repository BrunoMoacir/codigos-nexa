"""
Testa todos os endpoints do Optimizer. Requer backend em http://localhost:8000.
"""
import sys
import requests

BASE = "http://localhost:8000/api/v1"
EMAIL = "teste@nexa.com"
PASSWORD = "Teste123!"
USER_ID = "054b2734-bf06-4acb-8720-65096d980d68"


def login():
    # OAuth2 form-encoded
    r = requests.post(
        f"{BASE}/auth/token",
        data={"username": EMAIL, "password": PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, f"Login falhou: {r.status_code} {r.text}"
    token = r.json()["access_token"]
    print(f"Login OK | token: {token[:40]}...")
    return token


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_cards():
    print("\n=== 1. CARDS (publico) ===")
    r = requests.get(f"{BASE}/optimizer/cards")
    print(f"Status: {r.status_code} | Total: {r.json().get('total', '?')} cartoes")


def test_promotions(token):
    print("\n=== 2. PROMOTIONS ===")
    r = requests.get(f"{BASE}/optimizer/promotions", headers=headers(token))
    print(f"Status: {r.status_code} | Total: {r.json().get('total', '?')} promocoes")


def test_roi(token):
    print("\n=== 3. ROI (com monthly_spend manual) ===")
    r = requests.get(
        f"{BASE}/optimizer/roi/nubank-roxinho",
        params={"user_id": USER_ID, "monthly_spend": 3000},
        headers=headers(token),
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        print(f"  Cartao: {d.get('card_name')}")
        print(f"  Veredicto: {d.get('verdict')}")
        print(f"  Reward anual: R$ {d.get('reward_value_generated')}")
        print(f"  Anuidade paga: R$ {d.get('annuity_paid')}")
        print(f"  ROI liquido: R$ {d.get('net_roi')}")
    else:
        print(f"  Erro: {r.text}")


def test_roi_sem_spend(token):
    print("\n=== 4. ROI (com historico real - sem monthly_spend) ===")
    r = requests.get(
        f"{BASE}/optimizer/roi/nubank-roxinho",
        params={"user_id": USER_ID},
        headers=headers(token),
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        print(f"  Cartao: {d.get('card_name')}")
        print(f"  Veredicto: {d.get('verdict')}")
        print(f"  Reward anual: R$ {d.get('reward_value_generated')}")
        print(f"  ROI liquido: R$ {d.get('net_roi')}")
    else:
        print(f"  Erro: {r.text}")


def test_opportunity_cost(token):
    print("\n=== 5. OPPORTUNITY COST ===")
    r = requests.get(
        f"{BASE}/optimizer/opportunity-cost",
        params={"user_id": USER_ID, "current_card_id": "nubank-roxinho", "months": 3},
        headers=headers(token),
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        print(f"  Cartao atual: {d.get('current_card_name')}")
        print(f"  Total gasto no periodo: R$ {d.get('total_spent')}")
        print(f"  Reward atual: R$ {d.get('current_card_reward_value')}")
        best = d.get("best_opportunity") or {}
        print(f"  Melhor alternativa: {best.get('card_name')}")
        print(f"  Diferenca: R$ {best.get('difference')}")
        print(f"  Diferenca anualizada: R$ {best.get('difference_annualized')}")
        opps = d.get("opportunities", [])
        print(f"  Total oportunidades: {len(opps)}")
    else:
        print(f"  Erro: {r.text}")


def test_portfolio(token, max_cards=3):
    print(f"\n=== 6. PORTFOLIO MULTI-CARD (max_cards={max_cards}) ===")
    r = requests.get(
        f"{BASE}/optimizer/portfolio/{USER_ID}",
        params={"max_cards": max_cards},
        headers=headers(token),
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        print(f"  Total cartoes: {d.get('total_cards')}")
        print(f"  Retorno anual total: R$ {d.get('total_annual_return')}")
        print(f"  Custo anuidades: R$ {d.get('total_annuity_cost')}")
        print(f"  Ganho liquido: R$ {d.get('net_annual_gain')}")
        print(f"  Vs melhor unico: R$ {d.get('vs_single_best')}")
        print(f"  Data quality: {d.get('data_quality')}")
        for c in d.get("cards", []):
            print(f"    - {c.get('card_name')} | categorias: {c.get('assigned_categories')} | liquido: R$ {c.get('net_annual')}")
    else:
        print(f"  Erro: {r.text}")


def test_analyze(token):
    print("\n=== 7. ANALYZE (POST) ===")
    r = requests.post(
        f"{BASE}/optimizer/analyze",
        json={"user_id": USER_ID},
        headers=headers(token),
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        recs = d.get("recommendations", [])
        print(f"  Total recomendacoes: {len(recs)}")
        if recs:
            top = recs[0]
            print(f"  Top pick: {top.get('card_name')} | score: {top.get('score')}")
    else:
        print(f"  Erro: {r.text[:300]}")


def main():
    print("=== TESTE DE ENDPOINTS NEXA OPTIMIZER ===")
    try:
        token = login()
    except Exception as e:
        print(f"ERRO no login: {e}")
        sys.exit(1)

    test_cards()
    test_promotions(token)
    test_roi(token)
    test_roi_sem_spend(token)
    test_opportunity_cost(token)
    test_portfolio(token, max_cards=3)
    test_portfolio(token, max_cards=1)
    test_analyze(token)
    print("\n=== FIM DOS TESTES ===")


if __name__ == "__main__":
    main()
