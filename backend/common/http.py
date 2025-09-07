from __future__ import annotations
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .config import HTTP_TIMEOUT
import time, os
from functools import lru_cache

def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("HEAD","GET","POST","PUT","DELETE","PATCH","OPTIONS"),
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s

HTTP = make_session()

def get(url, **kwargs):
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    return HTTP.get(url, **kwargs)

def post(url, **kwargs):
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    return HTTP.post(url, **kwargs)

def put(url, **kwargs):
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    return HTTP.put(url, **kwargs)

def delete(url, **kwargs):
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    return HTTP.delete(url, **kwargs)

def head(url, **kwargs):
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    return HTTP.head(url, **kwargs)

def patch(url, **kwargs):
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    return HTTP.patch(url, **kwargs)


# simple in-process cache for GET requests by (url, sorted params) with short TTL
_CACHE = {}
CACHE_TTL_GET = float(os.getenv("CACHE_TTL_GET", "2"))

def _cache_key(url: str, **kwargs):
    params = kwargs.get("params")
    key_params = tuple(sorted(params.items())) if isinstance(params, dict) else params
    return (url, key_params)

def get(url, **kwargs):
    ttl = kwargs.pop("cache_ttl", CACHE_TTL_GET)
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    if ttl and ttl > 0:
        k = _cache_key(url, **kwargs)
        now = time.time()
        hit = _CACHE.get(k)
        if hit and now - hit[0] < ttl:
            return hit[1]
        resp = HTTP.get(url, **kwargs)
        _CACHE[k] = (now, resp)
        return resp
    return HTTP.get(url, **kwargs)
