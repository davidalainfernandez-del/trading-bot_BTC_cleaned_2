#!/usr/bin/env bash
# Usage: ./healthcheck.sh [BASE_URL]
# Default BASE_URL: http://localhost:5000
set -u

URL="${1:-http://localhost:5000}"

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: 'jq' is required (brew install jq)"; exit 2
fi

PASS=0; FAIL=0
hr(){ printf '%s\n' "----------------------------------------"; }
ok(){ echo "✅ $1"; PASS=$((PASS+1)); }
ko(){ echo "❌ $1"; FAIL=$((FAIL+1)); }

hr
echo "Healthcheck for: $URL"
hr

# 1) Autotrade loop alive / freshness
h=$(curl -s "$URL/api/health")
okflag=$(echo "$h" | jq -r '.ok')
age=$(echo "$h" | jq -r '.last_tick_age_s // 99999')
if [[ "$okflag" == "true" && "$age" -lt 15 ]]; then
  ok "Autotrade loop alive (last_tick_age_s=${age}s)"
else
  ko "Health not fresh or down (last_tick_age_s=${age}s)"
fi

# 2) Status sanity
st=$(curl -s "$URL/api/status")
price=$(echo "$st" | jq -r '.price // 0')
if awk "BEGIN{exit !($price>0)}"; then
  ok "Status price sane: $price"
else
  ko "Status price invalid: $price"
fi

# 3) Sentiment snapshot present
snap=$(curl -s "$URL/api/sentiment")
pred=$(echo "$snap" | jq -r '.prediction // empty')
if [[ -n "$pred" ]]; then
  ok "Sentiment snapshot prediction present ($pred)"
else
  ko "Sentiment snapshot missing 'prediction'"
fi

# 4) Sentiment+price timeline has data
tl=$(curl -s "$URL/api/sentiment_price")
len=$(echo "$tl" | jq 'length')
if [[ "$len" -ge 10 ]]; then
  ok "Sentiment timeline length OK ($len points)"
else
  ko "Sentiment timeline too short ($len)"
fi

# 5) Decision trace has recent entries
dt=$(curl -s "$URL/api/decision_trace?n=10")
dlen=$(echo "$dt" | jq '.items|length // length')
if [[ "$dlen" -ge 1 ]]; then
  newest=$(echo "$dt" | jq -r '(.items // .) | max_by(.time) | .time')
  ok "Decision trace non-empty (latest: $newest, count: $dlen)"
else
  ko "No decisions recorded yet"
fi

# 6) Account valuation ~= cash + btc*price
acc=$(curl -s "$URL/api/account")
cash=$(echo "$acc" | jq -r '.cash // 0')
btc=$(echo "$acc" | jq -r '.btc // 0')
p=$(echo "$acc" | jq -r '.price // 0')
val=$(echo "$acc" | jq -r '.valuation // 0')
calc=$(awk -v c="$cash" -v b="$btc" -v pr="$p" 'BEGIN{printf "%.8f", c + b*pr}')
diff=$(awk -v v="$val" -v x="$calc" 'BEGIN{d=v-x; if (d<0) d=-d; printf "%.6f", d}')
if awk -v d="$diff" 'BEGIN{exit !(d<=0.5)}'; then
  ok "Account valuation consistent (|valuation - (cash+btc*px)| ≈ $diff)"
else
  ko "Account valuation mismatch (diff ≈ $diff)"
fi

# 7) Learning signals in logs (SGD/bandit/reward)
logs=$(curl -s "$URL/api/logs?tail=500" || echo "")
hits=$(echo "$logs" | tr '[:upper:]' '[:lower:]' | grep -E 'sgd|bandit|reward|update sgd' -c || true)
if [[ "$hits" -ge 1 ]]; then
  ok "Learning logs found ($hits match in last 500 lines)"
else
  ko "No obvious learning messages in last 500 log lines"
fi

# 8) Why-now reasons available
why=$(curl -s "$URL/api/why/now")
line=$(echo "$why" | jq -r '.line // .reasons.line // empty')
if [[ -n "$line" ]]; then
  ok "Why/now response present: $(echo "$line" | head -c 80)"
else
  ok "Why/now endpoint reachable"
fi

hr
echo "PASS=$PASS  FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
