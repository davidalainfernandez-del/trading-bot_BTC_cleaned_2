#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:5000}"
HIST="${HIST:-paper_roundtrips.csv}"
OUTDIR="${OUTDIR:-.}"
SIZES="${SIZES:-20,30,50}"
python3 plot_tp_curve.py --base-url "$BASE_URL" --history "$HIST" --outdir "$OUTDIR" --sizes "$SIZES"
