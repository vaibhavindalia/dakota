# DAKOTA — PRODUCT ACCEPTANCE TEST REPORT (PAT-1)

**Execution Date:** 2026-10-19  
**Branch:** `feature/integrate-official-simple-jev`  
**Repository:** `D:\dakota V4 with telegram integrated\dakota integ. d11 final prototype1 minus telegram feature\dakota`  
**Execution Environment:** Windows 11 (Host) / WSL2 Ubuntu 22.04 | NVIDIA RTX 4060 Laptop GPU (8GB VRAM) | Python 3.14 (.venv) | Node.js v24.21.0 | Next.js 16.4.0 (Turbopack) | FastAPI 0.4.0  
**Feature Flag Configuration:** `DAKOTA_USE_JEV=0` (Safe default deterministic zero-weight mock; official JEV adapter loaded conditionally on-demand)

---

## 1. Executive Summary

The Product Acceptance Test (PAT-1) evaluated Dakota as an integrated financial intelligence and scam investigation system across eight core user-facing and backend workflows. All eight end-to-end workflows passed empirical verification without blocking issues. 

One functional batch parsing defect in the launcher scripts was identified during cold startup, immediately diagnosed, repaired with regression tests, and verified. The full automated regression suite now stands at **121 passed tests (100% pass rate)** with zero failures.

---

## 2. Integrated Product Acceptance Results Matrix

| # | Workflow | Test Method & Exact Steps / Commands | Expected Behavior | Actual Observed Behavior | Status | Relevant Logs & References | Defects & Severity | Service Type |
|---|---|---|---|---|---|---|---|---|
| **1** | **Startup / Shutdown** | 1. Executed `START_DAKOTA.bat`<br>2. Ran `scripts/launchers/status_check.py summary`<br>3. Verified HTTP 200 on `http://127.0.0.1:8000/health` & `http://127.0.0.1:3000/`<br>4. Executed `scripts/launchers/stop_services.py`<br>5. Verified zero orphaned processes. | All three subsystems (FastAPI on port 8000, Next.js on port 3000, and Telethon channel reader) launch, report healthy status, and terminate cleanly on shutdown. | Backend, Frontend, and Telethon initialized and responded HTTP 200. Clean shutdown successfully terminated PIDs 27224, 8536, and 16772 without collateral process impact. | **PASS** | `status_check.py`: `Backend (8000): ONLINE`, `Frontend (3000): ONLINE`, `Telegram Stream: ACTIVE` | **High (Repaired):** Multi-byte Unicode banner in `START_DAKOTA.bat` & `STOP_DAKOTA.bat` caused OEM code page pipe delimiter parsing errors (`'██║' is not recognized`) setting `errorlevel=1`. Fixed via `chcp 65001` and clean ASCII banner; extended initialization wait loop to 30s. | Real Services |
| **2** | **Portfolio** | 1. Search: `GET /api/stocks?search=TCS&limit=5`<br>2. Detail: `GET /api/stocks/TCS`<br>3. Add Holding: `POST /api/portfolio/holdings` (`{"ticker": "INFY", "quantity": 100, "average_buy_price": 1450.0}`)<br>4. Check: `GET /api/portfolio`<br>5. Edit: `POST /api/portfolio/holdings` (`quantity=150, price=1420.0`)<br>6. Delete: `DELETE /api/portfolio/holdings/INFY`<br>7. Verify removal. | Company is searchable in 2,615 stock database; detail returns company metadata, risk profile, and decision guidance; holding persists in `data/portfolio.json`, updates valuation, and cleanly deletes. | Stock found (2 items); TCS metadata retrieved (`name: Tata Consultancy Services Limited`, NSE, `score: 0.0`, Low band); initial holding persisted (Qty: 100.0, Buy Price: ₹1,450.0); edit updated (Qty: 150.0, Buy Price: ₹1,420.0); delete removed record completely (`infy is None: True`). | **PASS** | `test_pat1_portfolio_workflow` in `tests/test_product_acceptance_e2e.py` | None | Real Services & SQLite (`data/dakota.db` + `data/portfolio.json`) |
| **3** | **Intelligence** | 1. `POST /api/intelligence/jev/classify` with deal claim context<br>2. `POST /api/intelligence/jev/analyze`<br>3. Schema validation: `POST /api/intelligence/jev/classify` with `sample: "not-a-dict"`. | Logit-derived sentiment classification across 6 canonical classes; citation-grounded analysis report with evidence IDs (`[E1]`, source, timestamp); HTTP 422 on invalid schema. | `predicted_label: Mixed`, confidence: 0.8306, 6-class normalized probability vector (`Bullish`, `Bearish`, `Neutral`, `Mixed`, `Ambiguous`, `Insufficient Evidence`). Analyze returned structured citations (`[E1]`, `[E2]`, `[E3]`). Malformed input rejected with HTTP 422 Unprocessable Entity. | **PASS** | `tests/test_jev_api.py`, `scripts/test_product_acceptance.py` [3/8] (16.4 ms) | None | Deterministic Safe Mock (`DAKOTA_USE_JEV=0`) |
| **4** | **Risk / Forensics** | 1. `GET /api/stocks/CLOUD/risk`<br>2. `POST /api/tip/check` with multi-marker scam text (`BUY URGENT! CDSL target 2500... 100% GUARANTEED RETURN! Join VIP channel`). | Forensic risk engine flags known high-risk equity (CLOUD) with high score and detailed forensic reasons; scam tip triggers scam language detection, quotes price target, and elevates risk band. | CLOUD scored 78.0/100 (`High` band, 12 forensic reasons including promoter exit, SEBI enforcement order, unbilled revenue, thin float). Scam tip scored 75.0/100 (`High` band, 5 scam markers extracted: guaranteed returns, VIP funnel, urgency). | **PASS** | `scripts/test_product_acceptance.py` [4/8] (132.5 ms) | None | Real Engine + Indian Market Fixtures |
| **5** | **Telegram** | 1. Controlled tip fixture passed to `intake_tip(..., source="telegram")`<br>2. PII scrub check on phone numbers and t.me invite links<br>3. Deterministic SHA-256 fingerprint deduplication check<br>4. Telethon process monitoring. | Ingestion scrubs PII without leaking phone numbers/handles, extracts price target & primary ticker, generates consistent fingerprint, and prevents duplicate processing. No outbound messages sent. | PII scrubbed (`+919876543210` -> `[phone]`, `t.me/...` -> `[link]`). Investigation ID generated, price target extracted (`₹1,200`), identical fingerprint computed on duplicate input (`fp1 == fp2: True`). Telethon MTProto reader confirmed running (PID 16772) in read-only mode. | **PASS** | `scripts/test_product_acceptance.py` [5/8] (649.4 ms) | None | Controlled Fixture + Telethon MTProto Process |
| **6** | **Missing or Conflicting Evidence** | 1. Conflicting: Bullish promotional claim with collapsing delivery volume & GSM surveillance<br>2. Stale: Query stock with cached data timestamp<br>3. Insufficient: Ticker with zero filings, no telemetry. | System cleanly differentiates conflicting evidence from one-sided sentiment; stale telemetry surfaces explicit staleness flags; empty context evaluates to `Insufficient Evidence`. | Conflicting evidence classified as `Mixed` / `Bearish` with divergent citations. ZOMATO risk returned `data_freshness: "cached"` / `"stale"`. Empty sample scored `Insufficient Evidence` in class probability distribution. | **PASS** | `scripts/test_product_acceptance.py` [6/8] (70.3 ms) | None | Deterministic Engine & Grounded Evaluator |
| **7** | **External Connectors** | 1. `GET /api/connectors/status`<br>2. Verified reporting of unconfigured channels (Instagram, WhatsApp, Telegram webhook) vs local/public sources (NSE, BSE, Reddit, News). | Unconfigured third-party credentials must be reported transparently as coverage gaps (`missing_credentials`), falling back to local/public feeds without throwing 500 errors or interrupting the terminal. | `status: "ok"`. Connectors status surfaced `instagram: "missing_credentials"`, `whatsapp: "missing_credentials"`, `telegram: "missing_credentials"`, `reddit: "rss_fallback"`, `news: "gdelt_public"`, `nse: "local_package_or_cached"`. Terminal functionality completely uninterrupted. | **PASS** | `scripts/test_product_acceptance.py` [7/8] (23.9 ms) | None | Real Connector Status Endpoint |
| **8** | **Regression Suite** | Ran full configured test suite via `.venv\Scripts\python.exe -m pytest tests/` | All unit, integration, valuation, risk, and JEV tests pass with 0 failures. | **121 passed, 0 failures, 2 warnings in 172.10s (100% pass rate)** across 19 test modules. | **PASS** | `tests/` directory (121 tests passed) | None | Pytest Automated Test Suite |

---

## 3. Frontend Web Interface Verification

All primary Next.js (Turbopack) web interface routes were exercised on port 3000 to verify end-to-end user navigation:

| Route | Page Purpose | HTTP Status | Response Payload |
|---|---|---|---|
| `http://localhost:3000/` | Terminal Home Dashboard & Live Feed | **200 OK** | 34,938 bytes |
| `http://localhost:3000/stocks` | Equities Universe Browser & Screener | **200 OK** | 31,491 bytes |
| `http://localhost:3000/stocks/TCS` | Stock Detail, 3-Pillar Decision & Forensics | **200 OK** | 31,103 bytes |
| `http://localhost:3000/portfolio` | Portfolio Holdings, Valuation & Risk Breakdown | **200 OK** | 32,478 bytes |
| `http://localhost:3000/intelligence` | JEV Intelligence Terminal & Model Telemetry | **200 OK** | 37,347 bytes |
| `http://localhost:3000/investigate` | Tip Authentication & Deep-Dive Forensic Input | **200 OK** | 32,017 bytes |
| `http://localhost:3000/campaigns` | Coordinated Scam Campaigns & Tip Clustering | **200 OK** | 27,072 bytes |
| `http://localhost:3000/watcher` | Real-time Telegram Channel Monitoring Feed | **200 OK** | 28,384 bytes |

---

## 4. Defects Identified & Repaired

### Defect 1: Windows Batch OEM Code Page Syntax Error in System Launchers
- **Severity:** High
- **Component:** `START_DAKOTA.bat` & `STOP_DAKOTA.bat`
- **Symptom:** When running `START_DAKOTA.bat` in standard Windows cmd shells, the UTF-8 box-drawing characters in the ASCII banner (`██║`, `╝`) were parsed as command pipe delimiters (`|`) under Windows OEM code pages (CP437/CP1252), raising `'██║' is not recognized as an internal or external command` and erroneously setting `errorlevel=1`. This caused the pre-flight check to falsely report that `node.exe` was missing. Furthermore, the backend startup wait loop was capped at 8 seconds, which was insufficient for cold-start model weight loading.
- **Root Cause:** Missing `chcp 65001` codepage initialization and unescaped multi-byte banner art in batch scripts.
- **Fix:**
  1. Inserted `chcp 65001 >nul 2>&1` in both `START_DAKOTA.bat` and `STOP_DAKOTA.bat`.
  2. Replaced multi-byte box-drawing characters with clean, standard ASCII banners.
  3. Increased the backend initialization verification loop in `START_DAKOTA.bat` from 8 iterations (8s) to 15 iterations (30s) to comfortably accommodate the 21-second cold-start FinBERT weights loading.
- **Regression Verification:** Added automated launcher status verification in `scripts/test_product_acceptance.py` and confirmed `status_check.py summary` outputs all 3 subsystems as `ONLINE` and `ACTIVE`.

---

## 5. Summary of Verification Metrics

- **Workflows Tested:** 8 / 8 (100%)
- **Workflows Passed:** 8 / 8 (100%)
- **Workflows Blocked:** 0
- **Total Pytest Tests:** 121 (115 baseline + 6 new PAT-1 E2E integration tests)
- **Pytest Pass Rate:** 100% (121 passed, 0 failed)
- **Active Safety Flag:** `DAKOTA_USE_JEV=0` strictly maintained as the default.
- **Outbound Message Safety:** 0 unsolicited external Telegram or WhatsApp messages sent.
