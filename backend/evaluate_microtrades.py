#!/usr/bin/env python3
import argparse, json, math, sys
from urllib.request import urlopen, Request
from urllib.error import URLError

def fetch_params(base_url):
    try:
        with urlopen(base_url.rstrip('/') + "/api/params") as r:
            return json.loads(r.read().decode('utf-8'))
    except URLError:
        return None

def main():
    p = argparse.ArgumentParser(description="Évalue le net/trade et le nombre de trades nécessaires pour atteindre un objectif.")
    p.add_argument("--base-url", default="http://localhost:5000")
    p.add_argument("--sizes", default="20,30,50", help="Tailles de trade en USDT (séparées par des virgules).")
    p.add_argument("--tps", default="0.003,0.005,0.01", help="Take-profit en décimal (0.005 = 0,5%).")
    p.add_argument("--target", type=float, default=10.0, help="Objectif de profit (USDT).")
    p.add_argument("--no-api", action="store_true", help="Ne pas lire les paramètres via l'API.")
    p.add_argument("--fee-buy", type=float, default=None, help="Frais achat par côté (décimal).")
    p.add_argument("--fee-sell", type=float, default=None, help="Frais vente par côté (décimal).")
    p.add_argument("--slippage", type=float, default=None, help="Slippage (décimal).")
    p.add_argument("--buffer", type=float, default=None, help="Buffer de sécurité (décimal).")
    p.add_argument("--csv", default="microtrade_eval.csv", help="Chemin du CSV de sortie.")
    args = p.parse_args()

    # Defaults (profil maker réaliste)
    fee_buy = 0.00075
    fee_sell = 0.00075
    slippage = 0.0002
    buffer = 0.0005
    profile = "maker"

    params = None
    if not args.no_api:
        params = fetch_params(args.base_url)

    if params:
        prefer_maker = bool(params.get("PREFER_MAKER", True))
        maker_fee_buy = float(params.get("MAKER_FEE_BUY", 0.00075))
        maker_fee_sell = float(params.get("MAKER_FEE_SELL", 0.00075))
        taker_fee_buy = float(params.get("FEE_RATE_BUY", 0.0010))
        taker_fee_sell = float(params.get("FEE_RATE_SELL", 0.0010))
        fee_buy = maker_fee_buy if prefer_maker else taker_fee_buy
        fee_sell = maker_fee_sell if prefer_maker else taker_fee_sell
        slippage = float(params.get("SLIPPAGE", slippage))
        buffer = float(params.get("FEE_BUFFER_PCT", buffer))
        profile = "maker" if prefer_maker else "taker"

    # CLI overrides
    if args.fee_buy is not None: fee_buy = args.fee_buy
    if args.fee_sell is not None: fee_sell = args.fee_sell
    if args.slippage is not None: slippage = args.slippage
    if args.buffer is not None: buffer = args.buffer

    sizes = [float(s.strip()) for s in args.sizes.split(",") if s.strip()]
    tps = [float(s.strip()) for s in args.tps.split(",") if s.strip()]

    cost = fee_buy + fee_sell + slippage + buffer  # aller-retour
    rows = []
    for size in sizes:
        for tp in tps:
            net = size * (tp - cost)
            trades = None
            if net > 0:
                trades = math.ceil(args.target / net)
            rows.append({
                "profile": profile,
                "size_usdt": size,
                "tp_pct": tp * 100,
                "break_even_pct": cost * 100,
                "net_per_trade_usdt": round(net, 6),
                "trades_for_target": trades
            })

    # Write CSV
    import csv
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Pretty print
    print(f"Profil: {profile}")
    print(f"Break-even ≈ {cost*100:.3f}% (fees+slip+buffer)")
    print(f"Sauvé: {args.csv}\n")
    print("{:>7} {:>8} {:>12} {:>14} {:>18}".format("Size", "TP %", "Break-even %", "Net/trade ($)", "# Trades 10$"))
    for r in rows:
        tr = r["trades_for_target"]
        tr_s = str(tr) if tr is not None else "∞"
        print("{:>7.0f} {:>8.3f} {:>12.3f} {:>14.6f} {:>18}".format(
            r["size_usdt"], r["tp_pct"], r["break_even_pct"], r["net_per_trade_usdt"], tr_s))

if __name__ == "__main__":
    main()
