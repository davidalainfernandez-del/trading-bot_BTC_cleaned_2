#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:5000}"
HIST="${HIST:-paper_roundtrips.csv}"
Q="${Q:-0.80}"
FLOOR="${FLOOR:-0.006}"

python3 optimize_sl_from_history.py --base-url "$BASE_URL" --history "$HIST" --quantile "$Q" --floor "$FLOOR" --apply
python3 plot_loss_distribution.py --history "$HIST" --sl "$FLOOR" || true
