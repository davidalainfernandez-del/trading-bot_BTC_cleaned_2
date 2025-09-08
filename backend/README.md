```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env   # à créer ci-dessous
cd backend && python app.py
```bash
cat > backend/.env.example <<'EOF'
BINANCE_TESTNET=1
BINANCE_API_KEY=u9X6jySR9sxwd511w1hespJB9bsDLOKTJo0vPfgKjrBpFRSdBCgkh2uS2MNFBcnN
BINANCE_API_SECRET=JDvB5qEeZ3LoQ3gU6p2M3x5THu5pOs8QpOHjlXRqZuHOuDdWLYeIkuWB5IKAHQbD
SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
TZ=Europe/Zurich
HTTP_TIMEOUT=10
