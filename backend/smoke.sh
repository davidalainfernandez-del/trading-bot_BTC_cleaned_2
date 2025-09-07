#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://localhost:5000}"
JQ="${JQ:-jq}"

pass(){ echo "✅ PASS: $*"; }
fail(){ echo "❌ FAIL: $*"; exit 1; }

req(){
  local path="$1" cond="$2" desc="$3"
  local tmp; tmp="$(mktemp)"
  local code
  code="$(curl -sS "$BASE$path" -w "%{http_code}" -o "$tmp" || true)"
  if [[ "$code" != "200" ]]; then
    echo "— HTTP $code — body:"; cat "$tmp"; rm -f "$tmp"
    fail "$desc ($path) HTTP $code"
  fi
  # JSON valide ?
  if ! $JQ -e . < "$tmp" >/dev/null 2>&1; then
    echo "— body:"; cat "$tmp"; rm -f "$tmp"
    fail "$desc ($path) JSON invalide"
  fi
  # NaN/Infinity interdits en JSON strict
  if grep -Eq '(^|[^A-Za-z])(NaN|Infinity|-Infinity)($|[^A-Za-z])' "$tmp"; then
    echo "— body:"; cat "$tmp"; rm -f "$tmp"
    fail "$desc ($path) contient NaN/Infinity"
  fi
  # Assertion jq
  if ! $JQ -e "$cond" < "$tmp" >/dev/null 2>&1; then
    echo "— body:"; cat "$tmp"; rm -f "$tmp"
    fail "$desc ($path) assertion jq échouée: $cond"
  fi
  rm -f "$tmp"
  pass "$desc ($path)"
}

echo "### BASE = $BASE"
echo "=== Liveness / Readiness ==="
req "/api/health" '.ok==true and ((.last_tick_age_s|type)=="number" or .last_tick_age_s==null)' "liveness"
req "/api/health/deep" '.ok==true and .db_ok==true and ((.btc_last|type)=="number")' "readiness"

echo "=== Autotrade ==="
req "/api/autotrade_state" 'type=="object"' "autotrade_state"

echo "=== Prix ==="
req "/api/price/ticker?symbol=BTCUSDT" '([.price,.last,.value] | map(select(type=="number")) | length) >= 1' "price/ticker BTCUSDT"
req "/api/price/avg20?symbol=BTCUSDT"   '([.avg,.avg20,.price] | map(select(type=="number")) | length) >= 1' "price/avg20 BTCUSDT"

echo "=== Décisions ==="

req "/api/decisions/recent?symbol=BTCUSDT&limit=5" \
  '((type=="array") and (length<=5)) or
   ((type=="object") and has("items") and (.items|type)=="array" and ((.items|length) <= 5))' \
  "decisions/recent BTCUSDT"
req "/api/decisions/now?symbol=BTCUSDT" \
  'has("action") and has("confidence") and has("symbol")
   and (.action|type)=="string"
   and (.confidence|type)=="number"
   and ((.symbol|ascii_downcase)=="btcusdt")' \
  "decisions/now BTCUSDT"

echo "=== Sentiment / ML / Portefeuille ==="
req "/api/sentiment/series?symbol=BTCUSDT&window=10h&fields=tw,rd,nw,tr" 'type=="object" or type=="array"' "sentiment series BTCUSDT"
req "/api/ml/status?symbol=BTCUSDT" 'type=="object"' "ml/status BTCUSDT"
req "/api/portfolio/summary" 'type=="object"' "portfolio/summary"

echo "=== Boucle multi-symboles (now+ticker) ==="
SYMS=(BTCUSDT ETHUSDT BNBUSDT SOLUSDT PEPEUSDT DOGEUSDT LINKUSDT XRPUSDT ADAUSDT AVAXUSDT)
for s in "${SYMS[@]}"; do
  req "/api/decisions/now?symbol=$s" \
    'has("action") and has("confidence")
     and (.action|type)=="string"
     and (.confidence|type)=="number"' \
    "decisions/now $s"
  req "/api/price/ticker?symbol=$s" \
    '([.price,.last,.value] | map(select(type=="number")) | length) >= 1' \
    "price/ticker $s"
done


echo "🎉 Tous les tests ont passé."
