"""
scripts/debug/pluggy_field_audit.py

Audita os campos reais retornados pela Pluggy Sandbox para validar
os normalizers em app/architect/router.py.

Questão central:
    interestRates[].rate para loans/financings — é mensal ou anual?
    Se mensal → (1 + r)^12 - 1 está correto.
    Se anual  → estamos calculando (1 + 0.268)^12 - 1 ≈ 1600% — errado.

Uso:
    cd backend
    PLUGGY_CLIENT_ID=xxx PLUGGY_CLIENT_SECRET=yyy python scripts/debug/pluggy_field_audit.py

    Ou com as credenciais já no .env:
    python scripts/debug/pluggy_field_audit.py
"""

import json
import os
import sys

# Permite rodar a partir do diretório backend/ sem instalar o pacote
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import requests

# ── Credenciais ────────────────────────────────────────────────────────────────
try:
    from app.core.config import settings
    CLIENT_ID     = settings.PLUGGY_CLIENT_ID     or os.getenv("PLUGGY_CLIENT_ID", "")
    CLIENT_SECRET = settings.PLUGGY_CLIENT_SECRET or os.getenv("PLUGGY_CLIENT_SECRET", "")
    BASE_URL      = settings.PLUGGY_BASE_URL
except Exception:
    CLIENT_ID     = os.getenv("PLUGGY_CLIENT_ID", "")
    CLIENT_SECRET = os.getenv("PLUGGY_CLIENT_SECRET", "")
    BASE_URL      = "https://api.pluggy.ai"

if not CLIENT_ID or not CLIENT_SECRET:
    print("ERRO: PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET não encontrados.")
    print("  Defina no backend/.env ou como variável de ambiente.")
    sys.exit(1)


# ── Helpers ────────────────────────────────────────────────────────────────────
def _pprint(label: str, data):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _highlight(label: str, value, note: str = ""):
    marker = "  >>>  "
    print(f"{marker}{label}: {value!r}  {note}")


# ── Auth ───────────────────────────────────────────────────────────────────────
def authenticate() -> str:
    resp = requests.post(
        f"{BASE_URL}/auth",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"clientId": CLIENT_ID, "clientSecret": CLIENT_SECRET},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if "apiKey" not in data:
        raise RuntimeError(f"Auth falhou: {data}")
    print(f"[OK] Autenticado — apiKey obtida")
    return data["apiKey"]


def headers(token: str) -> dict:
    return {
        "X-API-KEY": token,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# ── Sandbox item ───────────────────────────────────────────────────────────────
def create_sandbox_item(token: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/items",
        json={
            "connectorId": 0,
            "parameters": {"user": "user-ok", "password": "password-ok"},
        },
        headers=headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    item_id = data.get("id") or data.get("item", {}).get("id")
    if not item_id:
        raise RuntimeError(f"Não encontrou item_id na resposta: {data}")
    print(f"[OK] Sandbox item criado: {item_id}")
    return item_id


# ── Fetch endpoints ────────────────────────────────────────────────────────────
def fetch(token: str, path: str, params: dict) -> dict:
    resp = requests.get(
        f"{BASE_URL}/{path}",
        params=params,
        headers=headers(token),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ── Análise de campos críticos ─────────────────────────────────────────────────
def audit_investments(data: dict):
    results = data.get("results") or data.get("items") or []
    print(f"\n[investments] {len(results)} itens")
    for i, inv in enumerate(results[:3]):  # mostrar até 3
        print(f"\n  --- item {i} ---")
        for field in ("type", "subtype", "balance", "amount", "annualRate",
                      "quantity", "date", "dueDate", "code", "name"):
            if field in inv:
                _highlight(field, inv[field])
        # Campos extras não mapeados
        mapped = {"type","subtype","balance","amount","annualRate","date","dueDate"}
        extras = {k: v for k, v in inv.items() if k not in mapped and not isinstance(v, dict)}
        if extras:
            print(f"       outros campos: {list(extras.keys())}")


def audit_loans(data: dict):
    results = data.get("results") or data.get("items") or []
    print(f"\n[loans] {len(results)} itens")
    for i, loan in enumerate(results[:3]):
        print(f"\n  --- item {i} ---")
        _highlight("type", loan.get("type"))
        _highlight("monthlyPaymentAmount", loan.get("monthlyPaymentAmount"))
        _highlight("totalAmount", loan.get("totalAmount"))
        _highlight("fees", loan.get("fees"))

        # interestRates — o campo crítico
        ir = loan.get("interestRates") or []
        if ir:
            print(f"\n  [interestRates] — {len(ir)} entradas:")
            for r in ir:
                rate_val  = r.get("rate")
                rate_type = r.get("type")
                rate_unit = r.get("unit") or r.get("frequency") or r.get("period")
                _highlight(
                    f"  rate={rate_val} type={rate_type} unit/frequency/period={rate_unit}",
                    "",
                    _interpret_rate(rate_val, rate_unit, rate_type),
                )
            # Mostrar objeto completo para não perder nada
            print("  [interestRates raw]:", json.dumps(ir, indent=4, ensure_ascii=False, default=str))
        else:
            print("  [interestRates]: AUSENTE")

        # fees — alternativa ao interestRates
        fees = loan.get("fees") or {}
        if fees:
            print(f"  [fees raw]: {json.dumps(fees, indent=4, default=str)}")

        instalments = loan.get("instalments") or {}
        if instalments:
            print(f"  [instalments]: {instalments}")


def audit_financings(data: dict):
    results = data.get("results") or data.get("items") or []
    print(f"\n[financings] {len(results)} itens")
    for i, fin in enumerate(results[:3]):
        print(f"\n  --- item {i} ---")
        _highlight("type", fin.get("type"))
        _highlight("subtype", fin.get("subtype"))
        _highlight("monthlyPaymentAmount", fin.get("monthlyPaymentAmount"))

        ir = fin.get("interestRates") or []
        if ir:
            print(f"\n  [interestRates] — {len(ir)} entradas:")
            for r in ir:
                rate_val  = r.get("rate")
                rate_unit = r.get("unit") or r.get("frequency") or r.get("period")
                rate_type = r.get("type")
                _highlight(
                    f"  rate={rate_val} unit={rate_unit} type={rate_type}",
                    "",
                    _interpret_rate(rate_val, rate_unit, rate_type),
                )
            print("  [interestRates raw]:", json.dumps(ir, indent=4, ensure_ascii=False, default=str))
        else:
            print("  [interestRates]: AUSENTE")

        fees = fin.get("fees") or {}
        if fees:
            print(f"  [fees raw]: {json.dumps(fees, indent=4, default=str)}")


def _interpret_rate(rate_val, unit, rate_type) -> str:
    if rate_val is None:
        return "(sem valor)"
    r = float(rate_val)
    unit_str = str(unit or "").upper()
    type_str = str(rate_type or "").upper()

    # Inferência pela magnitude
    if r > 1.0:
        magnitude_note = f"⚠️  r={r:.4f} > 1 — parece percentual (ex: 2.5 = 2.5%), não decimal"
    elif r > 0.50:
        magnitude_note = f"⚠️  r={r:.4f} — provavelmente taxa anual em decimal (ex: 0.268 = 26.8% a.a.)"
    elif r > 0.10:
        magnitude_note = f"→ provável taxa ANUAL em decimal (ex: {r:.3f} = {r*100:.1f}% a.a.)"
    elif r > 0.008:
        magnitude_note = f"→ ambíguo: pode ser MENSAL ({r:.4f} = {(1+r)**12-1:.2%} a.a.) ou ANUAL ({r*100:.2f}% a.a.)"
    else:
        magnitude_note = f"→ provável taxa MENSAL em decimal ({r:.4f} = {(1+r)**12-1:.2%} a.a.)"

    unit_note = f"[unit/frequency='{unit_str}']" if unit_str else "[unit=ausente]"
    return f"{magnitude_note} {unit_note}"


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  PLUGGY FIELD AUDIT — validação de normalizers")
    print("="*60)

    token   = authenticate()
    item_id = create_sandbox_item(token)

    # Investments
    print("\n\n[1/3] Buscando /investments ...")
    inv_data = fetch(token, "investments", {"itemId": item_id})
    _pprint("investments — payload completo (primeiro item)", (inv_data.get("results") or [{}])[:1])
    audit_investments(inv_data)

    # Loans
    print("\n\n[2/3] Buscando /loans ...")
    try:
        loan_data = fetch(token, "loans", {"itemId": item_id})
        _pprint("loans — payload completo (primeiro item)", (loan_data.get("results") or [{}])[:1])
        audit_loans(loan_data)
    except Exception as e:
        print(f"  [loans] ERRO ou endpoint indisponível: {e}")

    # Financings
    print("\n\n[3/3] Buscando /financings ...")
    try:
        fin_data = fetch(token, "financings", {"itemId": item_id})
        _pprint("financings — payload completo (primeiro item)", (fin_data.get("results") or [{}])[:1])
        audit_financings(fin_data)
    except Exception as e:
        print(f"  [financings] ERRO ou endpoint indisponível: {e}")

    # Accounts (para confirmar estrutura já conhecida)
    print("\n\n[bônus] Confirmando /accounts ...")
    acc_data = fetch(token, "accounts", {"itemId": item_id})
    accounts = acc_data.get("results") or []
    print(f"  {len(accounts)} contas")
    for acc in accounts[:2]:
        _highlight("id", acc.get("id"))
        _highlight("type", acc.get("type"))
        _highlight("balance", acc.get("balance"))
        _highlight("currencyCode", acc.get("currencyCode"))

    print("\n\n" + "="*60)
    print("  RESUMO — o que corrigir nos normalizers")
    print("="*60)
    print("""
  Olhe as linhas com ⚠️  acima para identificar:

  1. Se rate > 0.50 → taxa já é anual — NÃO aplicar (1+r)^12-1.
     Fix: usar diretamente como cet_annual = float(rate).

  2. Se rate < 0.02 e unit contém 'MONTH' → taxa mensal.
     Fix: manter (1 + rate)^12 - 1.

  3. Se rate aparece como percentual (ex: 2.5 em vez de 0.025):
     Fix: dividir por 100 antes de converter.

  4. Se /loans ou /financings retornar 404/erro:
     O sandbox connector 0 pode não incluir esses produtos.
     Verificar na documentação Pluggy quais connectors têm loans/financings.
    """)


if __name__ == "__main__":
    main()
