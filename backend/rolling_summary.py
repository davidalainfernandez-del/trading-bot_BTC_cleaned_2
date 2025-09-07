#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, csv, json, math, sys
from urllib.request import urlopen

def jget(url):
    with urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def fetch_params(base_url):
    try:
        return jget(base_url.rstrip('/') + "/api/params")
    except Exception:
        return {"ok": False, "params": {}}

def fetch_trades(base_url):
    try:
        js = jget(base_url.rstrip('/') + "/api/trades")
        return js.get("items", []) if js.get("ok") else []
    except Exception:
        return []

def reconstruct_roundtrips(trades):
    lots = []; out = []
    for row in trades:
        side = (row.get("side") or "").lower()
        ts = float(row.get("time") or row.get("ts") or 0.0)
        px = float(row.get("price") or 0.0)
        qty = float(row.get("qty") or 0.0)
        fee = float(row.get("fee") or 0.0)
        if qty <= 0 or px <= 0: continue
        if side == "buy":
            lots.append([qty, px*qty + fee, ts, px])
        elif side == "sell":
            remain = qty; proceeds = px*qty - fee
            alloc_cost = 0.0; entry_ts=None; entry_px=None
            while remain > 1e-12 and lots:
                lqty, lcost, lts, lpx = lots[0]
                use = min(lqty, remain)
                unit_cost = (lcost / lqty) if lqty > 0 else 0.0
                alloc_cost += unit_cost * use
                if entry_ts is None: entry_ts=float(lts); entry_px=float(lpx)
                lqty -= use; remain -= use
                if lqty <= 1e-12: lots.pop(0)
                else:
                    lots[0][0] = lqty; lots[0][1] = unit_cost * lqty
            pnl = proceeds - alloc_cost
            ret = (pnl / alloc_cost) if alloc_cost > 0 else 0.0
            out.append({"entry_ts": entry_ts or ts, "exit_ts": ts, "ret": ret})
    return out

def tp_grid_search(returns, break_even, size, tp_min, tp_max, tp_step):
    # démarre la grille au max(tp_min, break-even + 1 bp)
    tp_min_eff = max(tp_min, break_even + 0.0001)

    tps = []
    v = tp_min_eff
    while v <= tp_max + 1e-12:
        tps.append(round(v, 8))
        v += tp_step

    best = {"tp": None, "hit_rate": 0.0, "net": 0.0}
    n = len(returns)
    if n == 0:
        return best

    for tp in tps:
        hit = sum(1 for r in returns if r >= tp)
        hr = hit / n
        net = size * (tp - break_even) * hr
        # garde le meilleur même si net <= 0
        if best["tp"] is None or net >= best["net"]:
            best = {"tp": tp, "hit_rate": hr, "net": net}

    # fallback explicite si HR=0 : afficher BE + 1 bp
    if best["hit_rate"] == 0.0 or best["tp"] is None:
        best = {"tp": max(args.tp_min, break_even + 0.0001), "hit_rate": 0.0, "net_per_trade": 0.0}
    return best


def losses_quantile(losses_abs, q):
    if not losses_abs: return None
    vs = sorted(losses_abs)
    idx = (len(vs)-1) * q
    lo = int(idx//1); hi = int(-(-idx//1))
    if lo == hi: return vs[lo]
    frac = idx - lo
    return vs[lo]*(1-frac) + vs[hi]*frac

def main():
    ap = argparse.ArgumentParser(description="Résumé rolling windows pour TP/SL.")
    ap.add_argument("--base-url", default="http://localhost:5000")
    ap.add_argument("--primary-size", type=float, default=50.0)
    ap.add_argument("--tp-min", type=float, default=0.002)
    ap.add_argument("--tp-max", type=float, default=0.015)
    ap.add_argument("--tp-step", type=float, default=0.0005)
    ap.add_argument("--sl-quantile", type=float, default=0.80)
    ap.add_argument("--sl-floor", type=float, default=0.0060)
    ap.add_argument("--windows", default="10,50,100,250,1000")
    ap.add_argument("--csv", default="rolling_summary.csv")
    args = ap.parse_args()

    params = fetch_params(args.base_url)
    pr = params.get("params", {})
    prefer_maker = bool(pr.get("PREFER_MAKER", True))
    maker_fee_buy = float(pr.get("MAKER_FEE_BUY", 0.00075))
    maker_fee_sell = float(pr.get("MAKER_FEE_SELL", 0.00075))
    taker_fee_buy = float(pr.get("FEE_RATE_BUY", 0.0010))
    taker_fee_sell = float(pr.get("FEE_RATE_SELL", 0.0010))
    slip = float(pr.get("SLIPPAGE", 0.0002))
    buf  = float(pr.get("FEE_BUFFER_PCT", 0.0005))
    fee_buy = maker_fee_buy if prefer_maker else taker_fee_buy
    fee_sell = maker_fee_sell if prefer_maker else taker_fee_sell
    be = fee_buy + fee_sell + slip + buf

    trades = fetch_trades(args.base_url)
    rts = reconstruct_roundtrips(trades)
    rets = [rt["ret"] for rt in rts]
    wins = [int(x.strip()) for x in args.windows.split(",") if x.strip()]

    rows = []
    for N in wins:
        seg = rets[-N:] if len(rets) >= N else rets[:]
        best = tp_grid_search(seg, be, args.primary_size, args.tp_min, args.tp_max, args.tp_step)
        losses = [abs(x) for x in seg if x < 0]
        if len(losses) >= 5:
            sl = max(args.sl_floor, losses_quantile(losses, max(0.5, min(args.sl_quantile, 0.99))))
            method = "quantile"
        else:
            sl = args.sl_floor; method="floor"
        rows.append({
            "window": N,
            "n_samples": len(seg),
            "tp_opt_pct": best["tp"],
            "hit_rate": best["hit_rate"],
            "net_per_trade_usdt": best["net"],
            "sl_reco_pct": sl,
            "sl_method": method
        })

    # print table
    print("{:>6} {:>9} {:>10} {:>10} {:>14} {:>12} {:>9}".format("Win", "Samples", "TP_opt%", "HitRate", "Net/trade$", "SL_reco%", "SL_meth"))
    for r in rows:
        tp_pct = (r["tp_opt_pct"]*100.0) if r["tp_opt_pct"] is not None else float('nan')
        print("{:>6} {:>9} {:>10.3f} {:>10.3f} {:>14.6f} {:>12.3f} {:>9}".format(
            r["window"], r["n_samples"], tp_pct, r["hit_rate"], r["net_per_trade_usdt"], r["sl_reco_pct"]*100.0, r["sl_method"]))

    # save csv
    import csv as _csv
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows: w.writerow(r)

if __name__ == "__main__":
    main()
