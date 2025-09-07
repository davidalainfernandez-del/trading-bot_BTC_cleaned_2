
#!/usr/bin/env python3
"""
analyze_trades_offline.py
-------------------------
But : analyser la rentabilité à partir d'un export /api/trades (JSON) ou d'un CSV des trades.
- Calcule PnL réalisé (FIFO), PnL non réalisé (via mark price fourni en argument), drawdown, Sharpe simple.
- Produit un rapport texte + un CSV enrichi + deux graphiques (equity reconstruit & drawdown).

Exemples
- python analyze_trades_offline.py --trades my_trades.json --mark 65000
- python analyze_trades_offline.py --trades my_trades.csv --price-col close  (si CSV avec colonnes)

Notes
- Le format des trades étant variable, le script essaie côté clefs courantes: time/timestamp, side, qty/amount, price, fee.
- Si vous passez aussi un fichier de prix (CSV OHLC), on peut reconstruire une equity curve plus réaliste.
"""

import argparse
import json
import os
from typing import Any, Dict, List, Tuple

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def _load_trades(path: str) -> pd.DataFrame:
    if path.lower().endswith(".json"):
        data = json.load(open(path, "r"))
    else:
        # CSV ou autre
        try:
            return pd.read_csv(path)
        except Exception as e:
            raise SystemExit(f"Impossible de lire {path}: {e}")

    # normaliser JSON (list/dict)
    if isinstance(data, dict):
        data = data.get("trades") or data.get("data") or data.get("items") or data.get("results") or list(data.values())[0]
    if not isinstance(data, list):
        raise SystemExit("Format JSON inattendu pour les trades.")

    rows = []
    for r in data:
        if not isinstance(r, dict):
            continue
        ts = r.get("timestamp") or r.get("time") or r.get("ts") or r.get("created_at")
        side = (r.get("side") or r.get("type") or "").lower()
        qty = r.get("qty") or r.get("amount") or r.get("size") or r.get("quantity")
        price = r.get("price") or r.get("avg_price") or r.get("fill_price")
        fee = r.get("fee") or r.get("fees") or 0.0
        rows.append({"time": ts, "side": side, "qty": qty, "price": price, "fee": fee})
    df = pd.DataFrame(rows)
    # nettoyage minimal
    df = df.dropna(subset=["side", "qty", "price"])
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["fee"] = pd.to_numeric(df["fee"], errors="coerce").fillna(0.0)
    df = df[df["qty"] > 0]
    df = df[df["price"] > 0]
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.sort_values("time")
    return df


def fifo_metrics(trades: pd.DataFrame, mark: float = None) -> Dict[str, float]:
    buys = []
    realized = 0.0
    pos_qty = 0.0
    for _, tr in trades.iterrows():
        side, qty, price = tr["side"], tr["qty"], tr["price"]
        if side == "buy":
            buys.append([qty, price])
            pos_qty += qty
        elif side == "sell":
            remaining = qty
            while remaining > 1e-12 and buys:
                lot_qty, lot_price = buys[0]
                take = min(remaining, lot_qty)
                realized += (price - lot_price) * take
                lot_qty -= take
                remaining -= take
                if lot_qty <= 1e-12:
                    buys.pop(0)
                else:
                    buys[0][0] = lot_qty
            pos_qty -= qty
    # vwap
    numer = sum(q*p for q, p in buys)
    denom = sum(q for q, _ in buys)
    vwap = numer / denom if denom else 0.0
    unrealized = (mark - vwap) * denom if (mark and denom) else 0.0
    return {"realized": realized, "unrealized": unrealized, "pos_qty": pos_qty, "vwap": vwap}


def equity_curve_from_trades(trades: pd.DataFrame, start_cash: float = 10_000.0) -> pd.DataFrame:
    """
    Reconstruit une equity curve naïve en supposant qu'on part avec start_cash USDT.
    """
    cash = start_cash
    inventory = 0.0
    equity = []
    for _, tr in trades.iterrows():
        side, qty, price = tr["side"], tr["qty"], tr["price"]
        if side == "buy":
            cost = qty * price
            cash -= cost
            inventory += qty
        else:
            revenue = qty * price
            cash += revenue
            inventory -= qty
        equity.append({"time": tr["time"], "equity": cash + inventory * price})
    df = pd.DataFrame(equity).set_index("time")
    df = df.asfreq("H").ffill()  # lisser à l'heure pour un graphe propre
    df["ret"] = df["equity"].pct_change().fillna(0.0)
    # drawdown
    roll_max = df["equity"].cummax()
    df["drawdown"] = df["equity"] / roll_max - 1.0
    return df


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--trades", required=True, help="Fichier JSON/CSV des trades")
    p.add_argument("--mark", type=float, default=None, help="Prix spot pour calculer l'unrealized")
    p.add_argument("--start-cash", type=float, default=10_000.0, help="Capital initial pour equity curve reconstruite")
    args = p.parse_args()

    trades = _load_trades(args.trades)
    if trades.empty:
        raise SystemExit("Pas de trades valides.")

    # FIFO metrics
    m = fifo_metrics(trades, mark=args.mark)
    print(f"Realized PnL: {m['realized']:.2f}")
    print(f"Unrealized PnL: {m['unrealized']:.2f}")
    print(f"Position qty: {m['pos_qty']:.6f} @ vwap {m['vwap']:.2f}")

    # Equity curve
    curve = equity_curve_from_trades(trades, start_cash=args.start_cash)
    curve.to_csv("equity_curve.csv")
    print("Equity curve -> equity_curve.csv")

    # KPI
    sharpe = (curve["ret"].mean() / (curve["ret"].std() + 1e-12)) * (365**0.5 * 24**0.5)
    max_dd = curve["drawdown"].min()
    print(f"Sharpe (approx): {sharpe:.2f} | Max Drawdown: {max_dd:.2%}")

    # Graphiques
    plt.figure()
    curve["equity"].plot(title="Equity (reconstruite depuis les trades)")
    plt.xlabel("Time"); plt.ylabel("Equity")
    plt.savefig("equity_curve.png", bbox_inches="tight")
    print("Graphique equity -> equity_curve.png")

    plt.figure()
    curve["drawdown"].plot(title="Drawdown")
    plt.xlabel("Time"); plt.ylabel("Drawdown")
    plt.savefig("drawdown.png", bbox_inches="tight")
    print("Graphique drawdown -> drawdown.png")


if __name__ == "__main__":
    main()
