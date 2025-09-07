#!/usr/bin/env bash
# flatten_portfolio_v4.sh — aplanit TOUTES les positions via l'API locale (paper)
# - vend les longs (SELL qty_rounded)
# - rachète les shorts (BUY usdt pour couvrir |qty_rounded| * last)
# - quantize au pas (step) et ignore les poussières (< epsilon)
# - protège contre les notionals trop petits
# Dépendances: bash, jq, curl, awk

set -euo pipefail
export LC_ALL=C
export LANG=C

API="${1:-http://localhost:5000}"

# --- Paramètres ajustables via ENV (avec valeurs prudentes) ---
: "${QTY_STEP:=0.000001}"            # pas d'arrondi par défaut (si l'exchange n'est pas connu)
: "${MIN_BASE_QTY:=0.000001}"        # quantité min d'exécution (base asset)
: "${MIN_QUOTE_NOTIONAL:=10}"        # notional (USDT) minimal cible
: "${COVER_BUFFER_BPS:=15}"          # buffer pour couvrir short (15 bps = 0.15%)
: "${DRY_RUN:=0}"                    # 1 = affiche sans exécuter
: "${SYMBOLS_CSV:=}"                 # vide = tous; sinon "BTCUSDT,ETHUSDT"

# -------- Helpers --------
j() { jq -r "$@"; }

# Arrondi "vers le bas" au step (quantize)
quantize_floor() {
  # $1 = qty, $2 = step
  awk -v q="$1" -v s="$2" 'BEGIN{
    if (s <= 0) { printf("%.12f\n", q); exit }
    # floor(q/step)*step
    v = (q>=0 ? (int(q/s)) : (int((q/s)-0.9999999999))) * s
    printf("%.12f\n", v)
  }'
}

abs() { awk -v x="$1" 'BEGIN{ if (x<0) x=-x; printf("%.12f\n", x) }'; }
gt()  { awk -v a="$1" -v b="$2" 'BEGIN{ exit (a>b)?0:1 }'; }  # 0 si a>b
ge()  { awk -v a="$1" -v b="$2" 'BEGIN{ exit (a>=b)?0:1 }'; } # 0 si a>=b

line() { printf '%s\n' "----------------------------------------------------------------"; }

info()  { printf '[INFO] %s\n' "$*"; }
warn()  { printf '[WARN] %s\n' "$*" >&2; }
act()   { printf '[ACTION] %s\n' "$*"; }
skip()  { printf '[SKIP] %s\n' "$*"; }

# -------- Récup du portfolio --------
info "Reading $API/api/portfolio/summary"
PF="$(curl -fsS "$API/api/portfolio/summary")" || { warn "Portfolio fetch failed"; exit 1; }

# Liste des positions
if [[ -n "$SYMBOLS_CSV" ]]; then
  MAP="$(echo "$PF" | jq --arg csv "$SYMBOLS_CSV" '
    ($csv | split(",") | map(.)) as $want
    | .positions | map(select(.symbol as $s | $want | index($s)))
  ')"
else
  MAP="$(echo "$PF" | jq '.positions')"
fi

COUNT="$(echo "$MAP" | jq 'length')"
info "Found $COUNT symbols."

line
for i in $(seq 0 $((COUNT-1))); do
  ROW="$(echo "$MAP" | jq ".[$i]")"
  SYMBOL="$(echo "$ROW" | j '.symbol')"
  LAST="$(echo "$ROW"   | j '.last // 0')"
  RAW_QTY="$(echo "$ROW"| j '.qty // 0')"   # si l'API expose qty_raw, remplace par .qty_raw // .qty

  # paramètres marché (fallback ENV)
  STEP="$QTY_STEP"
  MIN_QTY="$MIN_BASE_QTY"
  MIN_NOTIONAL="$MIN_QUOTE_NOTIONAL"

  # Quantize & epsilon (epsilon = max(step, min_qty))
  QTY_ROUNDED="$(quantize_floor "$RAW_QTY" "$STEP")"
  EPS="$(awk -v a="$STEP" -v b="$MIN_QTY" 'BEGIN{e=(a>b)?a:b; printf("%.12f\n", e)}')"

  # Notional (pour checks & couvertures short)
  NOTIONAL="$(awk -v q="$QTY_ROUNDED" -v p="$LAST" 'BEGIN{printf("%.6f\n", q*p)}')"
  ABS_QTY="$(abs "$QTY_ROUNDED")"
  ABS_NOTIONAL="$(abs "$NOTIONAL")"

  printf "%-9s qty_raw=% .10f  qty_round=% .10f  last=%.8f  notional=% .6f\n" "$SYMBOL" "$RAW_QTY" "$QTY_ROUNDED" "$LAST" "$NOTIONAL"

  # Skip si poussière
  if ! gt "$ABS_QTY" "$EPS"; then
    skip "$SYMBOL : |qty| <= epsilon ($EPS) → ignore"
    line; continue
  fi

  # LONG -> SELL tout
  if ge "$QTY_ROUNDED" "0"; then
    # vérifier notional minimum
    if ! ge "$ABS_NOTIONAL" "$MIN_NOTIONAL"; then
      skip "$SYMBOL : notional ${ABS_NOTIONAL} < min ${MIN_NOTIONAL} → ignore"
      line; continue
    fi
    act "SELL $SYMBOL qty=$QTY_ROUNDED"
    if [[ "$DRY_RUN" = "1" ]]; then
      echo '[DRY-RUN] curl -s -X POST /api/force/sell ...'
    else
      curl -fsS -X POST "$API/api/force/sell" \
        -H "Content-Type: application/json" \
        -d "{\"symbol\":\"$SYMBOL\",\"qty\":$QTY_ROUNDED}" | jq .
    fi
    line; continue
  fi

  # SHORT -> BUY pour couvrir |qty|
  # montant en USDT avec petit buffer (slippage/fees)
  COVER_USDT_RAW="$(awk -v q="$ABS_QTY" -v p="$LAST" 'BEGIN{printf("%.6f\n", q*p)}')"
  COVER_USDT="$(awk -v u="$COVER_USDT_RAW" -v bps="$COVER_BUFFER_BPS" 'BEGIN{printf("%.2f\n", u*(1+bps/10000.0))}')"

  if ! ge "$COVER_USDT" "$MIN_NOTIONAL"; then
    skip "$SYMBOL : cover_usdt ${COVER_USDT} < min ${MIN_NOTIONAL} → ignore"
    line; continue
  fi

  act "BUY  $SYMBOL usdt=$COVER_USDT   (cover |qty|=$ABS_QTY @ last=$LAST, buffer=${COVER_BUFFER_BPS}bps)"
  if [[ "$DRY_RUN" = "1" ]]; then
    echo '[DRY-RUN] curl -s -X POST /api/force/buy ...'
  else
    curl -fsS -X POST "$API/api/force/buy" \
      -H "Content-Type: application/json" \
      -d "{\"symbol\":\"$SYMBOL\",\"usdt\":$COVER_USDT}" | jq .
  fi
  line
done

# Affiche le nouveau portfolio à la fin
info "New portfolio:"
curl -fsS "$API/api/portfolio/summary" | jq .
