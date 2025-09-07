"""
Minimal multiclass logistic "stub" with online SGD-like API.
If no model is present in KV, sgd_mc_predict raises so caller can fallback.
"""
from __future__ import annotations
from typing import Callable, Dict, Any, List, Tuple, Optional
import json, math, random

MODEL_KEY = "mc_model_v1"

FEATURES = ["reddit_avg","twitter_ema","sig_tech","atr_pct","ema_slope","vol_norm","hour_of_day"]

def _softmax(z):
    m = max(z)
    e = [math.exp(v - m) for v in z]
    s = sum(e)
    return [v/s for v in e]

def sgd_mc_predict(row: Dict[str, Any], kv_get: Callable[[str, Any], Any]) -> Dict[str, float]:
    raw = kv_get(MODEL_KEY, None) if callable(getattr(kv_get, "__call__", None)) else None
    if not raw:
        raise RuntimeError("model missing")
    try:
        model = json.loads(raw)
    except Exception:
        raise RuntimeError("bad model")
    W = model.get("W"); b = model.get("b")
    if not W or not b:
        raise RuntimeError("bad model")
    # Build feature vector
    x = [float(row.get(f, 0.0)) for f in FEATURES]
    # Linear logits for 3 classes in order ["down","flat","up"]
    logits = [
        sum(wi*xi for wi, xi in zip(W[0], x)) + b[0],
        sum(wi*xi for wi, xi in zip(W[1], x)) + b[1],
        sum(wi*xi for wi, xi in zip(W[2], x)) + b[2],
    ]
    p = _softmax(logits)
    return {"down": float(p[0]), "flat": float(p[1]), "up": float(p[2])}

def sgd_mc_train_online(select_rows, kv_get, kv_set, limit: int = 2000) -> Dict[str,str]:
    """
    Very small "trainer": if there is no historical data, create a neutral model.
    Otherwise, random-initialize small weights. This is a stub to unblock runtime.
    Expect select_rows(sql, params) -> list[dict-like], but we don't depend on schema.
    """
    try:
        data = select_rows("SELECT 1 LIMIT ?", (min(limit, 2000),))
        # we don't actually use data here in the stub
    except Exception:
        data = []
    # neutral-ish model: small randoms to avoid NaN
    rnd = lambda: (random.random()-0.5)*0.02
    W = [[rnd() for _ in FEATURES] for _ in range(3)]
    b = [0.0, 0.0, 0.0]
    model = {"W": W, "b": b, "features": FEATURES}
    kv_set(MODEL_KEY, json.dumps(model))
    return {"status": "ok", "classes": "down,flat,up", "features": ",".join(FEATURES)}
