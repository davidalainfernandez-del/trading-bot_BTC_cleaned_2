"""
Run while the Flask app is up (PORT env or 5000). Simple smoke tests.
"""
import os, requests, sys, json

PORT = int(os.getenv("PORT", "5000"))
BASE = f"http://127.0.0.1:{PORT}"
ok = True

def check(path):
    global ok
    try:
        r = requests.get(BASE + path, timeout=3)
        print(path, r.status_code, r.text[:200])
        if r.status_code != 200:
            ok = False
    except Exception as e:
        print(path, "ERR", e)
        ok = False

check("/api/ping")

print("OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
