#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv, json, math, os, sys
from urllib.request import urlopen

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")
OUT = os.environ.get("OUT", "paper_roundtrips.csv")

def fetch(endpoint):
    with urlopen(BASE_URL.rstrip('/') + endpoint) as r:
        return json.loads(r.read().decode("utf-8"))

def load_existing(path):
    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []

def save_rows(path, rows):
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def main():
    data = fetch("/api/trades")
    if not data.get("ok"):
        print("No trades from API.", file=sys.stderr); sys.exit(1)
    tr = data.get("items", [])

    # Build FIFO lots and closed roundtrips with normalized return
    lots = []  # each: [qty, total_cost_usdt]
    out = []
    for row in tr:
        side  = (row.get("side") or "").lower()
        ts    = float(row.get("time") or row.get("ts") or 0.0)
        px    = float(row.get("price") or 0.0)
        qty   = float(row.get("qty") or 0.0)
        fee   = float(row.get("fee") or 0.0)

        if qty <= 0 or px <= 0: 
            continue

        if side == "buy":
            lots.append([qty, px*qty + fee, ts, px])
        elif side == "sell":
            remain = qty
            proceeds = px*qty - fee
            alloc_cost = 0.0
            alloc_ts_first = None
            alloc_px_first = None
            while remain > 1e-12 and lots:
                lqty, lcost, lts, lpx = lots[0]
                use = min(lqty, remain)
                unit_cost = (lcost / lqty) if lqty > 0 else 0.0
                alloc_cost += unit_cost * use
                if alloc_ts_first is None:
                    alloc_ts_first = float(lts)
                    alloc_px_first = float(lpx)
                lqty -= use; remain -= use
                if lqty <= 1e-12:
                    lots.pop(0)
                else:
                    lots[0][0] = lqty
                    lots[0][1] = unit_cost * lqty
            pnl = proceeds - alloc_cost
            # normalized return relative to allocated cost
            ret = (pnl / alloc_cost) if alloc_cost > 0 else 0.0
            out.append({
                "entry_ts": alloc_ts_first or ts,
                "exit_ts": ts,
                "entry_px": alloc_px_first or 0.0,
                "exit_px": px,
                "alloc_cost": round(alloc_cost, 8),
                "pnl": round(pnl, 8),
                "ret": round(ret, 8),
            })

    # Merge with previous (dedupe by entry+exit timestamp)
    prev = load_existing(OUT)
    key = lambda r: (str(r.get("entry_ts")), str(r.get("exit_ts")))
    seen = set(key(r) for r in prev)
    merged = prev[:]
    for r in out:
        k = key(r)
        if k not in seen:
            merged.append(r); seen.add(k)

    # Sort by exit_ts
    merged.sort(key=lambda r: float(r.get("exit_ts") or 0.0))
    save_rows(OUT, merged)
    print(f"Saved {len(merged)} rows to {OUT}")

if __name__ == "__main__":
    main()
