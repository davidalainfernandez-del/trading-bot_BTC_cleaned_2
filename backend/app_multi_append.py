from common.http import HTTP as _HTTP

# ==============================
#   Multi-Actifs — Append Block
#   (safe to paste at END OF FILE)
# ==============================

# Liste des symboles USDT (modifiable via env SYMBOLS)
SYMBOLS = [
    s.strip().upper().replace("/", "")
    for s in os.getenv(
        "SYMBOLS",
        "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,PEPEUSDT,DOGEUSDT,LINKUSDT,XRPUSDT,ADAUSDT,AVAXUSDT",
    ).split(",")
    if s.strip()
]

# ---- Helpers (noms préfixés _ma_ pour éviter les collisions) ----
def _ma_last_prices_from_db(symbols):
    if not symbols: return {}
    conn = get_db(); c = conn.cursor()
    out = {}
    try:
        qmarks = ",".join("?"*len(symbols))
        rows = c.execute(f"""
            SELECT s.symbol, s.price
            FROM snapshots2 s
            JOIN (
              SELECT symbol, MAX(ts) AS mts FROM snapshots2 GROUP BY symbol
            ) t ON t.symbol = s.symbol AND t.mts = s.ts
            WHERE s.symbol IN ({qmarks})
        """, tuple(symbols)).fetchall()
        for sym, px in rows:
            if px is not None: out[(sym or "").upper()] = float(px)
    except Exception:
        pass
    return out

def _ma_http_price_binance(sym):
    try:
        r = _HTTP.get(
    "https://api.binance.com/api/v3/ticker/price",
    params={"symbol": sym.replace("/", "")},
    timeout=10,
)

        r.raise_for_status()
        return float(r.json()["price"])
    except Exception:
        return None

def _ma_get_last_price(sym):
    sym = sym.upper().replace("/", "")
    pxs = _ma_last_prices_from_db([sym])
    if sym in pxs: return pxs[sym]
    return _ma_http_price_binance(sym)

def _ma_binance_klines(symbol, interval="1m", limit=120):
    sym = symbol.upper().replace("/", "")
    r = _HTTP.get("https://api.binance.com/api/v3/klines",
                     params={"symbol": sym, "interval": interval, "limit": limit}, timeout=5)
    r.raise_for_status()
    return r.json()

# ---- Prix ----
@app.route("/api/price/ticker")
def api_price_ticker():
    symbol = (request.args.get("symbol") or "BTCUSDT").upper()
    px = _ma_get_last_price(symbol)
    return jsonify({"ok": True, "symbol": symbol, "price": px})

@app.route("/api/price/ohlc")
def api_price_ohlc():
    symbol = (request.args.get("symbol") or "BTCUSDT").upper()
    interval = request.args.get("interval", "1m")
    limit = int(request.args.get("limit", 120))
    rows = []
    try:
        if "ccxt" in globals() and ccxt is not None:
            market = f"{symbol[:3]}/{symbol[3:]}" if "/" not in symbol else symbol
            ex = ccxt.binance({"enableRateLimit": True, "options": {"adjustForTimeDifference": True}})
            ohlc = ex.fetch_ohlcv(market, timeframe=interval, limit=limit)
            rows = [dict(t=r[0], o=float(r[1]), h=float(r[2]), l=float(r[3]), c=float(r[4]), v=float(r[5])) for r in ohlc]
        else:
            kl = _ma_binance_klines(symbol, interval, limit)
            rows = [dict(t=int(k[0]), o=float(k[1]), h=float(k[2]), l=float(k[3]), c=float(k[4]), v=float(k[5])) for k in kl]
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "data": []}), 200
    return jsonify({"ok": True, "symbol": symbol, "data": rows})

@app.route("/api/price/avg20")
def api_price_avg20():
    symbol = (request.args.get("symbol") or "BTCUSDT").upper()
    # a) ccxt
    try:
        if "ccxt" in globals() and ccxt is not None:
            market = f"{symbol[:3]}/{symbol[3:]}" if "/" not in symbol else symbol
            ex = ccxt.binance({"enableRateLimit": True, "options": {"adjustForTimeDifference": True}})
            rows = ex.fetch_ohlcv(market, timeframe="1m", limit=20)
            if rows:
                avg = sum(r[4] for r in rows)/len(rows)
                return jsonify({"ok": True, "avg": float(avg)})
    except Exception:
        pass
    # b) DB snapshots2
    try:
        conn = get_db(); c = conn.cursor()
        rows = c.execute("SELECT price FROM snapshots2 WHERE symbol=? ORDER BY ts DESC LIMIT 20",(symbol,)).fetchall()
        pxs = [float(r[0]) for r in rows if r and r[0] is not None]
        if pxs:
            return jsonify({"ok": True, "avg": float(sum(pxs)/len(pxs))})
    except Exception:
        pass
    # c) REST klines
    try:
        kl = _ma_binance_klines(symbol, "1m", 20)
        closes = [float(k[4]) for k in kl]
        avg = sum(closes)/max(1,len(closes))
        return jsonify({"ok": True, "avg": float(avg)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ---- Résumé portefeuille ----
@app.route("/api/portfolio/summary")
def api_portfolio_summary():
    try:
        conn = get_db(); c = conn.cursor()
        cash = 200; pos = {}
        have_trades2 = False
        try:
            rows = c.execute("SELECT symbol, ts, side, price, qty, fee FROM trades2 ORDER BY ts ASC").fetchall()
            have_trades2 = True
        except Exception:
            rows = c.execute("SELECT ts, side, price, qty, fee FROM trades ORDER BY ts ASC").fetchall()
        if have_trades2:
            for sym, ts, side, price, qty, fee in rows:
                sym = (sym or "BTCUSDT").upper(); side=(side or "").lower()
                price=float(price or 0.0); qty=float(qty or 0.0); fee=float(fee or 0.0)
                if side=="buy":
                    cash -= price*qty + fee; pos[sym]=pos.get(sym,0.0)+qty
                elif side=="sell":
                    cash += price*qty - fee; pos[sym]=pos.get(sym,0.0)-qty
        else:
            base = (os.getenv("SYMBOL","BTC/USDT").replace("/","")).upper()
            for ts, side, price, qty, fee in rows:
                side=(side or "").lower(); price=float(price or 0.0); qty=float(qty or 0.0); fee=float(fee or 0.0)
                if side=="buy":
                    cash -= price*qty + fee; pos[base]=pos.get(base,0.0)+qty
                elif side=="sell":
                    cash += price*qty - fee; pos[base]=pos.get(base,0.0)-qty
        syms_needed = sorted(set(list(pos.keys()) + SYMBOLS))
        pxs = _ma_last_prices_from_db(syms_needed)
        for s in syms_needed:
            if s not in pxs:
                p = _ma_http_price_binance(s)
                if p is not None: pxs[s]=p
        net = cash; positions=[]
        for s,q in sorted(pos.items()):
            last = float(pxs.get(s,0.0))
            positions.append({"symbol": s, "qty": float(q), "last": last})
            net += float(q)*last
        return jsonify({"ok": True, "symbols": SYMBOLS, "cash_usdt": float(cash), "positions": positions, "net_value_usdt": float(net)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ---- Trades ----
@app.route("/api/trades")
def api_trades():
    symbol = (request.args.get("symbol") or "").upper().strip()
    limit  = int(request.args.get("limit", 100))
    conn = get_db(); c = conn.cursor()
    out = []
    try:
        if symbol:
            rows = c.execute("""SELECT id, ts, side, price, qty, fee, order_type, maker, slippage
                                FROM trades2 WHERE symbol = ? ORDER BY ts DESC LIMIT ?""",(symbol,limit)).fetchall()
        else:
            rows = c.execute("""SELECT id, ts, side, price, qty, fee, order_type, maker, slippage, symbol
                                FROM trades2 ORDER BY ts DESC LIMIT ?""",(limit,)).fetchall()
        for r in rows:
            d = dict(id=r[0], ts=float(r[1]), side=r[2], price=float(r[3] or 0), qty=float(r[4] or 0),
                     fee=float(r[5] or 0), order_type=r[6], maker=int(r[7] or 0), slippage=float(r[8] or 0))
            d["symbol"] = (symbol or r[9] if len(r) > 9 else symbol) or "BTCUSDT"
            out.append(d)
        return jsonify({"ok": True, "trades": out})
    except Exception:
        # fallback ancienne table
        rows = c.execute("""SELECT id, ts, side, price, qty, fee, order_type, maker, slippage
                            FROM trades ORDER BY ts DESC LIMIT ?""",(limit,)).fetchall()
        for r in rows:
            out.append(dict(id=r[0], ts=float(r[1]), side=r[2], price=float(r[3] or 0),
                            qty=float(r[4] or 0), fee=float(r[5] or 0),
                            order_type=r[6], maker=int(r[7] or 0), slippage=float(r[8] or 0)))
        return jsonify({"ok": True, "trades": out})

# ---- Décisions ----
def _ma_momentum_signal(symbol):
    try:
        conn = get_db(); c = conn.cursor()
        rows = c.execute("SELECT price FROM snapshots2 WHERE symbol=? ORDER BY ts DESC LIMIT 20",(symbol,)).fetchall()
        closes = [float(r[0]) for r in rows if r and r[0] is not None]
        if len(closes) < 5: return ("hold", 0.0, "not-enough-data")
        ma20 = sum(closes)/len(closes); ma5 = sum(closes[:5])/5.0
        score = (ma5 - ma20)/max(1e-9, ma20)
        if score > 0.001:  return ("buy",  min(1.0, abs(score)*100), "ma5>ma20")
        if score < -0.001: return ("sell", min(1.0, abs(score)*100), "ma5<ma20")
        return ("hold", abs(score), "flat")
    except Exception:
        return ("hold", 0.0, "error")

@app.route("/api/decisions/now")
def api_decisions_now():
    symbol = (request.args.get("symbol") or "BTCUSDT").upper()
    action, conf, reason = _ma_momentum_signal(symbol)
    return jsonify({"ok": True, "symbol": symbol, "action": action, "confidence": conf, "reason": reason, "ts": time.time()*1000})

@app.route("/api/decisions/recent")
def api_decisions_recent():
    symbol = (request.args.get("symbol") or "").upper().strip()
    limit  = int(request.args.get("limit", 10))
    out = []
    conn = get_db(); c = conn.cursor()
    if symbol:
        rows = c.execute("SELECT ts, side, price, qty FROM trades2 WHERE symbol=? ORDER BY ts DESC LIMIT ?", (symbol, limit)).fetchall()
        for ts, side, price, qty in rows:
            act = "buy" if (side or "").lower()=="buy" else "sell"
            out.append({"ts": float(ts), "symbol": symbol, "action": act, "score": None})
    else:
        rows = c.execute("SELECT symbol, ts, side, price, qty FROM trades2 ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        for sym, ts, side, price, qty in rows:
            act = "buy" if (side or "").lower()=="buy" else "sell"
            out.append({"ts": float(ts), "symbol": sym, "action": act, "score": None})
    return jsonify({"ok": True, "items": out})

# ---- Stats rapides ----
def _ma_compute_stats(symbol):
    conn = get_db(); c = conn.cursor()
    rows = c.execute("SELECT ts, side, price, qty, fee FROM trades2 WHERE symbol=? ORDER BY ts ASC",(symbol,)).fetchall()
    lots = []; realized = []
    for ts, side, price, qty, fee in rows:
        side=(side or '').lower(); price=float(price or 0); qty=float(qty or 0); fee=float(fee or 0)
        if side=='buy':
            lots.append([qty, price])
        elif side=='sell':
            remaining=qty
            while remaining>1e-12 and lots:
                q0,p0 = lots[0]
                use = min(remaining, q0)
                pnl = (price-p0)*use - fee*(use/qty if qty>0 else 0)
                realized.append(pnl)
                q0 -= use; remaining -= use
                if q0<=1e-12: lots.pop(0)
                else: lots[0]=[q0,p0]
    n=len(realized)
    return {"trades": n, "avg_pnl": (sum(realized)/n if n>0 else None), "win_rate": (sum(1 for x in realized if x>0)/n if n>0 else None)}

@app.route("/api/stats/quick")
def api_stats_quick():
    symbol = (request.args.get("symbol") or "BTCUSDT").upper()
    return jsonify({"ok": True, **_ma_compute_stats(symbol)})

# ---- Logs & News (vides si pas peuplés) ----
@app.route("/api/logs")
def api_logs():
    symbol = (request.args.get("symbol") or "").upper().strip()
    limit = int(request.args.get("limit", 50))
    try:
        conn = get_db(); c = conn.cursor()
        if symbol:
            rows = c.execute("SELECT ts, level, line FROM logs2 WHERE symbol=? ORDER BY ts DESC LIMIT ?", (symbol,limit)).fetchall()
            lines = [f"{int(ts)} [{level}] {line}" for ts, level, line in rows]
            return jsonify({"ok": True, "symbol": symbol, "lines": lines})
        else:
            rows = c.execute("SELECT symbol, ts, level, line FROM logs2 ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
            blocks = {}
            for sym, ts, level, line in rows:
                blocks.setdefault(sym or "NA", []).append(f"{int(ts)} [{level}] {line}")
            lines = [f"### {sym}\n" + "\n".join(ls) for sym, ls in blocks.items()]
            return jsonify({"ok": True, "lines": lines})
    except Exception:
        return jsonify({"ok": True, "symbol": symbol, "lines": []})

@app.route("/api/news")
def api_news():
    symbol = (request.args.get("symbol") or "").upper().strip()
    limit = int(request.args.get("limit", 12))
    try:
        conn = get_db(); c = conn.cursor()
        if symbol:
            rows = c.execute("SELECT ts, title, url, source FROM news2 WHERE symbol=? ORDER BY ts DESC LIMIT ?", (symbol,limit)).fetchall()
            items = [dict(ts=float(ts), title=title, url=url, source=source) for ts, title, url, source in rows]
            return jsonify({"ok": True, "symbol": symbol, "items": items})
        else:
            out = {}
            for sym in SYMBOLS:
                rows = c.execute("SELECT ts, title, url, source FROM news2 WHERE symbol=? ORDER BY ts DESC LIMIT ?", (sym,limit)).fetchall()
                out[sym] = [dict(ts=float(ts), title=title, url=url, source=source) for ts, title, url, source in rows]
            return jsonify({"ok": True, "items": out})
    except Exception:
        return jsonify({"ok": True, "symbol": symbol, "items": []})

# ---- Sentiment (instant + séries + corrélation) ----
@app.route("/api/sentiment/price")
def api_sentiment_price():
    symbol = (request.args.get("symbol") or "BTCUSDT").upper()
    try:
        from sentiment_sources import get_sentiment_features  # si dispo dans ton projet
        feats = get_sentiment_features()
        out = {"ok": True, "symbol": symbol}; out.update(feats or {})
        return jsonify(out)
    except Exception:
        return jsonify({"ok": True, "symbol": symbol, "tw_ema": 0.0, "rd_ema": 0.0, "nw_ema": 0.0, "tr_ema": 0.0})

@app.route("/api/sentiment/series")
def api_sentiment_series():
    symbol = (request.args.get("symbol") or "BTCUSDT").upper()
    return jsonify({"ok": True, "symbol": symbol, "series": []})

@app.route("/api/sentiment_correlation")
def api_sentiment_correlation():
    symbol = (request.args.get("symbol") or "BTCUSDT").upper()
    return jsonify({"ok": True, "symbol": symbol, "corr": None, "n": 0, "series": []})

# ---- ML status (stub) ----
@app.route("/api/ml/status")
def api_ml_status():
    symbol = (request.args.get("symbol") or "BTCUSDT").upper()
    return jsonify({"ok": True, "symbol": symbol, "counts": {"raw": None, "labeled": None}, "last_ts": {}})

# ---- Autotrader (stub global) ----
_AUTOTRADE_STATE = {"paused": True, "status": "paused", "last_ts": None, "current": None, "queue": []}

@app.route("/api/autotrade_state")
def api_autotrade_state():
    return jsonify({**_AUTOTRADE_STATE})

@app.route("/api/autotrade_toggle", methods=["POST"])
def api_autotrade_toggle():
    _AUTOTRADE_STATE["paused"] = not _AUTOTRADE_STATE.get("paused", True)
    _AUTOTRADE_STATE["status"] = "running" if not _AUTOTRADE_STATE["paused"] else "paused"
    _AUTOTRADE_STATE["last_ts"] = time.time()*1000
    return jsonify({**_AUTOTRADE_STATE})

# ---- Simulation rapide ----
@app.route("/api/sim/quick", methods=["POST"])
def api_sim_quick():
    data = request.get_json(force=True) if request.data else {}
    symbol = (data.get("symbol") or "BTCUSDT").upper()
    usdt = float(data.get("usdt") or 0.0)
    tpsl = str(data.get("tpsl") or "")
    px = _ma_get_last_price(symbol) or 0.0
    if usdt <= 0 or px <= 0:
        return jsonify({"ok": False, "summary": "inputs invalides"}), 400
    qty = usdt / px
    try:
        tp, sl = 1.0, 0.5
        if "/" in tpsl:
            a,b = tpsl.split("/",1); tp = float(a); sl = float(b)
        elif tpsl:
            tp = float(tpsl)
    except Exception:
        tp, sl = 1.0, 0.5
    px_tp = px * (1 + tp/100.0)
    px_sl = px * (1 - sl/100.0)
    summary = f"Buy {symbol}: px={px:.4f}, qty={qty:.8f}, TP={tp:.2f}%→{px_tp:.4f}, SL={sl:.2f}%→{px_sl:.4f}"
    return jsonify({"ok": True, "summary": summary})

# ---- Strategy Presets ----
_PRESETS = [
    {"key":"conservative","name":"Conservateur"},
    {"key":"balanced","name":"Équilibré"},
    {"key":"aggressive","name":"Agressif"},
]

@app.route("/api/strategy/presets")
def api_strategy_presets():
    return jsonify({"ok": True, "presets": _PRESETS})

@app.route("/api/strategy/apply", methods=["POST"])
def api_strategy_apply():
    data = request.get_json(force=True) if request.data else {}
    symbol = (data.get("symbol") or "BTCUSDT").upper()
    key = (data.get("preset") or "balanced").strip()
    try:
        conn = get_db(); c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS strategy_presets(symbol TEXT PRIMARY KEY, preset_key TEXT)")
        c.execute("INSERT OR REPLACE INTO strategy_presets(symbol, preset_key) VALUES(?,?)", (symbol, key))
        conn.commit()
    except Exception:
        pass
    return jsonify({"ok": True, "symbol": symbol, "preset": key})