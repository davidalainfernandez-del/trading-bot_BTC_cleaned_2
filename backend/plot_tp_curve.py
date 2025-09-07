#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, csv, json, math, os, sys
from urllib.request import urlopen
import matplotlib.pyplot as plt
from pathlib import Path

def fetch_json(url):
    with urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def estimate_break_even(base_url, defaults):
    try:
        p = fetch_json(base_url.rstrip('/') + "/api/params")
    except Exception:
        p = {"ok": False}
    fee_buy = defaults["fee_buy"]; fee_sell = defaults["fee_sell"]
    slip = defaults["slippage"]; buf  = defaults["buffer"]
    if p.get("ok"):
        pr = p.get("params", p)
        prefer_maker = bool(pr.get("PREFER_MAKER", True))
        maker_fee_buy = float(pr.get("MAKER_FEE_BUY", 0.00075))
        maker_fee_sell = float(pr.get("MAKER_FEE_SELL", 0.00075))
        taker_fee_buy = float(pr.get("FEE_RATE_BUY", 0.0010))
        taker_fee_sell = float(pr.get("FEE_RATE_SELL", 0.0010))
        fee_buy = maker_fee_buy if prefer_maker else taker_fee_buy
        fee_sell = maker_fee_sell if prefer_maker else taker_fee_sell
        slip = float(pr.get("SLIPPAGE", slip))
        buf  = float(pr.get("FEE_BUFFER_PCT", buf))
    return fee_buy + fee_sell + slip + buf

def load_returns(path):
    rets = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                x = float(r.get("ret", "nan"))
                if math.isfinite(x): rets.append(x)
            except Exception: pass
    return rets

def build_grid(tp_min, tp_max, tp_step):
    xs = []; v = tp_min
    while v <= tp_max + 1e-12: xs.append(round(v, 10)); v += tp_step
    return xs

def main():
    ap = argparse.ArgumentParser(description="Trace la courbe Net/trade ($) en fonction du TP, à partir de l'historique papier.")
    ap.add_argument("--base-url", default="http://localhost:5000")
    ap.add_argument("--history", default="paper_roundtrips.csv")
    ap.add_argument("--sizes", default="20,30,50")
    ap.add_argument("--tp-min", type=float, default=0.002)
    ap.add_argument("--tp-max", type=float, default=0.015)
    ap.add_argument("--tp-step", type=float, default=0.0005)
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()
    defaults = dict(fee_buy=0.00075, fee_sell=0.00075, slippage=0.0002, buffer=0.0005)
    break_even = estimate_break_even(args.base_url, defaults)
    rets = load_returns(args.history)
    if not rets: print("Aucun historique trouvé dans", args.history, file=sys.stderr); sys.exit(1)
    tps = build_grid(args.tp_min, args.tp_max, args.tp_step)
    sizes = [float(s.strip()) for s in args.sizes.split(",") if s.strip()]
    for size in sizes:
        ys = []
        for tp in tps:
            hit = sum(1 for r in rets if r >= tp)
            n = len(rets); hr = (hit / n) if n > 0 else 0.0
            net = size * (tp - break_even) * hr
            ys.append(net)
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.plot([tp*100 for tp in tps], ys, label=f"size={size:.0f} USDT")
        ax.set_title("Net/trade ($) vs TP (%)")
        ax.set_xlabel("TP (%)")
        ax.set_ylabel("Net par trade (USDT)")
        ax.axvline(break_even*100)
        ax.legend()
        outpath = Path(args.outdir) / f"net_vs_tp_size{int(size)}.png"
        fig.savefig(outpath, dpi=120, bbox_inches="tight")
        plt.close(fig)
        print(str(outpath))
if __name__ == "__main__":
    main()
