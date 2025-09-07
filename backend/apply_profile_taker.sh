#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:5000}"

echo ">> Profil TAKer (0.10%/côté)"
curl -sf -X POST "${BASE_URL}/api/params/update" -H 'Content-Type: application/json' -d '{
  "PREFER_MAKER": false,
  "MAKER_FEE_BUY": 0.00075,
  "MAKER_FEE_SELL": 0.00075,
  "FEE_RATE_BUY": 0.0010,
  "FEE_RATE_SELL": 0.0010,
  "SLIPPAGE": 0.0002,
  "FEE_BUFFER_PCT": 0.0005,
  "RISK_MIN_ORDER_NOTIONAL": 10,
  "BUY_PCT": 0.25,
  "MIN_TP_PCT": 0.0035,
  "MIN_SL_PCT": 0.0060
}'
echo
echo "✅ Profil TAKer appliqué."
