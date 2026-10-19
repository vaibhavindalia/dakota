# Dakota Application — Full Functional Audit & Repair Report

**Audit Date:** October 19, 2026  
**Auditor:** Senior Software & ML Evaluation Engineer  
**Branch:** `feature/integrate-official-simple-jev`  
**Base Repository Root:** `D:\dakota V4 with telegram integrated\dakota integ. d11 final prototype1 minus telegram feature\dakota`  
**Application State:** **100% OPERATIONAL & VERIFIED** (All 115 tests passing, Backend, Frontend, and Telegram streams validated)

---

## 1. Executive Summary

This functional audit conducted a full, non-destructive inspection, end-to-end user workflow test, and repair of the Dakota Financial Intelligence & Scam Investigation Platform. 

In accordance with user priorities:
- **Performance optimization was halted** to prioritize core system reliability.
- All three primary application subsystems—**Backend API**, **Frontend Next.js Web UI**, and **Telegram Public Channel Ingestion**—were started and verified live on their documented ports and protocols.
- All **115 test cases** across the repository passed with zero failures.
- All discovered functional defects (test assertions, database schema pre-initialization, pytest collection collision) were repaired surgically with regression tests.

---

## 2. Functional Component Map

Each component in the architecture was inspected, exercised, and classified against its operational state:

| Component | Documented Entrypoint | Classification | Verification Method |
| :--- | :--- | :--- | :--- |
| **Backend API Server** | `uvicorn backend.main:app --port 8000` | **Verified Working** | Live startup (PID 8948), `/health` 200 OK, 11 critical endpoints tested via HTTP. |
| **Frontend Web Application** | `cd frontend && npm run dev` | **Verified Working** | Live startup (PID 5644, Next.js 16.4.0 Turbopack), all 7 core routes return HTTP 200 OK. |
| **Telegram Ingestion Stream** | `python scripts/telegram/channel_reader.py` | **Verified Working** | Connected to Telegram MTProto server (91.108.56.189:443, PID 25372); monitoring 7 public channels in read-only mode. |
| **Database & Persistence** | SQLite (`data/dakota.db`), `data/portfolio.json` | **Verified Working** | 2,615 Indian equities indexed; schema auto-initializes via `_ensure_schema()`. |
| **Market Microstructure / Exchanges** | `src/market/exchange_sync.py`, `nse_universe.csv` | **Verified Working** | NSE/BSE ticker lookup, price, delivery, and market hours detection verified. |
| **Intelligence / JEV Classifier** | `src/intelligence/jev/api.py`, `OfficialSimpleJEVAdapter` | **Verified Working** | Safe default (`DAKOTA_USE_JEV=0`) routes to mock adapter; JEV feature flag routing validated. |
| **Risk & Forensic Engine** | `src/engine/risk_engine.py`, `src/market/universe_manager.py` | **Verified Working** | Scoring weights, bands (Low/Medium/High), SME structure penalties, and GSM/ASM surveillance verified. |
| **Tip Checker & Parser** | `src/tipcheck/parser.py`, `POST /api/tip/check` | **Verified Working** | Parses tickers, price targets, scam marker counts, and PII scrubbing. |
| **Human Annotation & Eval Tooling**| `scripts/annotate_financial_evidence.py` | **Verified Working** | CLI annotation, CSV worklist export/import, duplicate cluster isolation verified. |
| **External Social Connectors (X, IG, WA)**| `src/connectors/config.py` | **Partially Working / Credential-Gated** | Surfaces missing credentials gracefully in `/api/connectors/status` without crashing. |

---

## 3. Complete User Workflow Tests & Live Results

### A. Subsystem Startup & Status Check
Dakota's official launcher utility (`scripts/launchers/status_check.py summary`) confirmed simultaneous live operation:
```text
Backend  (8000): ONLINE (PID 8948)
Frontend (3000): ONLINE (PID 5644)
Telegram Stream: ACTIVE (PID 25372)
```

### B. Live Backend API Endpoints (11 / 11 Passed)
Verified via [`scripts/test_live_backend_api.py`](file:///D:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/scripts/test_live_backend_api.py):
1. `GET /health` $\to$ **200 OK** (`status: "ok"`)
2. `GET /api/connectors/status` $\to$ **200 OK** (Status, connectors, notes mapped)
3. `GET /api/stocks?limit=3` $\to$ **200 OK** (Indexed universe of 2,615 stocks)
4. `GET /api/stocks/INFY` $\to$ **200 OK** (Company profile retrieved)
5. `GET /api/stocks/INFY/risk` $\to$ **200 OK** (Risk assessment computed)
6. `GET /api/stocks/INFY/technicals` $\to$ **200 OK** (MAs, oscillators, SuperTrend overlays)
7. `GET /api/portfolio` $\to$ **200 OK** (4 holdings retrieved from `data/portfolio.json`)
8. `GET /api/investigations/live` $\to$ **200 OK** (Live telegram feed records)
9. `POST /api/tip/check` $\to$ **200 OK** (Parsed ticker, target, scam markers, and verdict)
10. `POST /api/intelligence/jev/classify` $\to$ **200 OK** (Predicted: `Mixed`, Margin: 0.7624, 6 canonical class scores)
11. `GET /api/intelligence/jev/models` $\to$ **200 OK** (Active model: `mock-qwen2.5-7b-instruct`)

### C. Live Frontend Route Compilation (7 / 7 Passed)
All Next.js Turbopack routes were compiled and verified returning **HTTP 200 OK**:
1. `http://localhost:3000/` (Dashboard & Market Watch) $\to$ **HTTP 200**
2. `http://localhost:3000/investigate` (Scam Tip Investigator) $\to$ **HTTP 200**
3. `http://localhost:3000/stocks` (Universe Directory & Search) $\to$ **HTTP 200**
4. `http://localhost:3000/portfolio` (Holdings & Valuation) $\to$ **HTTP 200**
5. `http://localhost:3000/intelligence` (JEV & NLP Hub) $\to$ **HTTP 200**
6. `http://localhost:3000/campaigns` (Syndicate Coordination Map) $\to$ **HTTP 200**
7. `http://localhost:3000/watcher` (Real-Time Evidence Stream) $\to$ **HTTP 200**

### D. Telegram Public Channel Stream
- Connected via Telethon to MTProto server `91.108.56.189:443`.
- Active read-only session monitoring 7 channels: `@Stock_Burner_Offixal`, `@Growx_intraday_groww`, `@NIFTY50STOCKSSEBI`, `@Mystocksin`, `@MINISH_FAST`, `@mastertrustresearch`, `@markemahakelpredictions`.
- Zero messages sent; strictly passive evidence collection.

---

## 4. Prioritized Bug Log & Applied Repairs

### Bug 1: 6-Class Canonical Schema vs Legacy Assertion Mismatch
- **Severity:** High
- **Affected Files:** [`tests/test_jev_api.py`](file:///D:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/tests/test_jev_api.py), [`src/intelligence/jev/api.py`](file:///D:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/src/intelligence/jev/api.py)
- **Reproduction:** `pytest tests/test_jev_api.py`
- **Observed Behavior:** Failed with `AssertionError: assert 6 == 5` on `len(data["class_scores"])`.
- **Root Cause:** Phase 3 expanded `STANDARD_CLASSES` to include `"Ambiguous"`, bringing the total canonical classes to 6 (`Bullish`, `Bearish`, `Neutral`, `Mixed`, `Ambiguous`, `Insufficient Evidence`). In `api.py`, `_ACTIVE_ADAPTER.preset_logits` lacked letter `"F"`, and the test asserted `== 5`.
- **Fix:** Added `"F": 0.1` to preset logits in `api.py`, updated test to assert all 6 canonical classes are present.
- **Verification:** Test passed cleanly in 0.28s.

### Bug 2: Missing `_ensure_schema` Database Pre-Initialization
- **Severity:** Medium
- **Affected Files:** [`src/market/universe_manager.py`](file:///D:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/src/market/universe_manager.py), [`backend/main.py`](file:///D:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/backend/main.py)
- **Reproduction:** Launching backend server with `uvicorn backend.main:app`.
- **Observed Behavior:** Emitted warning `Could not pre-init database schema: cannot import name '_ensure_schema' from 'src.market.universe_manager'`.
- **Root Cause:** `backend/main.py` lines 75-76 attempted to import `_ensure_schema` from `universe_manager.py`, but the function was never defined.
- **Fix:** Implemented `_ensure_schema()` in `src/market/universe_manager.py` to create `stock_assessments` and required indices (`idx_stock_segment`, `idx_stock_band`, `idx_stock_status`, `idx_stock_score`) idempotently in `data/dakota.db`.
- **Verification:** Backend starts with zero warnings; `test_universe_manager.py` passes 4/4 tests.

### Bug 3: Unscoped Recursive PyTest Collection Collision
- **Severity:** Medium
- **Affected Files:** [`pytest.ini`](file:///D:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/pytest.ini)
- **Reproduction:** Running `pytest` from repository root without arguments.
- **Observed Behavior:** 28 collection errors due to module collisions with `market system dacota/tests/`, scratch scripts, and ad-hoc scripts.
- **Root Cause:** Absence of a root `pytest.ini` caused pytest to recursively crawl all subdirectories, attempting to import non-test scratch files and duplicate legacy test files.
- **Fix:** Created [`pytest.ini`](file:///D:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/pytest.ini) configuring `testpaths = tests` and `norecursedirs = .git .venv node_modules scratch scripts "market system dacota" dacota`.
- **Verification:** Running `pytest` executes all 115 authoritative tests with **100% pass rate** in 173.88s.

---

## 5. Official Application Startup Instructions

To launch the complete Dakota stack in development or evaluation mode:

### Option A: One-Click Windows Batch Launcher
Double-click [`START_DAKOTA.bat`](file:///D:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/START_DAKOTA.bat) in the repository root. It performs pre-flight checks and launches all three services in separate labelled console windows.

To stop all services safely, double-click [`STOP_DAKOTA.bat`](file:///D:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/STOP_DAKOTA.bat).

### Option B: Manual Command Line Startup

1. **Terminal 1 — Backend API Server:**
   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   *Available at:* `http://localhost:8000` (API Docs: `http://localhost:8000/docs`)

2. **Terminal 2 — Frontend Next.js Web UI:**
   ```powershell
   cd frontend
   npm run dev
   ```
   *Available at:* `http://localhost:3000`

3. **Terminal 3 — Telegram Public Channel Ingestion (Optional):**
   ```powershell
   .\.venv\Scripts\python.exe scripts\telegram\channel_reader.py
   ```

4. **Verify Running Services:**
   ```powershell
   .\.venv\Scripts\python.exe scripts\launchers\status_check.py summary
   ```

---

## 6. Safety & Security Invariants Preserved

1. **Feature Flag Isolation:** `DAKOTA_USE_JEV=0` remains the default. The fast rule-based classifier and deterministic mock adapter handle all default traffic without requiring GPU load.
2. **Credential Safety:** No API keys, session tokens, or private data were committed or exposed.
3. **Model Weights Integrity:** Qwen3.5-9B weights in WSL2 remain intact and unmodified; no replacement models were introduced.
4. **Git Branch Protection:** All fixes are staged cleanly on `feature/integrate-official-simple-jev`. No merges into `main` occurred.
