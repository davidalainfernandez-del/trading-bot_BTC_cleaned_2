#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, csv, json, math, os, statistics, sys
from urllib.request import urlopen, Request

def fetch_json(url):
    with urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def estimate_break_even(base_url, defaults):
    # Read runtime params to estimate total roundtrip cost (fees+slip+buffer)
    try:
        p = fetch_json(base_url.rstrip('/') + "/api/params")
    except Exception:
        p = {"ok": False}
    fee_buy = defaults["fee_buy"]
    fee_sell = defaults["fee_sell"]
    slip = defaults["slippage"]
    buf  = defaults["buffer"]
    profile = defaults["profile"]
    if p.get("ok"):
        prefer_maker = bool(p["params"].get("PREFER_MAKER", True))
        maker_fee_buy = float(p["params"].get("MAKER_FEE_BUY", 0.00075))
        maker_fee_sell = float(p["params"].get("MAKER_FEE_SELL", 0.00075))
        taker_fee_buy = float(p["params"].get("FEE_RATE_BUY", 0.0010))
        taker_fee_sell = float(p["params"].get("FEE_RATE_SELL", 0.0010))
        fee_buy = maker_fee_buy if prefer_maker else taker_fee_buy
        fee_sell = maker_fee_sell if prefer_maker else taker_fee_sell
        slip = float(p["params"].get("SLIPPAGE", slip))
        buf  = float(p["params"].get("FEE_BUFFER_PCT", buf))
        profile = "maker" if prefer_maker else "taker"
    return profile, fee_buy + fee_sell + slip + buf

def load_roundtrips(path):
    rows = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "entry_ts": float(r.get("entry_ts") or 0.0),
                    "exit_ts": float(r.get("exit_ts") or 0.0),
                    "ret": float(r.get("ret") or 0.0),
                    "pnl": float(r.get("pnl") or 0.0),
                    "alloc_cost": float(r.get("alloc_cost") or 0.0),
                })
            except Exception:
                continue
    return rows

def grid_search_tp(returns, tps, break_even, size):
    best = None
    for tp in tps:
        hit = sum(1 for r in returns if r >= tp)
        n   = len(returns)
        hr  = (hit / n) if n > 0 else 0.0
        net = size * (tp - break_even) * hr
        cand = {"tp": tp, "hit_rate": hr, "net_per_trade": net}
        if best is None or cand["net_per_trade"] > best["net_per_trade"]:
            best = cand
    return best or {"tp": None, "hit_rate": 0.0, "net_per_trade": 0.0}

def main():
    ap = argparse.ArgumentParser(description="Optimise TP à partir de l'historique papier (roundtrips).")
    ap.add_argument("--base-url", default="http://localhost:5000")
    ap.add_argument("--history", default="paper_roundtrips.csv")
    ap.add_argument("--sizes", default="20,30,50,200")
    ap.add_argument("--tp-min", type=float, default=0.002)  # 0.20%
    ap.add_argument("--tp-max", type=float, default=0.015)  # 1.50%
    ap.add_argument("--tp-step", type=float, default=0.0005)
    ap.add_argument("--apply", action="store_true", help="Applique MIN_TP_PCT=TP* via l'API.")
    ap.add_argument("--csv", default="tp_optim_results.csv")
    args = ap.parse_args()

    defaults = dict(fee_buy=0.00075, fee_sell=0.00075, slippage=0.0002, buffer=0.0005, profile="maker")
    profile, break_even = estimate_break_even(args.base_url, defaults)

    rows = load_roundtrips(args.history)
    rets = [r["ret"] for r in rows if math.isfinite(r["ret"])]
    n = len(rets)
    if n == 0:
        print("Aucun roundtrip dans l'historique. Lance collect_paper_history d'abord.", file=sys.stderr)
        sys.exit(1)

    # Build TP grid
    tps = []
    x = args.tp_min
    while x <= args.tp_max + 1e-12:
        tps.append(round(x, 8))
        x += args.tp_step

    sizes = [float(s.strip()) for s in args.sizes.split(",") if s.strip()]
    out = []
    for size in sizes:
        best = grid_search_tp(rets, tps, break_even, size)
        out.append({
            "profile": profile,
            "n_trades": n,
            "size_usdt": size,
            "break_even_pct": break_even*100.0,
            "tp_opt_pct": (best["tp"]*100.0 if best["tp"] is not None else None),
            "hit_rate_at_opt": best["hit_rate"],
            "net_per_trade_usdt": best["net_per_trade"],
        })

    # Save CSV
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        import csv
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        for r in out:
            w.writerow(r)

    # Optionally apply MIN_TP_PCT using the *first* size's optimal TP
    if args.apply and out and out[0]["tp_opt_pct"] is not None:
        tp_dec = float(out[0]["tp_opt_pct"])/100.0
        # small safety margin: -0.0001 (1 bp)
        tp_apply = max(tp_dec - 0.0001, break_even + 0.0001)
        payload = json.dumps({"MIN_TP_PCT": tp_apply}).encode("utf-8")
        req = Request(args.base_url.rstrip('/') + "/api/params/update", method="POST",
                      headers={"Content-Type": "application/json"}, data=payload)
        with urlopen(req) as r:
            _ = r.read()
        print(f"Applied MIN_TP_PCT={tp_apply:.4%}")

    # Pretty print
    print(f"Profil: {profile} | Break-even ≈ {break_even*100:.3f}% | N={n} trades")
    print("{:>7} {:>12} {:>10} {:>12}".format("Size", "TP_opt %", "HitRate", "Net/trade"))
    for r in out:
        print("{:>7.0f} {:>12.3f} {:>10.3f} {:>12.6f}".format(
            r["size_usdt"], r["tp_opt_pct"], r["hit_rate_at_opt"], r["net_per_trade_usdt"]))

if __name__ == "__main__":
    main()
