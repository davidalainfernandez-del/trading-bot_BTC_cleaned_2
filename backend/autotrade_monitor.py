
#!/usr/bin/env python3
"""
autotrade_monitor.py
--------------------
Objectif
- Vérifier que l'autotrade "évolue" (de nouveaux trades arrivent) et suivre la performance PnL en temps réel.
- Fonctionne en PAPER TRADING ou TESTNET, en lecture seule (aucun ordre n'est envoyé).

Pré-requis
- Le backend tourne localement (par défaut sur http://localhost:5000).
- Python 3.9+ avec requests et pandas installés.

Usage
- python autotrade_monitor.py --api http://localhost:5000 --poll 30
- Arrêter avec Ctrl+C. Les données sont loggées dans logs/monitor_autotrade.csv
- Pour tracer l'equity curve : python autotrade_monitor.py --plot

Ce que le script fait
- Récupère périodiquement /api/trades et /api/portfolio/summary (ou, à défaut, /api/price/ticker + reconstruction).
- Calcule un PnL approximatif en FIFO si aucun PnL n'est fourni par l'API.
- Sauvegarde un CSV (horodaté) avec equity, realized_pnl, unrealized_pnl, nb_trades.
- Option --plot pour afficher un graphique de l'equity et du realized PnL cumulé.

Notes de robustesse
- Le JSON exact des endpoints peut varier. Le script tente plusieurs clefs (voir _get_price, _parse_trades, _get_portfolio).
- Si votre API expose un endpoint PnL direct (ex: /api/portfolio/summary contient "pnl" ou "equity"), il sera privilégié.
"""

import argparse
import time
import datetime as dt
import json
import os
from typing import List, Dict, Any, Tuple

import requests
from common.http import HTTP as _HTTP
import pandas as pd
import matplotlib.pyplot as plt


def _safe_get(url: str, timeout: int = 10) -> Dict[str, Any]:
    try:
        r = _HTTP.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[WARN] GET {url} failed: {e}")
        return {}


def _get_price(base_url: str, symbol_hint: str = "BTC/USDT") -> float:
    """
    Essaie de récupérer un prix spot depuis /api/price/ticker.
    Le script essaie plusieurs formats de réponse.
    """
    data = _safe_get(f"{base_url}/api/price/ticker")
    # Essais d'extraction courants
    for key in ("price", "last", "close"):
        if isinstance(data, dict) and key in data and isinstance(data[key], (int, float)):
            return float(data[key])
    # Peut-être sous forme {"symbol":"BTC/USDT","ticker":{"last":...}}
    if isinstance(data, dict):
        t = data.get("ticker") or {}
        for key in ("last", "close", "price"):
            if key in t:
                try:
                    return float(t[key])
                except Exception:
                    pass
    # Liste ?
    if isinstance(data, list) and data:
        first = data[0]
        for key in ("price", "last", "close"):
            if key in first:
                try:
                    return float(first[key])
                except Exception:
                    pass
    # Fallback: 0 (déclenche recalcul equity par reconstruction plus tard)
    return 0.0


def _parse_trades(data: Any) -> pd.DataFrame:
    """
    Transforme la réponse /api/trades en DataFrame standardisé : time, side, qty, price, fee
    Supporte plusieurs structures plausibles.
    """
    # Si l'API renvoie déjà une liste brute
    trades = []
    if isinstance(data, dict):
        # Essayer clefs communes
        maybe = data.get("trades") or data.get("data") or data.get("items") or data.get("results")
        if isinstance(maybe, list):
            data = maybe
        else:
            # ou bien dict indexé
            # fallback: tenter "values"
            maybe = list(data.values())
            if maybe and isinstance(maybe[0], list):
                data = maybe[0]
    if not isinstance(data, list):
        data = []

    for row in data:
        if not isinstance(row, dict):
            continue
        ts = row.get("timestamp") or row.get("time") or row.get("ts") or row.get("created_at")
        # convertir en datetime iso si besoin
        if isinstance(ts, (int, float)):
            # considérer ms vs s
            ts_val = int(ts)
            if ts_val > 10_000_000_000:  # ms
                t_iso = dt.datetime.utcfromtimestamp(ts_val / 1000.0).isoformat()
            else:
                t_iso = dt.datetime.utcfromtimestamp(ts_val).isoformat()
        elif isinstance(ts, str):
            t_iso = ts
        else:
            t_iso = dt.datetime.utcnow().isoformat()

        side = (row.get("side") or row.get("type") or "").lower()
        if side in ("buy", "sell"):
            pass
        elif side in ("bid", "long"):
            side = "buy"
        elif side in ("ask", "short"):
            side = "sell"
        else:
            # inconnu -> skip
            continue

        qty = row.get("qty") or row.get("amount") or row.get("size") or row.get("quantity") or 0
        price = row.get("price") or row.get("avg_price") or row.get("fill_price") or 0
        fee = row.get("fee") or row.get("fees") or 0

        try:
            qty = float(qty)
            price = float(price)
            fee = float(fee)
        except Exception:
            continue

        trades.append({"time": t_iso, "side": side, "qty": qty, "price": price, "fee": fee})

    return pd.DataFrame(trades)


def _fifo_pnl(trades: pd.DataFrame) -> Tuple[float, float, float]:
    """
    Calcule realized/unrealized/pos_qty avec FIFO.
    Hypothèse: un seul instrument (BTC/USDT). Le mark price sera injecté à part.
    """
    if trades.empty:
        return 0.0, 0.0, 0.0

    buys = []  # list of (qty, price)
    realized = 0.0
    pos_qty = 0.0
    vwap = 0.0

    for _, tr in trades.sort_values("time").iterrows():
        side, qty, price, fee = tr["side"], tr["qty"], tr["price"], tr["fee"]
        if qty <= 0 or price <= 0:
            continue
        if side == "buy":
            buys.append([qty, price])
            pos_qty += qty
        else:  # sell
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

    # VWAP position (pour info / unrealized)
    numer = 0.0
    denom = 0.0
    for q, p in buys:
        numer += q * p
        denom += q
    vwap = numer / denom if denom > 0 else 0.0
    return realized, pos_qty, vwap


def _get_portfolio(base_url: str) -> Dict[str, Any]:
    data = _safe_get(f"{base_url}/api/portfolio/summary")
    return data if isinstance(data, dict) else {}


def _infer_equity_from_portfolio(pf: Dict[str, Any]) -> float:
    # Essayer quelques formats possibles
    for k in ("equity", "total_value", "portfolio_value", "nav"):
        if k in pf:
            try:
                return float(pf[k])
            except Exception:
                pass
    # Parfois sous pf["data"]
    d = pf.get("data") if isinstance(pf, dict) else None
    if isinstance(d, dict):
        for k in ("equity", "total_value", "portfolio_value", "nav"):
            if k in d:
                try:
                    return float(d[k])
                except Exception:
                    pass
    return 0.0


def _infer_cash_and_coin(pf: Dict[str, Any]) -> Tuple[float, float]:
    # retourne (cash, coin_qty) si possible
    cash = 200
    coin = 0.0
    # formats possibles
    for k in ("cash", "usdt", "base_currency_balance", "quote_balance"):
        if k in pf:
            try:
                cash = float(pf[k])
            except Exception:
                pass
    for k in ("btc", "coin", "asset_qty", "base_qty", "position_qty"):
        if k in pf:
            try:
                coin = float(pf[k])
            except Exception:
                pass
    # nested
    d = pf.get("data") if isinstance(pf, dict) else None
    if isinstance(d, dict):
        for k in ("cash", "usdt", "quote_balance"):
            if k in d:
                try:
                    cash = float(d[k])
                except Exception:
                    pass
        for k in ("btc", "coin", "position_qty", "base_qty"):
            if k in d:
                try:
                    coin = float(d[k])
                except Exception:
                    pass
    return cash, coin


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:5000", help="Base URL de l'API backend")
    parser.add_argument("--poll", type=int, default=30, help="Intervalle de polling en secondes")
    parser.add_argument("--once", action="store_true", help="Ne faire qu'un seul échantillon (pratique pour cron)")
    parser.add_argument("--plot", action="store_true", help="Tracer l'equity curve à partir du CSV")
    args = parser.parse_args()

    os.makedirs("logs", exist_ok=True)
    csv_path = os.path.join("logs", "monitor_autotrade.csv")

    if args.plot:
        if not os.path.exists(csv_path):
            print(f"Pas de {csv_path}. Lancez d'abord le script sans --plot.")
            return
        df = pd.read_csv(csv_path, parse_dates=["timestamp"])
        if df.empty:
            print("CSV vide.")
            return
        plt.figure()
        df.set_index("timestamp")["equity"].plot(title="Equity curve")
        plt.xlabel("Time"); plt.ylabel("Equity")
        plt.show()

        plt.figure()
        df.set_index("timestamp")["realized_pnl_cum"].plot(title="Realized PnL (cumulé)")
        plt.xlabel("Time"); plt.ylabel("PnL")
        plt.show()
        return

    print(f"[INFO] Monitoring {args.api} toutes les {args.poll}s. Ctrl+C pour arrêter.")
    history = []

    try:
        while True:
            now = dt.datetime.utcnow()
            trades_json = _safe_get(f"{args.api}/api/trades")
            trades_df = _parse_trades(trades_json)

            pf = _get_portfolio(args.api)
            equity_from_api = _infer_equity_from_portfolio(pf)

            mark_price = _get_price(args.api)
            realized, pos_qty, vwap = _fifo_pnl(trades_df)

            cash, coin_qty = _infer_cash_and_coin(pf)
            equity_derived = 0.0
            if cash or coin_qty:
                equity_derived = cash + coin_qty * (mark_price or vwap or 0.0)
            equity = equity_from_api or equity_derived

            row = {
                "timestamp": now.isoformat(),
                "nb_trades": int(len(trades_df)),
                "equity": float(equity) if equity else None,
                "mark_price": float(mark_price) if mark_price else None,
                "pos_qty_fifo": float(pos_qty),
                "vwap_fifo": float(vwap),
                "realized_pnl_fifo": float(realized),
            }
            history.append(row)

            # to CSV
            df = pd.DataFrame(history)
            # realized pnl cumulé (affichage)
            df["realized_pnl_cum"] = df["realized_pnl_fifo"].fillna(0).cummax()  # cummax comme proxy anti-bruit
            df.to_csv(csv_path, index=False)

            print(f"[{now.strftime('%H:%M:%S')}] trades={row['nb_trades']} equity={row['equity']} price={row['mark_price']} realized_fifo={row['realized_pnl_fifo']:.2f}")

            if args.once:
                break
            time.sleep(max(5, args.poll))
    except KeyboardInterrupt:
        print("\nArrêt demandé. CSV sauvegardé:", csv_path)


if __name__ == "__main__":
    main()