#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://codigos-nexa-production.up.railway.app/api/v1}"
EMAIL="${EMAIL:-teste@nexa.com}"
PASSWORD="${PASSWORD:-teste123}"
OUT_DIR="${OUT_DIR:-./backend/docs/smoke-online}"
MONTHLY_INCOME="${MONTHLY_INCOME:-9800}"

mkdir -p "$OUT_DIR"

echo "[1/4] Login em $BASE_URL ..."
LOGIN_JSON=$(curl -sS -X POST "$BASE_URL/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=$EMAIL" \
  --data-urlencode "password=$PASSWORD")

TOKEN=$(printf '%s' "$LOGIN_JSON" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
USER_ID=$(printf '%s' "$LOGIN_JSON" | sed -n 's/.*"user_id":"\([^"]*\)".*/\1/p')

if [[ -z "$TOKEN" || -z "$USER_ID" ]]; then
  echo "Falha no login. Resposta completa:"
  echo "$LOGIN_JSON"
  exit 1
fi

echo "[2/4] user_id detectado: $USER_ID"

auth_header=("-H" "Authorization: Bearer $TOKEN")

call_get() {
  local name="$1"
  local path="$2"
  local out="$OUT_DIR/${name}.json"
  local status

  status=$(curl -sS -o "$out" -w "%{http_code}" "${auth_header[@]}" "$BASE_URL$path")
  echo "$name => HTTP $status"
  if [[ "$status" -ge 400 ]]; then
    echo "  erro salvo em $out"
  fi
}

call_post_json() {
  local name="$1"
  local path="$2"
  local json="$3"
  local out="$OUT_DIR/${name}.json"
  local status

  status=$(curl -sS -o "$out" -w "%{http_code}" -X POST "$BASE_URL$path" \
    "${auth_header[@]}" -H "Content-Type: application/json" -d "$json")
  echo "$name => HTTP $status"
  if [[ "$status" -ge 400 ]]; then
    echo "  erro salvo em $out"
  fi
}

echo "[3/4] Executando endpoints chave..."
call_get forecast "/forecast/$USER_ID"
call_get safe_to_spend "/safe-to-spend/$USER_ID"
call_get transactions "/transactions/$USER_ID"
call_get budget "/budget/$USER_ID?monthly_income=$MONTHLY_INCOME"
call_get subscriptions "/subscriptions/$USER_ID"
call_get health_score_history "/health-score/history/$USER_ID"
call_get goals "/goals/$USER_ID"
call_get notifications "/notifications/$USER_ID"
call_get peers_compare "/peers/compare/$USER_ID?monthly_income=$MONTHLY_INCOME"
call_get architect_metrics "/architect/metrics?user_id=$USER_ID"
call_get architect_list "/architect/simulations?user_id=$USER_ID"
call_get context_overrides "/context/overrides/$USER_ID"
call_get fiscal_report "/fiscal-report/$USER_ID"

call_post_json optimizer_analyze "/optimizer/analyze" "{\"user_id\":\"$USER_ID\",\"monthly_income\":$MONTHLY_INCOME}"
call_get optimizer_portfolio "/optimizer/portfolio/$USER_ID?max_cards=3&monthly_income=$MONTHLY_INCOME"
call_get optimizer_opportunity_cost "/optimizer/opportunity-cost?current_card_id=nubank_gold&months=3&user_id=$USER_ID"
call_post_json purchase_analyze "/purchase/analyze" "{\"user_id\":\"$USER_ID\",\"amount\":8999.0,\"category\":\"Eletronicos\",\"installments\":10,\"monthly_income\":$MONTHLY_INCOME}"
call_post_json negotiator_script "/negotiator/generate-script" "{\"user_id\":\"$USER_ID\",\"bank_name\":\"Nubank\",\"fee_type\":\"anuidade\"}"
call_post_json chat "/chat/" "{\"user_id\":\"$USER_ID\",\"message\":\"Me explique meu safe-to-spend de hoje com base no meu fluxo de caixa\"}"

echo "[4/4] Concluido. JSONs em: $OUT_DIR"
echo "Sugestao: abrir os JSONs com erro HTTP >= 400 para mapear gaps de payload/auth/schema."
