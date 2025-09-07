#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:5000}"

echo "== Collecte de l'historique (roundtrips) =="
BASE_URL="$BASE_URL" python3 collect_paper_history.py

echo
echo "== Optimisation TP (profil courant depuis API) =="
BASE_URL="$BASE_URL" python3 optimize_tp_from_history.py --history paper_roundtrips.csv --sizes 20,30,50 --tp-min 0.002 --tp-max 0.015 --tp-step 0.0005 --csv tp_optim_results.csv "$@"

echo
echo "Résultats CSV: tp_optim_results.csv"
