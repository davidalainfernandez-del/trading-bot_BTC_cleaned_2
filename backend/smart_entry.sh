#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:5000}"
SYMBOL="${SYMBOL:-BTCUSDT}"
USDT="${USDT:-20}"
TIMEOUT="${TIMEOUT:-5}"
POLL="${POLL:-0.5}"
OFFSET_BPS="${OFFSET_BPS:-2}"
python3 smart_entry.py --base-url "$BASE_URL" --symbol "$SYMBOL" --usdt "$USDT" --timeout-sec "$TIMEOUT" --poll-sec "$POLL" --maker-offset-bps "$OFFSET_BPS"
