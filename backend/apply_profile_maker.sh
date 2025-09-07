#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:5000}"

echo ">> Profil MAKER (0.075%/côté avec BNB)"
curl -sf -X POST "${BASE_URL}/api/params/update" -H 'Content-Type: application/json' -d '{
  "PREFER_MAKER": true,
  "MAKER_FEE_BUY": 0.00075,
  "MAKER_FEE_SELL": 0.00075,
  "FEE_RATE_BUY": 0.00075,
  "FEE_RATE_SELL": 0.00075,
  "SLIPPAGE": 0.0002,
  "FEE_BUFFER_PCT": 0.0005,
  "RISK_MIN_ORDER_NOTIONAL": 10,
  "BUY_PCT": 0.25,
  "MIN_TP_PCT": 0.0030,
  "MIN_SL_PCT": 0.0060
}'
echo
echo "✅ Profil MAKER appliqué."
