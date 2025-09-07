from __future__ import annotations
import os, sqlite3
def _default_db_path():
    here = os.path.dirname(__file__)
    cand = os.path.abspath(os.path.join(here, "..", "data", "app.db"))
    return cand
DB_PATH = os.getenv("DB_PATH") or _default_db_path()
SYMBOL = os.getenv("SYMBOL", "BTC/USDT")
def main():
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS snapshots2(
        symbol TEXT NOT NULL,
        ts REAL NOT NULL,
        price REAL,
        PRIMARY KEY(symbol, ts)
    )""")
    migrated = 0
    try:
        rows = c.execute("SELECT ts, price FROM snapshots ORDER BY ts ASC").fetchall()
        base_sym = SYMBOL.replace("/", "").upper()
        for ts, px in rows:
            c.execute("INSERT OR IGNORE INTO snapshots2(symbol, ts, price) VALUES(?,?,?)",
                      (base_sym, float(ts), None if px is None else float(px)))
            migrated += 1
        db.commit()
        print(f"Migré {migrated} lignes vers snapshots2[{base_sym}]  (DB: {DB_PATH})")
    except sqlite3.OperationalError:
        print("Table snapshots introuvable, rien à migrer (ok).")
    db.close()

if __name__ == "__main__":
    main()
