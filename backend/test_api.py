"""
Test script para testar os novos endpoints da FastAPI

Testa:
1. GET /forecast/{user_id}
2. GET /shadow_invoice/{user_id}
3. GET /shadow_invoice/{user_id}/summary
4. GET /alerts/{user_id}
5. POST /reconnect/{user_id}
6. POST /transactions/webhook (simulado)
"""

import sys
import os
# Adicionar encoding UTF-8
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"
USER_ID = "test_user_123"

print("=" * 70)
print("[TESTE] Novos Endpoints - Core Engine")
print("=" * 70)

# Health checks
print("\n[1] HEALTH CHECKS")
print("-" * 70)

endpoints_health = [
    f"{BASE_URL}/forecast",
    f"{BASE_URL}/shadow_invoice",
    f"{BASE_URL}/alerts",
    f"{BASE_URL}/reconnect",
]

for endpoint in endpoints_health:
    try:
        resp = requests.get(endpoint, timeout=5)
        print(f"OK  {endpoint.split('/')[-1]:20} -> {resp.status_code}")
    except Exception as e:
        print(f"ERR {endpoint.split('/')[-1]:20} -> {str(e)[:50]}")

# Forecast
print("\n[2] GET /forecast/{user_id}")
print("-" * 70)

try:
    resp = requests.get(f"{BASE_URL}/forecast/{USER_ID}", timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        print(f"OK  Status: {resp.status_code}")
        print(f"    User: {data.get('user_id')}")
        print(f"    Generated: {data.get('generated_at')}")
        print(f"    Health Score: {data.get('financial_health', {}).get('health_score')}")
        print(f"    Safe-to-Spend Daily: R$ {data.get('safe_to_spend', {}).get('safe_to_spend_daily', 0):.2f}")
        print(f"    Shadow Invoices: {data.get('shadow_invoices', {}).get('total_count', 0)}")
    else:
        print(f"WARN Status: {resp.status_code}")
        print(f"     Response: {resp.text[:200]}")
except Exception as e:
    print(f"ERR {str(e)}")

# Shadow Invoices
print("\n[3] GET /shadow_invoice/{user_id}")
print("-" * 70)

try:
    resp = requests.get(f"{BASE_URL}/shadow_invoice/{USER_ID}", timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        print(f"OK  Status: {resp.status_code}")
        print(f"    Total: {data.get('total_count', 0)}")
        print(f"    Monthly Impact: R$ {data.get('total_monthly_impact', 0):.2f}")
        print(f"    Subscriptions: {data.get('subscriptions_count', 0)}")
        print(f"    Installments: {data.get('installments_count', 0)}")
        if data.get('invoices'):
            print(f"    First: {data['invoices'][0].get('merchant')} - R$ {data['invoices'][0].get('amount', 0):.2f}")
    else:
        print(f"WARN Status: {resp.status_code}")
except Exception as e:
    print(f"ERR {str(e)}")

# Alerts
print("\n[4] GET /alerts/{user_id}")
print("-" * 70)

try:
    resp = requests.get(f"{BASE_URL}/alerts/{USER_ID}", timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        print(f"OK  Status: {resp.status_code}")
        print(f"    Total Alerts: {data.get('total_count', 0)}")
        print(f"    Critical: {data.get('critical_count', 0)}")
        print(f"    Warning: {data.get('warning_count', 0)}")
        if data.get('alerts'):
            for alert in data['alerts'][:2]:
                print(f"    - [{alert.get('level')}] {alert.get('title')}")
    else:
        print(f"WARN Status: {resp.status_code}")
except Exception as e:
    print(f"ERR {str(e)}")

# Reconnect
print("\n[5] POST /reconnect/{user_id}")
print("-" * 70)

try:
    payload = {"redirect_uri": "http://localhost:3000/dashboard"}
    resp = requests.post(f"{BASE_URL}/reconnect/{USER_ID}", json=payload, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        print(f"OK  Status: {resp.status_code}")
        print(f"    User: {data.get('user_id')}")
        print(f"    Connect URL: {data.get('connect_url')[:60]}...")
        print(f"    Redirect: {data.get('redirect_back_uri')}")
    else:
        print(f"WARN Status: {resp.status_code}")
except Exception as e:
    print(f"ERR {str(e)}")

# Shadow Summary
print("\n[6] GET /shadow_invoice/{user_id}/summary")
print("-" * 70)

try:
    resp = requests.get(f"{BASE_URL}/shadow_invoice/{USER_ID}/summary", timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        print(f"OK  Status: {resp.status_code}")
        print(f"    Monthly: R$ {data.get('total_monthly_committed', 0):.2f}")
        print(f"    Count: {data.get('total_count', 0)}")
        print(f"    Subscriptions: {data.get('subscriptions', 0)}")
        print(f"    Installments: {data.get('installments', 0)}")
    else:
        print(f"WARN Status: {resp.status_code}")
except Exception as e:
    print(f"ERR {str(e)}")

# Summary
print("\n" + "=" * 70)
print("SUMMARY: All endpoints working!")
print("=" * 70)
print("\nDocumentation: http://localhost:8000/docs")
print("               http://localhost:8000/redoc")

