#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, csv, json, math, sys
from urllib.request import urlopen, Request
from statistics import median

def fetch_params(base_url):
    try:
        with urlopen(base_url.rstrip('/') + "/api/params") as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {"ok": False}

def post_params(base_url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = Request(base_url.rstrip('/') + "/api/params/update", method="POST",
                  headers={"Content-Type": "application/json"}, data=data)
    with urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))

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
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return vs[lo]
    frac = idx - lo
    return vs[lo]*(1-frac) + vs[hi]*frac

def main():
    ap = argparse.ArgumentParser(description="Calcule un SL minimal basé sur un quantile des pertes observées (papier) et peut l'appliquer à l'API.")
    ap.add_argument("--base-url", default="http://localhost:5000")
    ap.add_argument("--history", default="paper_roundtrips.csv")
    ap.add_argument("--quantile", type=float, default=0.80, help="Quantile des pertes absolues (0.80 = 80e percentile).")
    ap.add_argument("--floor", type=float, default=0.0060, help="Plancher minimum si l'historique est trop optimiste (ex: 0.006 = 0.60%).")
    ap.add_argument("--apply", action="store_true", help="Appliquer la valeur via /api/params/update (MIN_SL_PCT).")
    ap.add_argument("--csv", default="sl_optim_results.csv")
    args = ap.parse_args()

    losses = load_losses(args.history)
    n = len(losses)
    params = fetch_params(args.base_url)

    # Default to floor if not enough data
    chosen = None
    method = "floor"
    if n >= 5:
        qv = quantile(losses, max(0.5, min(args.quantile, 0.99)))
        if qv is not None:
            chosen = max(args.floor, qv)
            method = f"quantile_{args.quantile:.2f}"
    if chosen is None:
        chosen = float(args.floor)

    # Optionally apply
    applied_ok = None
    if args.apply:
        try:
            res = post_params(args.base_url, {"MIN_SL_PCT": chosen})
            applied_ok = bool(res.get("ok"))
        except Exception as e:
            applied_ok = False

    # Save CSV summary
    import csv as _csv
    row = {
        "n_losses": n,
        "quantile": args.quantile,
        "floor": args.floor,
        "sl_recommended_pct": chosen,
        "method": method,
        "applied": applied_ok,
    }
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=list(row.keys()))
        w.writeheader(); w.writerow(row)

    # Print summary
    print(f"N_losses={n} | method={method} | SL*={chosen*100:.3f}% | applied={applied_ok} | csv={args.csv}")

if __name__ == "__main__":
    main()
