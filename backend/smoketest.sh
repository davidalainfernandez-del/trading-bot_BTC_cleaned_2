#!/usr/bin/env bash
set -euo pipefail

BASE="http://localhost:5000"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
pass(){ echo -e "${GREEN}PASS${NC}  $*"; }
fail(){ echo -e "${RED}FAIL${NC}  $*"; exit 1; }
warn(){ echo -e "${YELLOW}WARN${NC}  $*"; }

need_jq=1
if ! command -v jq >/dev/null 2>&1; then need_jq=0; warn "jq absent — les réponses ne seront pas jolies mais on continue."; fi

# --- helpers ---
get_json() {
  local url="$1"
  if [[ $need_jq -eq 1 ]]; then
    curl -sS "$url" | jq .
  else
    curl -sS "$url"
  fi
}
get_code() {
  local method="$1" url="$2" data="${3:-}"
  if [[ "$method" == "GET" ]]; then
    curl -sS -o /dev/null -w "%{http_code}" "$url"
  else
    curl -sS -o /dev/null -w "%{http_code}" -X "$method" -H 'Content-Type: application/json' -d "$data" "$url"
  fi
}

echo "== Smoke tests sur $BASE =="

# 1) Health
code=$(get_code GET "$BASE/api/health")
[[ "$code" == "200" ]] || fail "/api/health code=$code"
get_json "$BASE/api/health" >/dev/null || true
pass "/api/health"

# 2) Prix
for r in \
  "$BASE/api/price/ohlc?symbol=BTCUSDT&interval=1m&limit=1" \
  "$BASE/api/price/ticker?symbol=BTCUSDT" \
  "$BASE/api/price/avg20?symbol=BTCUSDT"
do
  code=$(get_code GET "$r")
  [[ "$code" == "200" ]] || fail "$r code=$code"
  get_json "$r" >/dev/null || true
done
pass "Endpoints prix OK (ohlc/ticker/avg20)"

# 3) Décisions
for r in \
  "$BASE/api/decisions/now?symbol=BTCUSDT" \
  "$BASE/api/decisions/recent?symbol=BTCUSDT&limit=5"
do
  code=$(get_code GET "$r")
  [[ "$code" == "200" ]] || fail "$r code=$code"
  get_json "$r" >/dev/null || true
done
pass "Décisions now/recent OK"

# 4) Autotrade & ML
for r in \
  "$BASE/api/autotrade_state" \
  "$BASE/api/ml/status?symbol=BTCUSDT"
do
  code=$(get_code GET "$r")
  [[ "$code" == "200" ]] || fail "$r code=$code"
done
pass "Autotrade & ML OK"

# 5) Paramètres (lecture)
code=$(get_code GET "$BASE/api/params")
if [[ "$code" == "200" ]]; then
  get_json "$BASE/api/params" >/dev/null || true
  pass "/api/params"
else
  warn "/api/params indisponible (code=$code) — on continue."
fi

# 6) Paramètres (mise à jour) – essaie GET si POST refusé
update_qs="$BASE/api/params/update?PREFER_MAKER=true&MAKER_FEE_BUY=0.00075&MAKER_FEE_SELL=0.00075&TAKER_FEE_BUY=0.00075&TAKER_FEE_SELL=0.00075&SLIPPAGE=0.0005&BUFFER=0.0005"
code_post=$(get_code POST "$BASE/api/params/update" '{"PREFER_MAKER":true}')
if [[ "$code_post" == "405" ]]; then
  code_get=$(get_code GET "$update_qs")
  if [[ "$code_get" == "200" ]]; then
    pass "params/update via GET"
  else
    warn "params/update non accessible (POST=405, GET=$code_get)."
  fi
elif [[ "$code_post" == "200" ]]; then
  pass "params/update via POST"
else
  warn "params/update code POST=$code_post"
fi

# 7) Achat manuel – GET si POST refusé
code_post=$(get_code POST "$BASE/api/manual/buy" '{"usdt":50}')
if [[ "$code_post" == "405" ]]; then
  code_get=$(get_code GET "$BASE/api/manual/buy?usdt=50")
  if [[ "$code_get" == "200" ]]; then
    pass "manual/buy via GET"
  else
    warn "manual/buy non accessible (POST=405, GET=$code_get)."
  fi
elif [[ "$code_post" == "200" ]]; then
  pass "manual/buy via POST"
else
  warn "manual/buy code POST=$code_post"
fi

# 8) Métriques (facultatif)
for r in "$BASE/metrics" "$BASE/api/metrics"; do
  code=$(get_code GET "$r")
  if [[ "$code" == "200" ]]; then
    pass "Métriques exposées sur $r"
    break
  fi
done

echo -e "${GREEN}== SMOKE TESTS : OK ==${NC}"
