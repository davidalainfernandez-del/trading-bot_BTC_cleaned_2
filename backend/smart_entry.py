#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, json, time, sys
from urllib.request import urlopen, Request
from urllib.parse import urlencode

def get_json(url):
    with urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, method="POST", headers={"Content-Type": "application/json"}, data=data)
    with urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))

def fetch_last_close(base_url, symbol="BTCUSDT"):
    # fallback via OHLC 1m last close
    q = urlencode({"symbol": symbol, "interval": "1m", "limit": 1})
    url = base_url.rstrip("/") + "/api/price/ohlc?" + q
    js = get_json(url)
    if isinstance(js, dict) and js.get("items"):
        row = js["items"][-1]
        # accept several keys
        close = row.get("c") or row.get("close") or row.get("Close") or row.get("CLOSE")
        return float(close)
    raise RuntimeError("No price available from /api/price/ohlc")

def set_profile(base_url, prefer_maker, maker_fee=0.00075, taker_fee=0.0010, slippage=0.0002, buffer=0.0005):
    payload = {
        "PREFER_MAKER": bool(prefer_maker),
        "MAKER_FEE_BUY": float(maker_fee),
        "MAKER_FEE_SELL": float(maker_fee),
        "FEE_RATE_BUY": float(taker_fee),
        "FEE_RATE_SELL": float(taker_fee),
        "SLIPPAGE": float(slippage),
        "FEE_BUFFER_PCT": float(buffer)
    }
    return post_json(base_url.rstrip("/") + "/api/params/update", payload)

def manual_buy(base_url, usdt):
    return post_json(base_url.rstrip("/") + "/api/manual/buy", {"usdt": float(usdt)})

def main():
    ap = argparse.ArgumentParser(description="Entrée intelligente: tenter maker, basculer taker si non rempli dans le délai.")
    ap.add_argument("--base-url", default="http://localhost:5000")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--usdt", type=float, required=True, help="Montant USDT de l'ordre (ex: 20, 50).")
    ap.add_argument("--timeout-sec", type=float, default=5.0, help="Délai max avant bascule taker.")
    ap.add_argument("--poll-sec", type=float, default=0.5, help="Période de scrutation du prix.")
    ap.add_argument("--maker-offset-bps", type=float, default=2.0, help="Offset en bps sous le dernier prix pour tenter une 'remplissable' maker.")
    ap.add_argument("--maker-fee", type=float, default=0.00075)
    ap.add_argument("--taker-fee", type=float, default=0.0010)
    ap.add_argument("--slippage", type=float, default=0.0002)
    ap.add_argument("--buffer", type=float, default=0.0005)
    args = ap.parse_args()

    base = args.base_url
    sym = args.symbol

    # price snapshot and target
    last = fetch_last_close(base, sym)
    limit_px = last * (1.0 - args.maker_offset_bps / 10000.0)

    # Try to wait for dip (simulate maker fill opportunity)
    t0 = time.time()
    filled_maker = False
    while time.time() - t0 < args.timeout_sec:
        try:
            last_now = fetch_last_close(base, sym)
        except Exception:
            last_now = last
        if last_now <= limit_px:
            filled_maker = True
            break
        time.sleep(args.poll_sec)

    # Apply profile and buy
    if filled_maker:
        set_profile(base, prefer_maker=True, maker_fee=args.maker_fee, taker_fee=args.taker_fee,
                    slippage=args.slippage, buffer=args.buffer)
        res = manual_buy(base, args.usdt)
        print(json.dumps({"mode":"maker","limit_px":limit_px,"last_px":last_now,"buy_response":res}, ensure_ascii=False))
    else:
        # fallback to taker
        set_profile(base, prefer_maker=False, maker_fee=args.maker_fee, taker_fee=args.taker_fee,
                    slippage=args.slippage, buffer=args.buffer)
        res = manual_buy(base, args.usdt)
        print(json.dumps({"mode":"taker","limit_px":limit_px,"last_px":last_now,"buy_response":res}, ensure_ascii=False))
        # restore maker as default
        set_profile(base, prefer_maker=True, maker_fee=args.maker_fee, taker_fee=args.taker_fee,
                    slippage=args.slippage, buffer=args.buffer)

if __name__ == "__main__":
    main()
