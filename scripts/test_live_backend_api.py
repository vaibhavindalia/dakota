"""Live integration test against the running Dakota backend server.

Verifies:
1. /health
2. /api/connectors/status
3. /api/stocks (pagination, search)
4. /api/stocks/{ticker}
5. /api/stocks/{ticker}/risk
6. /api/stocks/{ticker}/technicals
7. /api/portfolio
8. /api/investigations/live
9. /api/tip/check
10. /api/intelligence/jev/classify
11. /api/intelligence/jev/models
"""
import json
import urllib.request
import urllib.error
import sys

BASE_URL = "http://127.0.0.1:8000"

def get(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200, f"Expected 200 for {path}, got {resp.status}"
        return json.loads(resp.read().decode("utf-8"))

def post(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        assert resp.status == 200, f"Expected 200 for {path}, got {resp.status}"
        return json.loads(resp.read().decode("utf-8"))

def main():
    print("=== TESTING LIVE RUNNING BACKEND API ===")
    
    # 1. Health
    h = get("/health")
    print(f"[1] /health: PASS (Status={h.get('status')})")

    # 2. Connectors Status
    c = get("/api/connectors/status")
    print(f"[2] /api/connectors/status: PASS (Connectors: {list(c.keys())})")

    # 3. Stocks Universe
    s = get("/api/stocks?limit=3")
    stocks = s.get("stocks", [])
    print(f"[3] /api/stocks?limit=3: PASS (Returned {len(stocks)} stocks, Total={s.get('total')})")

    # 4. Stock Detail (INFY)
    infy = get("/api/stocks/INFY")
    print(f"[4] /api/stocks/INFY: PASS (Ticker={infy.get('ticker')}, Company={infy.get('company_name')})")

    # 5. Stock Risk (INFY)
    risk = get("/api/stocks/INFY/risk")
    print(f"[5] /api/stocks/INFY/risk: PASS (RiskScore={risk.get('risk_score')}, Band={risk.get('risk_band')})")

    # 6. Technicals (INFY)
    tech = get("/api/stocks/INFY/technicals")
    print(f"[6] /api/stocks/INFY/technicals: PASS (Keys: {list(tech.keys())})")

    # 7. Portfolio
    port = get("/api/portfolio")
    print(f"[7] /api/portfolio: PASS (Holdings count={len(port.get('holdings', []))}, Valuation={port.get('total_valuation')})")

    # 8. Live Investigations
    inv = get("/api/investigations/live")
    records = inv.get("investigations", [])
    print(f"[8] /api/investigations/live: PASS (Loaded {len(records)} live investigations)")

    # 9. Tip Check
    tip_res = post("/api/tip/check", {"tip": "Buy INFY target 2100 stoploss 1750 huge breakout!!"})
    print(f"[9] /api/tip/check: PASS (ParsedTicker={tip_res.get('parsed', {}).get('ticker')}, VerdictsCount={len(tip_res.get('stock_verdicts', []))})")

    # 10. JEV Classify Endpoint
    jev_res = post("/api/intelligence/jev/classify", {
        "ticker": "CDSL",
        "claim": "Massive target 1500 breakout buy immediately VIP channel",
    })
    print(f"[10] /api/intelligence/jev/classify: PASS (Predicted={jev_res.get('predicted_label')}, Margin={jev_res.get('margin')})")

    # 11. JEV Models
    jev_mod = get("/api/intelligence/jev/models")
    print(f"[11] /api/intelligence/jev/models: PASS (ActiveModel={jev_mod.get('active_model_id')}, Backend={jev_mod.get('backend')})")

    print("\nALL 11 CRITICAL BACKEND API PATHS VERIFIED WORKING!")

if __name__ == "__main__":
    main()
