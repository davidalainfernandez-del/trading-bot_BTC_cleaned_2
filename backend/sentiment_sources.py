# sentiment_sources.py
# Sources de sentiments (Twitter/X + Reddit + News) avec VADER, cache TTL et EMA lissé.

from __future__ import annotations
import os, time, statistics
from typing import List, Dict, Tuple
import requests
from common.http import HTTP as _HTTP
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# feedparser est optionnel (RSS). Si non installé, on ignore gentiment.
try:
    import feedparser  # type: ignore
except Exception:
    feedparser = None

# ---------------------------------------------------------------------
# VADER + lexique crypto
# ---------------------------------------------------------------------
_VADER = SentimentIntensityAnalyzer()
_VADER.lexicon.update({
    "bull": 2.0, "bullish": 2.5, "bull-run": 2.2, "moon": 2.2, "mooning": 2.4,
    "pump": 1.6, "pumps": 1.6, "pumped": 1.6, "rally": 1.8, "rallies": 1.8,
    "bid": 0.5, "bids": 0.5, "breakout": 1.4, "breakouts": 1.4,
    "bear": -2.0, "bearish": -2.5, "dump": -1.9, "dumps": -1.9, "dumped": -1.9,
    "rug": -3.0, "rugpull": -3.0, "liquidation": -2.0, "liquidations": -2.0,
    "hawkish": -1.2, "dovish": 1.0,
    "inflows": 0.6, "outflows": -0.6,
    "ETF": 0.2, "ETFs": 0.2, "spot-ETF": 0.4,
    "all-time-high": 2.5, "ath": 2.0,
    "capitulation": -2.2, "panic": -2.0, "fear": -1.6, "greed": 0.8,
})

# cooldown / rate-limit côté Twitter
_RATE = {"until": 0.0}  # epoch seconds jusqu’à quand on évite de requêter

# ---------------------------------------------------------------------
# Cache en mémoire de process
# ---------------------------------------------------------------------
_CACHE: Dict[str, object] = {
    # Twitter
    "tw_ts": 0.0,         # dernier recalcul
    "tw_avg": 0.0,        # moyenne brute
    "tw_ema": 0.0,        # ema lissée
    "tw_median": 0.0,     # médiane
    "tw_count": 0,        # nb de tweets scorés
    "tw_top_pos": [],     # [(score, text), ...]
    "tw_top_neg": [],
    "tw_rate_limited": False,
    "tw_reset_epoch": None,

    # Reddit
    "rd_ts": 0.0,
    "rd_avg": 0.0,
    "rd_count": 0,

    # News agrégées (RSS + CryptoCompare + Stocktwits)
    "nw_ts": 0.0,
    "nw_avg": 0.0,
    "nw_count": 0,
}

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _sent_score(txt: str) -> float:
    if not txt:
        return 0.0
    try:
        s = _VADER.polarity_scores(txt)
        return float(s.get("compound", 0.0))  # [-1, 1]
    except Exception:
        return 0.0

def _top_pos_neg(texts: List[str], scores: List[float], k: int = 5) -> Tuple[List[Tuple[float, str]], List[Tuple[float, str]]]:
    pairs = list(zip(scores, texts))
    if not pairs:
        return [], []
    pairs.sort(key=lambda x: x[0])
    neg = pairs[:k]
    pos = pairs[-k:][::-1]
    return pos, neg

# ---------------------------------------------------------------------
# Twitter/X (API v2 bearer)
# ---------------------------------------------------------------------
def _twitter_fetch_recent(max_results: int | None = None) -> List[str]:
    """Retourne une liste de textes de tweets récents (lang:en). Respecte un cooldown si rate-limité."""
    token = (os.getenv("TW_BEARER", "") or os.getenv("TWITTER_BEARER_TOKEN", "")).strip()
    if not token:
        _CACHE["tw_rate_limited"] = False
        _CACHE["tw_reset_epoch"] = None
        return []

    now = time.time()
    if now < float(_RATE.get("until", 0.0)):
        _CACHE["tw_rate_limited"] = True
        _CACHE["tw_reset_epoch"] = float(_RATE["until"])
        return []

    q = os.getenv("TW_QUERY") or os.getenv("TWITTER_QUERY") or "(bitcoin OR btc) lang:en -is:retweet -is:reply"
    mr = max_results if max_results is not None else int(os.getenv("TWITTER_MAX_RESULTS", "50"))
    mr = max(10, min(100, int(mr)))

    url = "https://api.twitter.com/2/tweets/search/recent"
    params = {"query": q, "max_results": mr, "tweet.fields": "lang,created_at"}

    try:
        r = _HTTP.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=10)
        if r.status_code == 429:
            cooldown = int(os.getenv("TW_RATE_LIMIT_COOLDOWN", "900"))  # 15 min par défaut
            _RATE["until"] = now + cooldown
            _CACHE["tw_rate_limited"] = True
            _CACHE["tw_reset_epoch"] = float(_RATE["until"])
            return []
        if r.status_code in (401, 403):
            _RATE["until"] = now + int(os.getenv("TW_AUTH_ERROR_COOLDOWN", "3600"))
            _CACHE["tw_rate_limited"] = True
            _CACHE["tw_reset_epoch"] = float(_RATE["until"])
            return []

        r.raise_for_status()
        data = r.json().get("data") or []
        texts = [d.get("text", "") for d in data if (d.get("lang") or "en").startswith("en")]
        _CACHE["tw_rate_limited"] = False
        _CACHE["tw_reset_epoch"] = None
        return texts
    except requests.RequestException:
        return []

def _twitter_stats() -> None:
    """Rafraîchit le cache Twitter : avg, median, count, tops."""
    texts = _twitter_fetch_recent()
    if not texts:
        return
    scores = [_sent_score(t) for t in texts if t]
    if not scores:
        return
    avg = float(sum(scores) / len(scores))
    med = float(statistics.median(scores))
    pos, neg = _top_pos_neg(texts, scores, k=5)
    _CACHE["tw_avg"] = avg
    _CACHE["tw_median"] = med
    _CACHE["tw_count"] = int(len(scores))
    _CACHE["tw_top_pos"] = [(float(s), str(t)) for (s, t) in pos]
    _CACHE["tw_top_neg"] = [(float(s), str(t)) for (s, t) in neg]

def _twitter_avg() -> float:
    """Compat: renvoie la dernière moyenne brute (utilisé par anciens appels)."""
    texts = _twitter_fetch_recent()
    if not texts:
        return float(_CACHE.get("tw_avg", 0.0))
    scores = [_sent_score(t) for t in texts]
    return float(sum(scores) / len(scores)) if scores else float(_CACHE.get("tw_avg", 0.0))

# ---------------------------------------------------------------------
# Reddit (PRAW si creds, sinon fallback JSON public)
# ---------------------------------------------------------------------
def _reddit_fetch_titles_public(n: int = 50) -> List[str]:
    """Fallback gratuit via JSON public reddit.com (limité mais fiable)."""
    headers = {"User-Agent": os.getenv("REDDIT_USER_AGENT", "trading-bot/1.0")}
    subs = [s.strip() for s in os.getenv("REDDIT_SUBS", "Bitcoin,btc,CryptoCurrency").split(",") if s.strip()]
    out: List[str] = []
    per = max(10, min(100, n))
    for sub in subs:
        url = f"https://www.reddit.com/r/{sub}/new.json?limit={per}"
        try:
            r = _HTTP.get(url, headers=headers, timeout=10)
            if r.status_code == 429:
                time.sleep(1)
                continue
            j = r.json()
            for ch in (j.get("data", {}).get("children") or []):
                d = ch.get("data") or {}
                out.append(f"{d.get('title','')} {d.get('selftext','') or ''}")
                if len(out) >= n:
                    return out
        except Exception:
            continue
    return out[:n]

def _reddit_fetch_titles(n: int = 50) -> List[str]:
    """Essaie PRAW avec credentials; sinon bascule vers JSON public."""
    cid  = os.getenv("REDDIT_CLIENT_ID", os.getenv("REDDIT_CLIENTID", "")).strip()
    csec = os.getenv("REDDIT_CLIENT_SECRET", os.getenv("REDDIT_SECRET", "")).strip()
    user = os.getenv("REDDIT_USERNAME", "").strip()
    pwd  = os.getenv("REDDIT_PASSWORD", "").strip()
    ua   = os.getenv("REDDIT_USER_AGENT", "trading-bot/1.0")

    if not (cid and csec and user and pwd):
        return _reddit_fetch_titles_public(n)

    try:
        import praw  # runtime import
    except Exception:
        return _reddit_fetch_titles_public(n)

    try:
        reddit = praw.Reddit(
            client_id=cid,
            client_secret=csec,
            username=user,
            password=pwd,
            user_agent=ua,
        )
        subs = [s.strip() for s in os.getenv("REDDIT_SUBS", "Bitcoin,btc,cryptocurrency").split(",") if s.strip()]
        texts: List[str] = []
        per = max(10, min(100, n))
        for sub in subs:
            try:
                for p in reddit.subreddit(sub).new(limit=per):
                    texts.append(f"{getattr(p,'title','')} {getattr(p,'selftext','') or ''}")
                    if len(texts) >= n:
                        return texts
            except Exception:
                continue
        return texts if texts else _reddit_fetch_titles_public(n)
    except Exception:
        return _reddit_fetch_titles_public(n)

def _reddit_stats() -> None:
    texts = _reddit_fetch_titles()
    if not texts:
        _CACHE["rd_count"] = 0
        return
    scores = [_sent_score(t) for t in texts if t]
    if not scores:
        _CACHE["rd_count"] = 0
        _CACHE["rd_avg"] = 0.0
        return
    _CACHE["rd_avg"] = float(sum(scores) / len(scores))
    _CACHE["rd_count"] = int(len(scores))

def _reddit_avg() -> float:
    """Compat: renvoie la dernière moyenne reddit (recalcule si possible)."""
    texts = _reddit_fetch_titles()
    if not texts:
        return float(_CACHE.get("rd_avg", 0.0))
    scores = [_sent_score(t) for t in texts]
    return float(sum(scores) / len(scores)) if scores else float(_CACHE.get("rd_avg", 0.0))

# ---------------------------------------------------------------------
# News gratuites (RSS + CryptoCompare + Stocktwits)
# ---------------------------------------------------------------------
def _news_rss_titles(n: int = 50) -> List[str]:
    """CoinDesk / CoinTelegraph / Decrypt / Bitcoin Magazine via RSS (si feedparser dispo)."""
    if not feedparser:
        return []
    feeds = [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
        "https://bitcoinmagazine.com/.rss/full",
    ]
    titles: List[str] = []
    per = max(10, min(100, n))
    for url in feeds:
        try:
            d = feedparser.parse(url)
            for e in (getattr(d, "entries", []) or [])[:per]:
                titles.append(f"{getattr(e,'title','')} {getattr(e,'summary','') or ''}")
        except Exception:
            continue
        if len(titles) >= n:
            break
    return titles[:n]

def _cryptocompare_titles(n: int = 50) -> List[str]:
    """CryptoCompare News (clé API optionnelle, pas nécessaire pour les bases)."""
    url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
    headers = {}
    api_key = os.getenv("CRYPTOCOMPARE_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Apikey {api_key}"
    try:
        r = _HTTP.get(url, headers=headers, timeout=10)
        res = (r.json().get("Data") or [])[:max(10, min(200, n))]
        return [f"{it.get('title','')} {it.get('body','') or ''}" for it in res]
    except Exception:
        return []

def _stocktwits_titles(n: int = 50) -> List[str]:
    """Flux public Stocktwits (BTC.X par défaut)."""
    symbol = os.getenv("STOCKTWITS_SYMBOL", "BTC.X").strip() or "BTC.X"
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
    try:
        r = _HTTP.get(url, timeout=10)
        msgs = (r.json().get("messages") or [])[:max(10, min(100, n))]
        return [m.get("body", "") for m in msgs]
    except Exception:
        return []

def _news_all_texts(n: int = 120) -> List[str]:
    """Agrège plusieurs sources de news/grain retail. Contrôlable via variables d'env."""
    texts: List[str] = []
    if os.getenv("NEWS_ENABLE_RSS", "1") != "0":
        texts += _news_rss_titles(n // 2)
    if os.getenv("NEWS_ENABLE_CRYPTOCOMPARE", "1") != "0":
        texts += _cryptocompare_titles(n // 2)
    if os.getenv("NEWS_ENABLE_STOCKTWITS", "1") != "0":
        texts += _stocktwits_titles(n // 2)
    # dédoublonnage simple
    seen = set()
    uniq = []
    for t in texts:
        t2 = (t or "").strip()
        if not t2: 
            continue
        key = t2.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t2)
        if len(uniq) >= n:
            break
    return uniq

def _news_stats() -> None:
    """Calcule la moyenne de sentiment des news agrégées."""
    n_fetch = max(30, min(300, int(os.getenv("NEWS_FETCH_COUNT", "120"))))
    texts = _news_all_texts(n_fetch)
    scores = [_sent_score(t) for t in texts if t]
    if not scores:
        _CACHE["nw_avg"] = 0.0
        _CACHE["nw_count"] = 0
        return
    _CACHE["nw_avg"] = float(sum(scores) / len(scores))
    _CACHE["nw_count"] = int(len(scores))

# ---------------------------------------------------------------------
# API publique: features sentiments avec cache + EMA
# ---------------------------------------------------------------------
def get_sentiment_features(now_ts: float | None = None) -> Dict[str, object]:
    """
    Renvoie un dict avec caches récents + EMA (TTL configurable).
    Clés utiles pour /api/sentiment_twitter et les autres endpoints :
      - twitter_avg (== moyenne brute), twitter_ema, twitter_median, tw_count
      - tw_top_pos, tw_top_neg (listes [ [score, text], ... ])
      - twitter_rate_limited (bool), twitter_reset_epoch (epoch seconds ou None)
      - reddit_avg, rd_count
      - news_avg (alias nw_avg), nw_count
    """
    import time as _time
    if now_ts is None:
        now_ts = _time.time()

    ttl = float(
        os.getenv("SENTIMENT_TTL")
        or os.getenv("TWITTER_TTL")
        or os.getenv("REDDIT_TTL")
        or "120"
    )
    alpha = float(os.getenv("TW_SMOOTH_EMA") or os.getenv("TWITTER_EMA_ALPHA") or "0.35")

    # Reddit (TTL)
    if (now_ts - float(_CACHE.get("rd_ts", 0.0))) > ttl:
        try:
            _reddit_stats()
        except Exception:
            pass
        _CACHE["rd_ts"] = now_ts

    # Twitter (TTL)
    if (now_ts - float(_CACHE.get("tw_ts", 0.0))) > ttl:
        try:
            _twitter_stats()
        except Exception:
            pass
        _CACHE["tw_ts"] = now_ts

    # News (TTL)
    if (now_ts - float(_CACHE.get("nw_ts", 0.0))) > ttl:
        try:
            _news_stats()
        except Exception:
            pass
        _CACHE["nw_ts"] = now_ts

    # EMA mise à jour à chaque appel (sur la base du dernier tw_avg)
    prev = float(_CACHE.get("tw_ema", 0.0))
    raw  = float(_CACHE.get("tw_avg", 0.0))
    ema  = raw if prev == 0.0 else (alpha * raw + (1 - alpha) * prev)
    _CACHE["tw_ema"] = float(ema)

    return {
        # Reddit
        "reddit_avg": float(_CACHE.get("rd_avg", 0.0)),
        "rd_count": int(_CACHE.get("rd_count", 0)),

        # Twitter
        "twitter_avg": float(_CACHE.get("tw_avg", 0.0)),   # alias pratique
        "twitter_raw": float(_CACHE.get("tw_avg", 0.0)),
        "twitter_ema": float(_CACHE.get("tw_ema", 0.0)),
        "twitter_median": float(_CACHE.get("tw_median", 0.0)),
        "tw_count": int(_CACHE.get("tw_count", 0)),
        "tw_top_pos": list(_CACHE.get("tw_top_pos", [])),
        "tw_top_neg": list(_CACHE.get("tw_top_neg", [])),
        "twitter_rate_limited": bool(_CACHE.get("tw_rate_limited", False)),
        "twitter_reset_epoch": _CACHE.get("tw_reset_epoch", None),

        # News agrégées
        "news_avg": float(_CACHE.get("nw_avg", 0.0)),
        "nw_avg": float(_CACHE.get("nw_avg", 0.0)),   # alias
        "nw_count": int(_CACHE.get("nw_count", 0)),
    }

# ---------------------------------------------------------------------
# Ingestion manuelle optionnelle (webhook ou tests)
# ---------------------------------------------------------------------
def ingest_twitter_texts(texts: List[str]) -> Dict[str, object]:
    """Permet d'injecter des textes (ex: depuis un webhook) et de mettre à jour le cache Twitter."""
    import time as _time
    if not texts:
        return get_sentiment_features()
    scores = [_sent_score(t) for t in texts if t]
    avg = float(sum(scores) / len(scores)) if scores else 0.0
    med = float(statistics.median(scores)) if scores else 0.0
    pos, neg = _top_pos_neg(texts, scores, k=5)

    _CACHE["tw_avg"] = avg
    _CACHE["tw_median"] = med
    _CACHE["tw_count"] = int(len(scores))
    _CACHE["tw_top_pos"] = [(float(s), str(t)) for (s, t) in pos]
    _CACHE["tw_top_neg"] = [(float(s), str(t)) for (s, t) in neg]
    _CACHE["tw_ts"] = _time.time()
    # EMA sera mis à jour au prochain get_sentiment_features()
    return get_sentiment_features()