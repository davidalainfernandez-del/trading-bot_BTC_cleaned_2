#!/usr/bin/env python3
from __future__ import annotations
"""
autotrade_monitor_v2.1.py — flexible ticker endpoints
-----------------------------------------------------
Ajouts vs v2 :
- --no-ticker pour ignorer complètement le mark price
- --ticker-url-template pour définir explicitement l’URL du ticker. Utilise {base} et {symbol}.
  Ex: --ticker-url-template "{base}/api/price?symbol={symbol}"
- Si non fourni, essaie une liste d’endpoints courants automatiquement.
- Parsing plus robuste (dict, list, clé 'data', 'result', etc.).
"""
from common.http import HTTP as _HTTP

import argparse, time, os
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional, Iterable
import csv, requests

CSV_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
CSV_PATH = os.path.join(CSV_DIR, "monitor_autotrade.csv")

def _get(url: str, timeout: float = 8.0) -> Any:
    try:
        r = _HTTP.get(url, timeout=timeout)
        r.raise_for_status()
        ct = r.headers.get("content-type", "").lower()
        if "json" in ct or r.text.strip().startswith(('{','[', '"')):
            return r.json()
        return r.text
    except Exception as e:
        print(f"[WARN] GET {url} failed: {e}")
        return None

def _parse_portfolio(pf: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    if not isinstance(pf, dict):
        return None, None
    for k in ("net_value_usdt", "gross_value_usdt", "equity", "equity_usdt"):
        v = pf.get(k)
        if isinstance(v, (int, float)):
            cash = pf.get("cash_usdt") if isinstance(pf.get("cash_usdt"), (int, float)) else None
            return float(v), float(cash) if cash is not None else None
    cash = pf.get("cash_usdt")
    equity = 0.0
    if isinstance(cash, (int, float)):
        equity += float(cash)
    pos = pf.get("positions") or []
    if isinstance(pos, list):
        for p in pos:
            try:
                qty = float(p.get("qty", 0.0))
                last = p.get("last", p.get("mark_price", p.get("price", 0.0)))
                last = float(last)
                equity += qty * last
            except Exception:
                pass
    return (equity if equity != 0.0 else None), (float(cash) if isinstance(cash, (int, float)) else None)

def _parse_perf_day(perf: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    if isinstance(perf, dict):
        # parfois encapsulé
        for key in ("data", "result"):
            if isinstance(perf.get(key), dict):
                perf = perf[key]
                break
        usd = perf.get("pnl_day_usd")
        pct = perf.get("pnl_day_pct")
        return (float(usd) if isinstance(usd, (int, float)) else None,
                float(pct) if isinstance(pct, (int, float)) else None)
    return None, None

def ensure_csv_header(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        import builtins
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["timestamp","equity","cash","mark_price","pnl_day_usd","pnl_day_pct"])    

def append_row(path: str, row: Dict[str, Any]):
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            row.get("timestamp"), row.get("equity"), row.get("cash"),
            row.get("mark_price"), row.get("pnl_day_usd"), row.get("pnl_day_pct")
        ])

def _extract_price_from_json(symbol: str, payload: Any) -> Optional[float]:
    def try_fields(d: Dict[str, Any]) -> Optional[float]:
        for k in ("mark_price", "last", "price", "close", "c", "p"):
            if k in d:
                try:
                    return float(d[k])
                except Exception:
                    pass
        return None

    if payload is None:
        return None
    # direct dict
    if isinstance(payload, dict):
        # nested containers
        for key in ("data", "result", "ticker", "tickers"):
            if key in payload:
                nested = payload[key]
                if isinstance(nested, (list, tuple)) and nested:
                    # list with potential dicts
                    for item in nested:
                        if isinstance(item, dict) and (item.get("symbol") == symbol or not item.get("symbol")):
                            v = try_fields(item)
                            if v is not None:
                                return v
                elif isinstance(nested, dict):
                    v = try_fields(nested)
                    if v is not None:
                        return v
        # maybe symbol-keyed dict: {"BTCUSDT": {...}}
        if symbol in payload and isinstance(payload[symbol], dict):
            v = try_fields(payload[symbol])
            if v is not None:
                return v
        # plain dict with fields
        v = try_fields(payload)
        if v is not None:
            return v
    # list of dicts
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and (item.get("symbol") == symbol or not item.get("symbol")):
                v = try_fields(item)
                if v is not None:
                    return v
    return None

def _candidate_ticker_urls(base: str, symbol: str) -> Iterable[str]:
    paths = [
        "/api/ticker?symbol={symbol}",
        "/api/ticker/{symbol}",
        "/api/tickers?symbol={symbol}",
        "/api/tickers/{symbol}",
        "/api/price?symbol={symbol}",
        "/api/price/{symbol}",
        "/api/market/ticker?symbol={symbol}",
        "/api/market/ticker/{symbol}",
    ]
    for p in paths:
        yield f"{base}{p.format(symbol=symbol)}"

def fetch_mark_price(base: str, symbol: str, url_template: Optional[str]) -> Optional[float]:
    if url_template:
        url = url_template.format(base=base.rstrip('/'), symbol=symbol)
        payload = _get(url)
        return _extract_price_from_json(symbol, payload)
    for url in _candidate_ticker_urls(base.rstrip('/'), symbol):
        payload = _get(url)
        price = _extract_price_from_json(symbol, payload)
        if price is not None:
            return price
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:5000", help="Base URL de l'API du bot")
    ap.add_argument("--symbol", default="BTCUSDT", help="Symbole de référence pour le mark price")
    ap.add_argument("--poll", type=int, default=30, help="Période de polling en secondes")    
    ap.add_argument("--once", action="store_true", help="Ne fait qu'un seul poll puis s'arrête")    
    ap.add_argument("--plot", action="store_true", help="Trace les courbes depuis le CSV et sort")
    ap.add_argument("--no-ticker", action="store_true", help="N'interroge pas l'endpoint ticker")
    ap.add_argument("--ticker-url-template", default=None,
                    help="Modèle d'URL pour le ticker. Utilise {base} et {symbol}. Ex: {base}/api/price?symbol={symbol}")
    args = ap.parse_args()

    if args.plot:
        import pandas as pd
        import matplotlib.pyplot as plt
        if not os.path.exists(CSV_PATH):
            print(f"Aucun CSV trouvé à {CSV_PATH}")
            return
        df = pd.read_csv(CSV_PATH, parse_dates=["timestamp"]).sort_values("timestamp")
        if df.empty:
            print("CSV vide.")
            return
        plt.figure()
        plt.plot(df["timestamp"], df["equity"])
        plt.title("Equity dans le temps")
        plt.xlabel("Temps")
        plt.ylabel("Equity (USDT)")
        plt.tight_layout()
        plt.show()
        return

    ensure_csv_header(CSV_PATH)

    try:
        while True:
            now = datetime.now(timezone.utc).astimezone()
            pf = _get(f"{args.api}/api/portfolio/summary")
            perf = _get(f"{args.api}/api/perf/day")
            equity, cash = _parse_portfolio(pf if isinstance(pf, dict) else {})
            pnl_day_usd, pnl_day_pct = _parse_perf_day(perf if isinstance(perf, dict) else {})

            mark = None
            if not args.no_ticker:
                mark = fetch_mark_price(args.api, args.symbol, args.ticker_url_template)

            row = {
                "timestamp": now.isoformat(),
                "equity": float(equity) if equity is not None else None,
                "cash": float(cash) if cash is not None else None,
                "mark_price": float(mark) if mark is not None else None,
                "pnl_day_usd": float(pnl_day_usd) if pnl_day_usd is not None else None,
                "pnl_day_pct": float(pnl_day_pct) if pnl_day_pct is not None else None,
            }
            append_row(CSV_PATH, row)

            pnl_str = ""
            if (pnl_day_usd is not None) and (pnl_day_pct is not None):
                pnl_str = f" | PnL jour: {pnl_day_usd:.2f} USD ({pnl_day_pct:.2%})"
            price_str = f" price={row['mark_price']}" if row['mark_price'] is not None else " price=NA"

            eq = f"{row['equity']:.2f}" if row['equity'] is not None else "NA"
            c  = f"{row['cash']:.2f}" if row['cash'] is not None else "NA"
            print(f"[{now.strftime('%H:%M:%S')}] equity={eq} cash={c}{price_str}{pnl_str}")

            if args.once:
                break
            time.sleep(max(5, args.poll))
    except KeyboardInterrupt:
        print("\nArrêt demandé. CSV sauvegardé:", CSV_PATH)

if __name__ == "__main__":
    main()