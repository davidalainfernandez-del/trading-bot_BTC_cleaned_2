#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:5000}"
HIST="${HIST:-paper_roundtrips.csv}"
OUT="${OUT:-paper_eval_report.pdf}"
SIZES="${SIZES:-20,30,50}"
# Forward all args so you can pass --apply and --apply-size 50, etc.
python3 make_paper_report.py --base-url "$BASE_URL" --history "$HIST" --out "$OUT" --sizes "$SIZES" "$@"
