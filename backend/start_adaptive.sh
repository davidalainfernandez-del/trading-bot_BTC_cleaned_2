#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:5000}"
python3 adaptive_risk_manager.py --base-url "$BASE_URL" --apply
