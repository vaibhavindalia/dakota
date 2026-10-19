"""Automatic Market Data Synchronization and Freshness Management for Dakota.

Provides bounded, reliable polling for Indian equities (NSE/BSE) and major market indices:
1. Indian market session awareness (Mon-Fri 09:15-15:30 IST) with dynamic intervals.
2. Bounded polling with configurable rate limits, timeouts, retries, and exponential backoff.
3. Singleton worker lifecycle with concurrency locks to prevent duplicate background workers.
4. Truthful data freshness states: live, delayed, cached, stale, unavailable.
5. In-memory hot cache for real-time indices (NIFTY 50, SENSEX, BANK NIFTY, INDIA VIX).
6. Safe persistence through local parquet caches and SQLite persistence.
7. Inspection telemetry: status, sync count, errors, provider capabilities, and last sync timestamps.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_DIR = BASE_DIR / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = BASE_DIR / "data" / "dakota.db"
PORTFOLIO_FILE = BASE_DIR / "data" / "portfolio.json"


@dataclass
class MarketSyncConfig:
    """Configurable parameters for market data synchronization."""
    enabled: bool = True
    market_hours_interval_sec: float = 30.0
    off_hours_interval_sec: float = 300.0
    stale_threshold_sec: float = 180.0
    rate_limit_pause_sec: float = 1.0
    batch_size: int = 10
    request_timeout_sec: float = 10.0
    max_retries: int = 2
    backoff_factor: float = 1.5

    @classmethod
    def from_env(cls) -> MarketSyncConfig:
        return cls(
            enabled=os.getenv("MARKET_AUTO_SYNC_ENABLED", "1").strip().lower() in ("1", "true", "yes"),
            market_hours_interval_sec=float(os.getenv("MARKET_SYNC_INTERVAL_SECONDS", "30.0")),
            off_hours_interval_sec=float(os.getenv("MARKET_OFF_HOURS_INTERVAL_SECONDS", "300.0")),
            stale_threshold_sec=float(os.getenv("MARKET_STALE_THRESHOLD_SECONDS", "180.0")),
            rate_limit_pause_sec=float(os.getenv("MARKET_RATE_LIMIT_PAUSE_SECONDS", "1.0")),
            batch_size=int(os.getenv("MARKET_SYNC_BATCH_SIZE", "10")),
            request_timeout_sec=float(os.getenv("MARKET_REQUEST_TIMEOUT_SECONDS", "10.0")),
            max_retries=int(os.getenv("MARKET_MAX_RETRIES", "2")),
            backoff_factor=float(os.getenv("MARKET_BACKOFF_FACTOR", "1.5")),
        )


INDEX_REGISTRY: dict[str, dict[str, Any]] = {
    "NIFTY 50": {"symbol": "^NSEI", "exchange": "NSE", "name": "Nifty 50 Index"},
    "SENSEX": {"symbol": "^BSESN", "exchange": "BSE", "name": "BSE Sensex 30"},
    "BANK NIFTY": {"symbol": "^NSEBANK", "exchange": "NSE", "name": "Nifty Bank Index"},
    "INDIA VIX": {"symbol": "^INDIAVIX", "exchange": "NSE", "name": "India Volatility Index"},
}


def _parse_iso_timestamp(ts_val: str | None) -> tuple[datetime | None, bool]:
    """Parse ISO timestamp or date. Returns (datetime_utc, is_date_only)."""
    if not ts_val:
        return None, False
    try:
        clean = str(ts_val).strip().replace("Z", "+00:00")
        if len(clean) == 10 and clean.count("-") == 2:
            dt = datetime.fromisoformat(clean).replace(tzinfo=timezone.utc)
            return dt, True
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc), False
    except Exception:
        return None, False


def compute_freshness_status(
    retrieved_at_iso: str | None,
    market_event_iso: str | None,
    is_market_open: bool,
    stale_threshold_sec: float = 180.0,
    provider_error: str | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> str:
    """Classify market observation freshness truthfully into one of 5 canonical states:
    
    - 'live': Fresh observation (<15m) fetched recently during active open session.
    - 'delayed': Observation is delayed relative to active market session (15m - 60m).
    - 'cached': Valid past session observation stored locally, within normal non-trading window.
    - 'stale': Data exceeds configured freshness threshold, observation is >60m old in open market, or provider is failing.
    - 'unavailable': No data recorded or retrieved.
    """
    if not retrieved_at_iso and not market_event_iso:
        return "unavailable"

    now_utc = now_fn().astimezone(timezone.utc) if now_fn else datetime.now(timezone.utc)

    # 1. Parse retrieval timestamp
    retrieved_dt, _ = _parse_iso_timestamp(retrieved_at_iso)
    if retrieved_dt is None and market_event_iso:
        retrieved_dt, _ = _parse_iso_timestamp(market_event_iso)

    if retrieved_dt is None:
        return "unavailable"

    retrieval_age = max(0.0, (now_utc - retrieved_dt).total_seconds())

    # 2. Parse observation timestamp
    obs_dt, is_date_only = _parse_iso_timestamp(market_event_iso)
    if obs_dt is None:
        obs_dt = retrieved_dt

    obs_age = max(0.0, (now_utc - obs_dt).total_seconds())

    # Provider error always marks feed as stale
    if provider_error:
        return "stale"

    if is_market_open:
        # During live market hours:
        if retrieval_age > stale_threshold_sec:
            return "stale"

        # If observation is date-only (daily bar) or > 16 hours old:
        # It represents yesterday's or an older closing bar retrieved during open trading.
        # It must NOT be labeled as "live"!
        if is_date_only or obs_age > 16 * 3600:
            return "cached"

        if obs_age <= 900.0:  # <= 15 minutes
            return "live"
        elif obs_age <= 3600.0:  # 15m to 60m
            return "delayed"
        else:
            return "stale"
    else:
        # When market is closed (evenings, weekends, holidays):
        # A valid session close observation from the most recent trading days is "cached".
        # If older than 15 calendar days, it becomes "stale".
        if obs_age <= 15 * 86400 and retrieval_age <= 15 * 86400:
            return "cached"
        return "stale"


class MarketSyncWorker:
    """Singleton background worker managing automatic market updates for Dakota."""

    _instance: MarketSyncWorker | None = None
    _instance_lock = threading.Lock()

    def __init__(self, config: MarketSyncConfig | None = None):
        self.config = config or MarketSyncConfig.from_env()
        self._running = False
        self._bg_task: asyncio.Task | None = None
        self._sync_lock = asyncio.Lock()
        
        # Telemetry & State
        self._last_sync_timestamp: str | None = None
        self._last_sync_duration_ms: float = 0.0
        self._sync_count: int = 0
        self._error_count: int = 0
        self._consecutive_errors: int = 0
        self._last_error: str | None = None
        
        # In-memory Hot Cache: {symbol: quote_dict}
        self._indices_cache: dict[str, dict[str, Any]] = {}
        self._active_monitored_tickers: set[str] = set()
        self._cache_lock = threading.Lock()

    @classmethod
    def get_instance(cls, config: MarketSyncConfig | None = None) -> MarketSyncWorker:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(config)
            return cls._instance

    @property
    def is_running(self) -> bool:
        return self._running and self._bg_task is not None and not self._bg_task.done()

    def register_monitored_ticker(self, ticker: str) -> None:
        """Register a ticker as actively inspected by a user or portfolio."""
        clean = ticker.upper().strip()
        if clean:
            with self._cache_lock:
                self._active_monitored_tickers.add(clean)

    def unregister_monitored_ticker(self, ticker: str) -> None:
        clean = ticker.upper().strip()
        with self._cache_lock:
            self._active_monitored_tickers.discard(clean)

    def get_monitored_tickers(self) -> list[str]:
        with self._cache_lock:
            return sorted(list(self._active_monitored_tickers))

    async def start(self) -> None:
        """Start the background synchronization worker safely (idempotent)."""
        if not self.config.enabled:
            logger.info("MarketSyncWorker is disabled by configuration (MARKET_AUTO_SYNC_ENABLED=0).")
            return

        if self.is_running:
            logger.info("MarketSyncWorker is already running (duplicate start avoided).")
            return

        self._running = True
        self._bg_task = asyncio.create_task(self._worker_loop(), name="DakotaMarketSyncWorker")
        logger.info("MarketSyncWorker started successfully.")

    async def stop(self) -> None:
        """Stop the background synchronization worker gracefully."""
        self._running = False
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
            logger.info("MarketSyncWorker stopped cleanly.")

    async def _worker_loop(self) -> None:
        """Main bounded polling loop with market-hours awareness and exponential backoff."""
        logger.info("MarketSyncWorker background loop active.")
        # Execute an initial synchronization immediately after startup
        try:
            await self.sync_once()
        except Exception as exc:
            logger.warning("Initial market sync encountered an issue: %s", exc)

        while self._running:
            try:
                from src.ingest.market_data import is_indian_market_open
                is_open, _, _ = is_indian_market_open()

                # Dynamic sleep interval based on market session and consecutive error backoff
                base_interval = (
                    self.config.market_hours_interval_sec
                    if is_open
                    else self.config.off_hours_interval_sec
                )
                
                # Exponential backoff if provider consecutive errors > 0
                if self._consecutive_errors > 0:
                    multiplier = min(self.config.backoff_factor ** self._consecutive_errors, 8.0)
                    sleep_interval = base_interval * multiplier
                else:
                    sleep_interval = base_interval

                await asyncio.sleep(sleep_interval)
                if not self._running:
                    break

                await self.sync_once()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("MarketSyncWorker loop exception: %s", exc, exc_info=True)
                self._error_count += 1
                self._consecutive_errors += 1
                self._last_error = str(exc)
                await asyncio.sleep(5.0)

    async def sync_once(self, force: bool = False) -> dict[str, Any]:
        """Perform a single synchronization cycle for indices and active equities."""
        if self._sync_lock.locked():
            logger.debug("Market sync already in progress; skipping overlapping run.")
            return {"status": "skipped", "reason": "sync_in_progress"}

        async with self._sync_lock:
            start_time = time.perf_counter()
            from src.ingest.market_data import is_indian_market_open
            is_open, session_status, market_time = is_indian_market_open()

            sync_results: dict[str, Any] = {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "is_market_open": is_open,
                "session_status": session_status,
                "indices_synced": 0,
                "stocks_synced": 0,
                "errors": [],
            }

            # 1. Sync Major Indian Indices
            try:
                await self._sync_indices(is_open)
                sync_results["indices_synced"] = len(self._indices_cache)
            except Exception as exc:
                logger.warning("Error syncing indices: %s", exc)
                sync_results["errors"].append(f"Indices: {exc}")

            # 2. Collect Priority Equities to Sync (Monitored + Portfolio + Top Universe)
            tickers_to_sync = await asyncio.to_thread(self._collect_priority_tickers)
            
            # 3. Synchronize Equities (with bounded rate limit pause)
            synced_count = 0
            for ticker in tickers_to_sync[: self.config.batch_size]:
                try:
                    await asyncio.to_thread(self._sync_single_stock, ticker, is_open)
                    synced_count += 1
                    # Polite rate-limiting pause between yfinance symbol requests
                    if self.config.rate_limit_pause_sec > 0:
                        await asyncio.sleep(self.config.rate_limit_pause_sec)
                except Exception as exc:
                    logger.debug("Error syncing stock %s: %s", ticker, exc)
                    sync_results["errors"].append(f"Stock {ticker}: {exc}")

            sync_results["stocks_synced"] = synced_count

            # Record Telemetry
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            now_iso = datetime.now(timezone.utc).isoformat()
            
            self._last_sync_timestamp = now_iso
            self._last_sync_duration_ms = duration_ms
            self._sync_count += 1

            if sync_results["errors"]:
                self._error_count += len(sync_results["errors"])
                self._consecutive_errors += 1
                self._last_error = "; ".join(sync_results["errors"][:3])
            else:
                self._consecutive_errors = 0
                self._last_error = None

            sync_results["completed_at"] = now_iso
            sync_results["duration_ms"] = duration_ms
            return sync_results

    async def _sync_indices(self, is_open: bool) -> None:
        """Fetch real quote data for Indian indices with error fallback to cache."""
        for name, spec in INDEX_REGISTRY.items():
            sym = spec["symbol"]
            try:
                quote = await asyncio.to_thread(
                    self._fetch_index_quote,
                    name=name,
                    symbol=sym,
                    exchange=spec["exchange"],
                    is_open=is_open,
                )
                with self._cache_lock:
                    self._indices_cache[name] = quote
            except Exception as exc:
                logger.debug("Index fetch error for %s (%s): %s", name, sym, exc)
                with self._cache_lock:
                    if name in self._indices_cache:
                        # Mark existing cache as stale with error
                        self._indices_cache[name]["data_status"] = "stale"
                        self._indices_cache[name]["last_error"] = str(exc)

    def _fetch_index_quote(
        self,
        name: str,
        symbol: str,
        exchange: str,
        is_open: bool,
    ) -> dict[str, Any]:
        """Fetch index quote via yfinance with timeout safety."""
        import yfinance as yf

        t = yf.Ticker(symbol)
        hist = t.history(period="5d", interval="5m")
        now_iso = datetime.now(timezone.utc).isoformat()

        if hist.empty:
            # Fall back to 1d daily series if intraday is empty
            hist = t.history(period="1mo", interval="1d")

        if hist.empty:
            raise RuntimeError(f"No market data returned for index {symbol}")

        hist = hist.dropna(subset=["Close"])
        latest_row = hist.iloc[-1]
        prev_close = None
        
        try:
            prev_close = float(getattr(t.fast_info, "previous_close", 0) or 0)
        except Exception:
            pass

        if not prev_close or prev_close <= 0:
            if len(hist) >= 2:
                prev_close = float(hist["Close"].iloc[-2])
            else:
                prev_close = float(latest_row["Open"])

        last_price = round(float(latest_row["Close"]), 2)
        change = round(last_price - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2) if prev_close > 0 else 0.0

        candle_dt = hist.index[-1]
        candle_iso = candle_dt.isoformat() if hasattr(candle_dt, "isoformat") else str(candle_dt)

        freshness = compute_freshness_status(
            retrieved_at_iso=now_iso,
            market_event_iso=candle_iso,
            is_market_open=is_open,
            stale_threshold_sec=self.config.stale_threshold_sec,
        )

        return {
            "name": name,
            "symbol": symbol,
            "exchange": exchange,
            "provider": "yfinance",
            "last_price": last_price,
            "previous_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "market_event_timestamp": candle_iso,
            "retrieved_at": now_iso,
            "data_status": freshness,
            "is_market_open": is_open,
            "currency": "INR",
        }

    def _collect_priority_tickers(self) -> list[str]:
        """Collect list of priority tickers to sync: active monitored + portfolio + universe cases."""
        priority_set: set[str] = set()

        # 1. Monitored in UI
        with self._cache_lock:
            priority_set.update(self._active_monitored_tickers)

        # 2. Portfolio holdings
        if PORTFOLIO_FILE.exists():
            try:
                p_data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
                holdings = p_data if isinstance(p_data, list) else p_data.get("holdings", [])
                for h in holdings:
                    tk = str(h.get("ticker", "")).upper().strip()
                    if tk:
                        priority_set.add(tk)
            except Exception:
                pass

        # 3. Known active demo cases if queue is small
        if len(priority_set) < 5:
            priority_set.update(["VARANIUM", "ZOMATO", "WIPRO", "TCS", "RELIANCE", "INFY"])

        return sorted(list(priority_set))

    def _sync_single_stock(self, ticker: str, is_open: bool) -> None:
        """Sync OHLCV and technical state for a single equity into parquet and database."""
        clean_ticker = ticker.upper().strip()
        from src.ingest.market_data import load_ohlcv, _cache_path, _meta_path
        from src.market.universe_manager import _get_connection

        now_iso = datetime.now(timezone.utc).isoformat()

        # Fetch/refresh daily and intraday series
        df = load_ohlcv(clean_ticker, force_refresh=True, allow_synthetic=False)
        if df is None or df.empty:
            return

        last_row = df.iloc[-1]
        candle_dt = last_row.get("date")
        candle_iso = candle_dt.isoformat() if hasattr(candle_dt, "isoformat") else str(candle_dt)

        freshness = compute_freshness_status(
            retrieved_at_iso=now_iso,
            market_event_iso=candle_iso,
            is_market_open=is_open,
            stale_threshold_sec=self.config.stale_threshold_sec,
        )

        close_series = df["close"].dropna()
        last_price = round(float(close_series.iloc[-1]), 2)
        prev_price = round(float(close_series.iloc[-2]), 2) if len(close_series) >= 2 else last_price
        change_pct = round(((last_price - prev_price) / prev_price) * 100, 2) if prev_price > 0 else 0.0

        high_52w = round(float(df["high"].tail(252).max()), 2) if "high" in df else None
        low_52w = round(float(df["low"].tail(252).min()), 2) if "low" in df else None
        volume = int(last_row.get("volume", 0))

        # Update metadata JSON
        meta_file = _meta_path(clean_ticker)
        meta_payload = {
            "ticker": clean_ticker,
            "exchange": "NSE",
            "provider": "yfinance",
            "retrieved_at": now_iso,
            "market_event_timestamp": candle_iso,
            "status": freshness,
            "latest_price": last_price,
            "change_pct": change_pct,
            "last_successful_sync": now_iso,
            "last_error": None,
        }
        meta_file.write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")

        # Update SQLite stock_assessments record
        try:
            conn = _get_connection()
            cur = conn.cursor()
            cur.execute("""
            UPDATE stock_assessments SET
                latest_price = ?,
                change_pct = ?,
                high_52w = ?,
                low_52w = ?,
                volume = ?,
                data_freshness = ?,
                market_data_as_of = ?,
                updated_at = ?
            WHERE ticker = ?
            """, (last_price, change_pct, high_52w, low_52w, volume, freshness, candle_iso, now_iso, clean_ticker))
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.debug("Database update error for %s: %s", clean_ticker, exc)

        # Trigger alert evaluation for this stock
        try:
            from src.alerts.engine import alert_engine
            data_dict = {
                "ticker": clean_ticker,
                "latest_price": last_price,
                "change_pct": change_pct,
                "high_52w": high_52w,
                "low_52w": low_52w,
                "volume": volume,
                "delivery_pct": float(last_row.get("delivery_pct", 0.0)) if "delivery_pct" in last_row else None,
                "data_freshness": freshness,
                "observation_timestamp": candle_iso,
                "market_event_timestamp": candle_iso,
                "retrieved_at": now_iso,
                "feed_type": "intraday_snapshot_5m",
            }
            rules = alert_engine.store.get_rules(enabled_only=True)
            for r in rules:
                alert_engine.evaluate_rule(r, clean_ticker, data_dict)
        except Exception as alt_exc:
            logger.debug("Alert evaluation error for %s: %s", clean_ticker, alt_exc)

    def get_indices(self) -> dict[str, dict[str, Any]]:
        """Return cached index quotes with freshness metadata."""
        with self._cache_lock:
            # If cache is empty, return default placeholder structures with status 'unavailable'
            if not self._indices_cache:
                return {
                    name: {
                        "name": name,
                        "symbol": spec["symbol"],
                        "exchange": spec["exchange"],
                        "provider": "yfinance",
                        "last_price": None,
                        "change": 0.0,
                        "change_pct": 0.0,
                        "data_status": "unavailable",
                        "retrieved_at": None,
                    }
                    for name, spec in INDEX_REGISTRY.items()
                }
            return {k: dict(v) for k, v in self._indices_cache.items()}

    def get_status(self) -> dict[str, Any]:
        """Return operational telemetry for Dakota health/connectors endpoints."""
        from src.ingest.market_data import is_indian_market_open
        is_open, session_status, market_time = is_indian_market_open()

        with self._cache_lock:
            indices_count = len(self._indices_cache)
            monitored = sorted(list(self._active_monitored_tickers))

        return {
            "status": "healthy" if self.is_running else ("disabled" if not self.config.enabled else "stopped"),
            "worker_running": self.is_running,
            "enabled": self.config.enabled,
            "is_market_open": is_open,
            "session_status": session_status,
            "market_time_ist": market_time,
            "last_sync_timestamp": self._last_sync_timestamp,
            "last_sync_duration_ms": self._last_sync_duration_ms,
            "sync_count": self._sync_count,
            "error_count": self._error_count,
            "consecutive_errors": self._consecutive_errors,
            "last_error": self._last_error,
            "intervals": {
                "market_hours_sec": self.config.market_hours_interval_sec,
                "off_hours_sec": self.config.off_hours_interval_sec,
                "stale_threshold_sec": self.config.stale_threshold_sec,
                "rate_limit_pause_sec": self.config.rate_limit_pause_sec,
            },
            "providers": [
                {
                    "provider": "yfinance",
                    "exchange_support": ["NSE", "BSE"],
                    "data_types": ["intraday_ohlcv", "daily_ohlcv", "indices", "fast_info"],
                    "transport": "bounded_polling",
                    "rate_limited": True,
                    "configured": True,
                },
                {
                    "provider": "nse_bse_bhavcopy",
                    "exchange_support": ["NSE", "BSE"],
                    "data_types": ["equity_bhavcopy", "delivery_position", "indices_bhavcopy", "priceband"],
                    "transport": "daily_session_sync",
                    "configured": True,
                },
            ],
            "monitored_tickers": monitored,
            "indices_tracked": indices_count,
            "alerts": self._get_alerts_telemetry(),
        }

    def _get_alerts_telemetry(self) -> dict[str, Any]:
        try:
            from src.alerts.engine import alert_engine
            return alert_engine.get_status()
        except Exception:
            return {"status": "uninitialized"}


# Global Worker Instance
market_sync_worker = MarketSyncWorker.get_instance()
