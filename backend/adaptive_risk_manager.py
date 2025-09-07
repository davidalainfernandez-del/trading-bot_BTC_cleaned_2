#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, csv, json, math, os, sys, time
from statistics import fmean
from urllib.request import urlopen, Request

def jget(url):
    with urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def jpost(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, method="POST", headers={"Content-Type":"application/json"}, data=data)
    with urlopen(req) as r:
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
    # FIFO; returns list of dicts with ret (pnl/alloc_cost)
    lots = []
    out = []
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
            alloc_cost = 0.0; entry_ts = None; entry_px = None
            while remain > 1e-12 and lots:
                lqty, lcost, lts, lpx = lots[0]
                use = min(lqty, remain)
                unit_cost = (lcost / lqty) if lqty > 0 else 0.0
                alloc_cost += unit_cost * use
                if entry_ts is None: entry_ts = float(lts); entry_px = float(lpx)
                lqty -= use; remain -= use
                if lqty <= 1e-12: lots.pop(0)
                else:
                    lots[0][0] = lqty
                    lots[0][1] = unit_cost * lqty
            pnl = proceeds - alloc_cost
            ret = (pnl / alloc_cost) if alloc_cost > 0 else 0.0
            out.append({"entry_ts": entry_ts or ts, "exit_ts": ts, "ret": ret})
    return out

def estimate_break_even(params):
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
    return fee_buy + fee_sell + slip + buf

def tp_grid_search(returns, break_even, size, tp_min, tp_max, tp_step):
    tp_min_eff = max(tp_min, break_even + 0.0001)
    tps = []
    v = tp_min_eff
    while v <= tp_max + 1e-12:
        tps.append(round(v, 8)); v += tp_step
    best = {"tp": None, "hit_rate": 0.0, "net": 0.0}
    n = len(returns)
    if n == 0: return best
    for tp in tps:
        hit = sum(1 for r in returns if r >= tp)
        hr = hit / n
        net = size * (tp - break_even) * hr
        if best["tp"] is None or net >= best["net"]:
            best = {"tp": tp, "hit_rate": hr, "net": net}
    if best["hit_rate"] == 0.0:
        best["tp"] = tp_min_eff
    return best


def losses_quantile(losses_abs, q):
    if not losses_abs: return None
    vs = sorted(losses_abs)
    idx = (len(vs)-1) * q
    lo = int(idx//1); hi = int(-(-idx//1))  # ceil
    if lo == hi: return vs[lo]
    frac = idx - lo
    return vs[lo]*(1-frac) + vs[hi]*frac

def recommend_tp_sl(returns, break_even, size, tp_grid, sl_quantile, sl_floor):
    best = tp_grid_search(returns, break_even, size, *tp_grid)
    losses = [abs(x) for x in returns if x < 0]
    if len(losses) >= 5:
        q = max(0.5, min(sl_quantile, 0.99))
        sl_rec = max(sl_floor, losses_quantile(losses, q))
        sl_method = f"quantile_{q:.2f}"
    else:
        sl_rec = sl_floor
        sl_method = "floor"
    return best, sl_rec, sl_method, len(losses)

def blend(values, weights):
    wsum = sum(weights)
    if wsum <= 0: return None
    return sum(v*w for v, w in zip(values, weights)) / wsum

def parse_windows(s):
    out = []
    for tok in s.split(","):
        tok = tok.strip()
        if not tok: continue
        if ":" in tok:
            n, w = tok.split(":", 1)
            out.append((int(n), float(w)))
        else:
            out.append((int(tok), None))
    return out

def main():
    ap = argparse.ArgumentParser(description="Adaptive TP/SL manager: per-trade updates + rolling windows ensemble.")
    ap.add_argument("--base-url", default="http://localhost:5000")
    ap.add_argument("--primary-size", type=float, default=50.0, help="Taille (USDT) utilisée pour l'optimisation TP.")
    ap.add_argument("--tp-min", type=float, default=0.002)
    ap.add_argument("--tp-max", type=float, default=0.015)
    ap.add_argument("--tp-step", type=float, default=0.0005)
    ap.add_argument("--sl-quantile", type=float, default=0.80)
    ap.add_argument("--sl-floor", type=float, default=0.0060)
    ap.add_argument("--windows", default="10:0.40,50:0.30,100:0.20,250:0.075,1000:0.025",
                    help="Liste 'N[:poids]' séparée par des virgules. Ex: '10:0.4,50:0.3,100:0.2,250:0.075,1000:0.025'")
    ap.add_argument("--apply", action="store_true", help="Appliquer automatiquement MIN_TP_PCT / MIN_SL_PCT.")
    ap.add_argument("--hysteresis-bps", type=float, default=2.0, help="Changement minimal (en bps) pour appliquer.")
    ap.add_argument("--cooldown-sec", type=float, default=1800.0, help="Délai minimal entre deux applications (sec).")
    ap.add_argument("--reevaluate-sec", type=float, default=900.0, help="Réévaluation périodique même sans nouveau trade.")
    ap.add_argument("--poll-sec", type=float, default=10.0, help="Période de scrutation des trades.")
    ap.add_argument("--dry-run", action="store_true", help="Ne pas appeler l'API de mise à jour, seulement logguer.")
    ap.add_argument("--log-csv", default="adaptive_risk_log.csv")
    args = ap.parse_args()

    base = args.base_url
    windows = parse_windows(args.windows)
    weights_user = [w for _, w in windows if w is not None]
    if weights_user and any(w is None for _, w in windows):
        print("Si vous fournissez un poids, fournissez-en pour tous les windows.", file=sys.stderr)
        sys.exit(1)
    # Default weights if none provided: inverse sqrt of window size, normalized
    if not weights_user:
        wsizes = [n for n, _ in windows]
        inv = [1.0 / math.sqrt(n) for n in wsizes]
        s = sum(inv); weights = [x/s for x in inv]
    else:
        w = [float(x) for x in weights_user]
        s = sum(w); weights = [x/s for x in w]

    # Initial state
    last_applied_tp = None
    last_applied_sl = None
    last_apply_ts = 0.0
    last_rt_count = -1
    last_reeval_ts = 0.0

    # Prepare log csv (header if missing)
    def log_row(row):
        hdr = list(row.keys())
        need_header = False
        try:
            with open(args.log_csv, "r", encoding="utf-8") as f:
                pass
        except Exception:
            need_header = True
        with open(args.log_csv, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=hdr)
            if need_header: w.writeheader()
            w.writerow(row)

    print("Adaptive manager started. Polling trades...")
    while True:
        try:
            params = fetch_params(base)
            be = estimate_break_even(params)
            trades = fetch_trades(base)
            rts = reconstruct_roundtrips(trades)
            n_rt = len(rts)

            now = time.time()
            should_reeval = (n_rt != last_rt_count) or (now - last_reeval_ts >= args.reevaluate_sec)

            if should_reeval and n_rt > 0:
                rets_all = [rt["ret"] for rt in rts]
                # Per-window recompute
                tp_list = []
                sl_list = []
                used_windows = []
                for i, (N, _) in enumerate(windows):
                    if n_rt < 1: break
                    seg = rets_all[-N:] if n_rt >= N else rets_all[:]
                    best, sl_rec, sl_method, n_losses = recommend_tp_sl(
                        seg, be, args.primary_size, (args.tp_min, args.tp_max, args.tp_step),
                        args.sl_quantile, args.sl_floor
                    )
                    tp_list.append(best["tp"] if best["tp"] is not None else args.tp_min)
                    sl_list.append(sl_rec)
                    used_windows.append(len(seg))

                tp_final = blend(tp_list, weights[:len(tp_list)])
                sl_final = max(sl_list) if sl_list else args.sl_floor  # conservative: max across windows

                # Safety bounds
                tp_final = max(be + 0.0001, min(args.tp_max, tp_final if tp_final is not None else args.tp_min))
                sl_final = max(args.sl_floor, min(0.03, sl_final))  # cap SL at 3%

                # Hysteresis check
                def changed_enough(prev, new):
                    if prev is None: return True
                    return abs(new - prev) >= (args.hysteresis_bps / 10000.0)

                can_apply = (now - last_apply_ts >= args.cooldown_sec)
                tp_ok = changed_enough(last_applied_tp, tp_final)
                sl_ok = changed_enough(last_applied_sl, sl_final)

                # Apply if allowed
                applied = {"tp": False, "sl": False}
                if args.apply and can_apply and (tp_ok or sl_ok):
                    try:
                        payload = {}
                        if tp_ok: payload["MIN_TP_PCT"] = float(tp_final)
                        if sl_ok: payload["MIN_SL_PCT"] = float(sl_final)
                        if payload and not args.dry_run:
                            jpost(base.rstrip('/') + "/api/params/update", payload)
                            applied["tp"] = tp_ok
                            applied["sl"] = sl_ok
                            last_apply_ts = now
                            if tp_ok: last_applied_tp = tp_final
                            if sl_ok: last_applied_sl = sl_final
                    except Exception as e:
                        print("Apply error:", e)

                # Log
                log_row({
                    "ts": int(now),
                    "n_roundtrips": n_rt,
                    "break_even_pct": be,
                    "tp_final": tp_final,
                    "sl_final": sl_final,
                    "tp_list": json.dumps(tp_list),
                    "sl_list": json.dumps(sl_list),
                    "weights": json.dumps(weights[:len(tp_list)]),
                    "windows_used": json.dumps(used_windows),
                    "applied_tp": applied["tp"],
                    "applied_sl": applied["sl"],
                })

                print(f"Reeval: N={n_rt} | be={be*100:.3f}% | TP*≈{tp_final*100:.3f}% | SL*≈{sl_final*100:.3f}% | applied={applied}")

                last_rt_count = n_rt
                last_reeval_ts = now

        except Exception as e:
            print("Loop error:", e)

        time.sleep(args.poll_sec)

if __name__ == "__main__":
    main()
