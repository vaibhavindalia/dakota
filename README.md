# Dakota — Real-data Tip Investigation Engine v3

Dakota is now structured around the actual product idea:

**Tip → investigate the stock across connected sources → aggregate evidence → explainable risk score**

## Connected investigation layers

1. Tip parser + privacy scrub.
2. Cached/refreshable NSE and BSE market data.
3. RSI, EMA/SMA, MACD, Bollinger Bands, volume anomaly, delivery context.
4. NIFTY 50 relative-performance context when local index history exists.
5. News via GDELT.
6. Reddit via official OAuth when credentials exist, with RSS fallback.
7. X recent-search via X API when `X_BEARER_TOKEN` exists.
8. Instagram public hashtag media via Meta Graph API when credentials exist.
9. NSE/BSE corporate evidence using the installed exchange clients where supported.
10. Telegram Bot API webhook ingestion for authorized messages/channels.
11. WhatsApp Cloud API webhook ingestion for the connected business account.
12. Privacy-preserving tip fingerprint storage for repeated-tip/coordination signals.

## Important boundary

A missing connector is **not** interpreted as clean evidence. Dakota reports risk indicators from available evidence and never labels a stock "fraud". It does not give buy/sell advice.

Telegram/WhatsApp ingestion is limited to messages delivered to an authorized bot/business integration. Dakota does not bypass private groups, access controls, or content protection.

## Setup

From the Dakota project root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill the credentials that are available. Do not paste credentials into chat or commit `.env` to git.

## Refresh real NSE/BSE data

After market close, run:

```powershell
.\.venv\Scripts\python.exe -m scripts.sync_market
```

Or a specific trading date:

```powershell
.\.venv\Scripts\python.exe -m scripts.sync_market --date 2026-10-06
```

The application reads the downloaded reports from `data/raw/` rather than downloading on every investigation request.

## Backend

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

Useful endpoints:

```text
GET  /health
GET  /api/connectors/status
POST /api/market/sync
POST /api/investigate
POST /api/connectors/telegram/webhook
GET  /api/connectors/whatsapp/webhook
POST /api/connectors/whatsapp/webhook
```

## Frontend

```powershell
cd frontend
npm run dev
```

Open:

`http://localhost:3000/investigate`

## Telegram

Create the bot through BotFather, place the token in `.env`, expose the FastAPI webhook over HTTPS, then call:

```text
POST /api/connectors/telegram/set-webhook?webhook_url=https://YOUR_PUBLIC_HOST/api/connectors/telegram/webhook
```

The bot can investigate messages it legitimately receives. Telegram documents long polling and webhooks as the two Bot API update mechanisms; bots receive channel posts only where they are members and group visibility depends on privacy/admin settings.

## WhatsApp

Configure the Meta/WhatsApp Cloud API webhook against:

```text
GET/POST https://YOUR_PUBLIC_HOST/api/connectors/whatsapp/webhook
```

Set `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, and the current Meta Graph API version.

## X

Set `X_BEARER_TOKEN`. The connector uses recent search and post fields needed for explainable evidence. X's recent-search surface is limited to the recent window exposed by the API.

## Reddit

For production-grade access, set Reddit OAuth client credentials. Without them Dakota falls back to its public RSS prototype collector.

## Score

The current investigator score is an **available-evidence prototype score**. It is intentionally separate from the older backtested five-signal engine until enough real evidence is collected to recalibrate the weights against point-in-time cases.

The next research step is to calibrate this score on real historical investigations rather than inventing weights from a few live examples.


## Live universal investigation pipeline

The current integration is:

```text
Telegram public-channel post
  -> privacy-safe intake
  -> local classifier
  -> impact/entity mapper
  -> universal investigation
  -> news + Reddit/social evidence
  -> explainable 0-100 evidence aggregation
  -> live JSONL store
  -> FastAPI
  -> /investigate dashboard
```

Run the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

Run the Telegram reader in a second terminal:

```powershell
.\.venv\Scripts\python.exe scripts\telegram\channel_reader.py
```

The Next.js frontend reads the live feed from:

```text
GET /api/investigations/live
```

The original Telegram message is not stored by the live store. Only derived investigation data is persisted.
