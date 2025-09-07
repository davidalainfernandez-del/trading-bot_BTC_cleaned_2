#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, csv, json, math, sys
from pathlib import Path
from urllib.request import urlopen, Request
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

def fetch_json(url):
    with urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def estimate_from_api(base_url, defaults):
    params = None
    try:
        params = fetch_json(base_url.rstrip('/') + "/api/params")
    except Exception:
        params = {"ok": False}
    prefer_maker = True
    maker_fee_buy = defaults["fee_buy"]
    maker_fee_sell = defaults["fee_sell"]
    taker_fee_buy = 0.0010
    taker_fee_sell = 0.0010
    slip = defaults["slippage"]
    buf  = defaults["buffer"]
    min_tp = None
    min_sl = None

    if params.get("ok"):
        pr = params.get("params", params)
        prefer_maker = bool(pr.get("PREFER_MAKER", True))
        maker_fee_buy = float(pr.get("MAKER_FEE_BUY", defaults["fee_buy"]))
        maker_fee_sell = float(pr.get("MAKER_FEE_SELL", defaults["fee_sell"]))
        taker_fee_buy = float(pr.get("FEE_RATE_BUY", 0.0010))
        taker_fee_sell = float(pr.get("FEE_RATE_SELL", 0.0010))
        slip = float(pr.get("SLIPPAGE", slip))
        buf  = float(pr.get("FEE_BUFFER_PCT", buf))
        # read current TP/SL if present
        if "MIN_TP_PCT" in pr:
            try: min_tp = float(pr["MIN_TP_PCT"])
            except Exception: min_tp = None
        if "MIN_SL_PCT" in pr:
            try: min_sl = float(pr["MIN_SL_PCT"])
            except Exception: min_sl = None

    fee_buy = maker_fee_buy if prefer_maker else taker_fee_buy
    fee_sell = maker_fee_sell if prefer_maker else taker_fee_sell
    profile = "maker" if prefer_maker else "taker"
    break_even = fee_buy + fee_sell + slip + buf
    return profile, break_even, min_tp, min_sl

def load_returns(path):
    rets = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                x = float(r.get("ret", "nan"))
                if math.isfinite(x):
                    rets.append(x)
            except Exception:
                pass
    return rets

def build_grid(tp_min, tp_max, tp_step):
    xs = []
    v = tp_min
    while v <= tp_max + 1e-12:
        xs.append(round(v, 10))
        v += tp_step
    return xs

def grid_search_tp(returns, tps, break_even, size):
    best = None
    for tp in tps:
        hit = sum(1 for r in returns if r >= tp)
        n   = len(returns); hr  = (hit / n) if n > 0 else 0.0
        net = size * (tp - break_even) * hr
        cand = {"tp": tp, "hit_rate": hr, "net_per_trade": net}
        if best is None or cand["net_per_trade"] >= best["net_per_trade"]:  
            best = cand
    return best or {"tp": None, "hit_rate": 0.0, "net_per_trade": 0.0}

def load_losses(history_path):
    losses = []
    with open(history_path, "r", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                ret = float(r.get("ret", "nan"))
                if math.isfinite(ret) and ret < 0:
                    losses.append(abs(ret))
            except Exception:
                pass
    return losses

def quantile(values, q):
    if not values:
        return None
    vs = sorted(values)
    idx = (len(vs)-1) * q
    lo = int(math.floor(idx)); hi = int(math.ceil(idx))
    if lo == hi: return vs[lo]
    frac = idx - lo
    return vs[lo]*(1-frac) + vs[hi]*frac

def apply_param(base_url, key, value):
    payload = json.dumps({key: value}).encode("utf-8")
    req = Request(base_url.rstrip('/') + "/api/params/update", method="POST",
                  headers={"Content-Type": "application/json"}, data=payload)
    with urlopen(req) as r:
        _ = r.read()

def main():
    ap = argparse.ArgumentParser(description="Rapport PDF (TP optimal + SL dynamique) avec options d'application.")
    ap.add_argument("--base-url", default="http://localhost:5000")
    ap.add_argument("--history", default="paper_roundtrips.csv")
    ap.add_argument("--sizes", default="20,30,50")
    ap.add_argument("--tp-min", type=float, default=0.002)
    ap.add_argument("--tp-max", type=float, default=0.015)
    ap.add_argument("--tp-step", type=float, default=0.0005)
    ap.add_argument("--out", default="paper_eval_report.pdf")
    ap.add_argument("--apply", action="store_true", help="Applique MIN_TP_PCT au TP optimal (marge -1 bp).")
    ap.add_argument("--apply-size", type=float, default=None, help="Taille (USDT) à utiliser pour l'application du TP (par défaut: plus grande taille).")
    # SL params
    ap.add_argument("--apply-sl", action="store_true", help="Applique MIN_SL_PCT issu du quantile/floor.")
    ap.add_argument("--sl-quantile", type=float, default=0.80, help="Quantile des pertes absolues (0.80 = 80e percentile).")
    ap.add_argument("--sl-floor", type=float, default=0.0060, help="Plancher minimum si peu de données.")
    args = ap.parse_args()

    defaults = dict(fee_buy=0.00075, fee_sell=0.00075, slippage=0.0002, buffer=0.0005)
    profile, break_even, min_tp_curr, min_sl_curr = estimate_from_api(args.base_url, defaults)

    # Load returns + TP grid
    rets = load_returns(args.history)
    if not rets:
        print("Aucun historique trouvé dans", args.history, file=sys.stderr); sys.exit(1)
    tps = build_grid(max(args.tp_min, break_even + 0.0001), args.tp_max, args.tp_step)
    sizes = [float(s.strip()) for s in args.sizes.split(",") if s.strip()]

    # Optimal TP per size
    recs = []
    for size in sizes:
        best = grid_search_tp(rets, tps, break_even, size)
        recs.append((size, best))

    # Choose TP to apply (if asked)
    applied_tp_line = None
    if args.apply and recs:
        chosen_size = max(sizes) if args.apply_size is None else args.apply_size
        chosen = next((b for (s, b) in recs if abs(s - chosen_size) < 1e-9), recs[-1][1])
        tp = chosen.get("tp")
        if tp is not None:
            tp_apply = max(tp - 0.0001, break_even + 0.0001)
            try:
                apply_param(args.base_url, "MIN_TP_PCT", tp_apply)
                applied_tp_line = f"MIN_TP_PCT appliqué: {tp_apply*100:.3f} % (taille: {int(chosen_size)} USDT)"
            except Exception as e:
                applied_tp_line = f"Échec application MIN_TP_PCT ({e})"

    # SL recommendation from loss distribution
    losses = [abs(x) for x in rets if x < 0]
    n_losses = len(losses)
    method = "floor"
    sl_reco = args.sl_floor
    if n_losses >= 5:
        q = max(0.5, min(args.sl_quantile, 0.99))
        qv = quantile(losses, q)
        if qv is not None:
            sl_reco = max(args.sl_floor, qv)
            method = f"quantile_{q:.2f}"

    # Optionally apply SL
    applied_sl_line = None
    if args.apply_sl:
        try:
            apply_param(args.base_url, "MIN_SL_PCT", sl_reco)
            applied_sl_line = f"MIN_SL_PCT appliqué: {sl_reco*100:.3f} % (méthode: {method}, n_losses={n_losses})"
        except Exception as e:
            applied_sl_line = f"Échec application MIN_SL_PCT ({e})"

    out_path = Path(args.out)
    with PdfPages(out_path) as pdf:
        # Page 1: Summary
        fig1 = plt.figure()
        ax1 = fig1.add_subplot(111); ax1.axis("off")
        lines = [
            "Rapport — Paper trading BTC",
            f"Profil frais: {profile}",
            f"Break-even (fees+slip+buffer): {break_even*100:.3f} %",
            f"Trades pris en compte: {len(rets)}",
        ]
        if min_tp_curr is not None:
            lines.append(f"TP minimal courant (MIN_TP_PCT): {min_tp_curr*100:.3f} %")
        if min_sl_curr is not None:
            lines.append(f"SL minimal courant (MIN_SL_PCT): {min_sl_curr*100:.3f} %")
        if applied_tp_line:
            lines.append(applied_tp_line)
        if applied_sl_line:
            lines.append(applied_sl_line)
        lines.append("")
        lines.append("Recommandations TP par taille:")
        for size, best in recs:
            tp = best["tp"]; hr = best["hit_rate"]; net = best["net_per_trade"]
            tp_s = f"{tp*100:.3f} %" if tp is not None else "n/a"
            lines.append(f"- {int(size)} USDT: TP* = {tp_s} | hit={hr:.3f} | net/trade=${net:.4f}")
        # SL recommendation
        lines.append("")
        lines.append(f"SL recommandé: {sl_reco*100:.3f} %  (méthode: {method}, pertes observées: {n_losses})")
        if n_losses < 5:
            lines.append("⚠️ Peu de pertes observées (<5) → on garde le plancher pour éviter un SL trop optimiste.")
        ax1.text(0.02, 0.98, "\n".join(lines), va="top", ha="left")
        pdf.savefig(fig1, bbox_inches="tight"); plt.close(fig1)

        # Page 2: Net/trade overlay
        fig2 = plt.figure()
        ax2 = fig2.add_subplot(111)
        xs = [tp*100 for tp in tps]
        for size in sizes:
            ys = []
            for tp in tps:
                hit = sum(1 for r in rets if r >= tp)
                n   = len(rets); hr  = (hit / n) if n > 0 else 0.0
                net = size * (tp - break_even) * hr
                ys.append(net)
            ax2.plot(xs, ys, label=f"{int(size)} USDT")
        ax2.set_title("Net/trade ($) vs TP (%) — tailles superposées")
        ax2.set_xlabel("TP (%)")
        ax2.set_ylabel("Net par trade (USDT)")
        ax2.axvline(break_even*100)
        ax2.legend()
        pdf.savefig(fig2, bbox_inches="tight"); plt.close(fig2)

        # Page 3: Hit rate vs TP
        fig3 = plt.figure()
        ax3 = fig3.add_subplot(111)
        hr_y = []
        for tp in tps:
            hit = sum(1 for r in rets if r >= tp)
            n   = len(rets); hr  = (hit / n) if n > 0 else 0.0
            hr_y.append(hr*100.0)
        ax3.plot(xs, hr_y)
        ax3.set_title("Hit rate (%) vs TP (%)")
        ax3.set_xlabel("TP (%)")
        ax3.set_ylabel("Hit rate (%)")
        pdf.savefig(fig3, bbox_inches="tight"); plt.close(fig3)

        # Page 4: Loss distribution + SL marker (if any losses)
        if n_losses > 0:
            fig4 = plt.figure()
            ax4 = fig4.add_subplot(111)
            losses_pct = [x*100.0 for x in losses]
            bins = min(20, max(5, int(len(losses_pct)/2)))
            ax4.hist(losses_pct, bins=bins, alpha=0.8)
            ax4.set_title("Distribution des pertes absolues (%)")
            ax4.set_xlabel("Perte (%)"); ax4.set_ylabel("Fréquence")
            ax4.axvline(sl_reco*100.0)
            pdf.savefig(fig4, bbox_inches="tight"); plt.close(fig4)

    print(str(out_path))

if __name__ == "__main__":
    main()
