#!/usr/bin/env bash
set -euo pipefail
# Kill by script name
pkill -f "adaptive_risk_manager.py" || true
