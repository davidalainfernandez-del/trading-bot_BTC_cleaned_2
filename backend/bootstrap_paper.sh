#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:5000}"

echo ">> Ping API"
curl -sf "${BASE_URL}/api/ping" || { echo "API non joignable"; exit 1; }
echo

echo ">> Activer le learning mode (papier)"
curl -sf -X POST "${BASE_URL}/api/learning" -H 'Content-Type: application/json' -d '{"enable": true}'
echo

echo ">> Mettre à jour les paramètres clés"
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

echo ">> Pause auto-trade au démarrage (sécurité)"
curl -sf -X POST "${BASE_URL}/api/autotrade" -H 'Content-Type: application/json' -d '{"paused": true}'
echo

echo ">> État autotrade:"
curl -sf "${BASE_URL}/api/autotrade"
echo

cat <<'TIP'

✅ Prêt.
- Lancement:    docker compose up -d --build
- Bootstrap:    BASE_URL=http://localhost:5000 bash bootstrap_paper.sh
- Reprendre:    curl -X POST ${BASE_URL}/api/autotrade -H 'Content-Type: application/json' -d '{"paused": false}'
- Forcer BUY:   curl -X POST ${BASE_URL}/api/manual/buy -H 'Content-Type: application/json' -d '{"usdt": 20}'
- Forcer SELL:  curl -X POST ${BASE_URL}/api/force/sell -H 'Content-Type: application/json' -d '{"pct": 100}'
TIP
