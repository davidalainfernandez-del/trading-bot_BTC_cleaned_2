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
    c.execute("""CREATE TABLE IF NOT EXISTS trades2(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        ts REAL NOT NULL,
        side TEXT NOT NULL,
        price REAL NOT NULL,
        qty REAL NOT NULL,
        fee REAL DEFAULT 0,
        order_type TEXT,
        maker INTEGER DEFAULT 0,
        slippage REAL DEFAULT 0
    )""")
    migrated = 0
    try:
        rows = c.execute("SELECT ts, side, price, qty, fee, order_type, maker, slippage FROM trades ORDER BY ts ASC").fetchall()
        base_sym = SYMBOL.replace("/", "").upper()
        for ts, side, price, qty, fee, order_type, maker, slippage in rows:
            c.execute("""INSERT INTO trades2(symbol, ts, side, price, qty, fee, order_type, maker, slippage)
                         VALUES(?,?,?,?,?,?,?,?,?)""",
                      (base_sym, float(ts), str(side), float(price), float(qty),
                       0.0 if fee is None else float(fee),
                       order_type, 0 if maker is None else int(maker),
                       0.0 if slippage is None else float(slippage)))
            migrated += 1
        db.commit()
        print(f"Migré {migrated} trades vers trades2[{base_sym}]  (DB: {DB_PATH})")
    except sqlite3.OperationalError:
        print("Table trades introuvable, rien à migrer (ok).")
    db.close()

if __name__ == "__main__":
    main()
