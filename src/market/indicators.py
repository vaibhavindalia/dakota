"""Explainable technical indicators for Dakota market investigations.

The module calculates indicators locally from OHLCV data. No external technical-
indicator API is required.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _number(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of OHLCV history with common indicators added."""
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    out = df.copy().sort_values("date").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume", "delivery_pct"]:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    close = out["close"]
    volume = out["volume"]

    out["sma_20"] = close.rolling(20, min_periods=1).mean()
    out["sma_50"] = close.rolling(50, min_periods=1).mean()
    out["ema_20"] = close.ewm(span=20, adjust=False, min_periods=1).mean()
    out["ema_50"] = close.ewm(span=50, adjust=False, min_periods=1).mean()

    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = losses.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    out["rsi_14"] = 100 - (100 / (1 + rs))
    out.loc[(avg_loss == 0) & (avg_gain > 0), "rsi_14"] = 100.0

    ema12 = close.ewm(span=12, adjust=False, min_periods=1).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=1).mean()
    out["macd"] = ema12 - ema26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False, min_periods=1).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]

    mid = close.rolling(20, min_periods=1).mean()
    std = close.rolling(20, min_periods=1).std(ddof=0)
    out["bb_mid"] = mid
    out["bb_upper"] = mid + 2 * std
    out["bb_lower"] = mid - 2 * std
    denom = (out["bb_upper"] - out["bb_lower"]).replace(0, pd.NA)
    out["bb_pct"] = (close - out["bb_lower"]) / denom

    out["return_1d_pct"] = close.pct_change() * 100
    out["return_5d_pct"] = close.pct_change(5) * 100
    out["return_20d_pct"] = close.pct_change(20) * 100
    out["volume_sma_20"] = volume.rolling(20, min_periods=1).mean()
    out["volume_ratio_20"] = volume / out["volume_sma_20"].replace(0, pd.NA)

    if "delivery_pct" in out:
        out["delivery_sma_20"] = out["delivery_pct"].rolling(20, min_periods=1).mean()
        out["delivery_delta_20"] = out["delivery_pct"] - out["delivery_sma_20"]

    return out


def latest_indicator_snapshot(df: pd.DataFrame) -> dict[str, Any]:
    """Return a JSON-friendly current indicator snapshot."""
    if df.empty:
        return {}
    row = df.iloc[-1]

    def pct_change_status(value: float | None) -> str:
        if value is None:
            return "unavailable"
        if value > 0:
            return "positive"
        if value < 0:
            return "negative"
        return "flat"

    rsi = _number(row.get("rsi_14"))
    if rsi is None:
        rsi_status = "unavailable"
    elif rsi >= 70:
        rsi_status = "overbought"
    elif rsi <= 30:
        rsi_status = "oversold"
    else:
        rsi_status = "neutral"

    volume_ratio = _number(row.get("volume_ratio_20"))
    if volume_ratio is None:
        volume_status = "unavailable"
    elif volume_ratio >= 3:
        volume_status = "extreme_spike"
    elif volume_ratio >= 2:
        volume_status = "high"
    elif volume_ratio >= 1.25:
        volume_status = "above_average"
    else:
        volume_status = "normal"

    delivery_delta = _number(row.get("delivery_delta_20"))
    delivery_status = "unavailable"
    if delivery_delta is not None:
        if delivery_delta >= 10:
            delivery_status = "well_above_average"
        elif delivery_delta <= -10:
            delivery_status = "well_below_average"
        else:
            delivery_status = "near_average"

    return {
        "close": _number(row.get("close")),
        "open": _number(row.get("open")),
        "high": _number(row.get("high")),
        "low": _number(row.get("low")),
        "previous_close": _number(row.get("previous_close")),
        "volume": _number(row.get("volume")),
        "delivery_pct": _number(row.get("delivery_pct")),
        "sma_20": _number(row.get("sma_20")),
        "sma_50": _number(row.get("sma_50")),
        "ema_20": _number(row.get("ema_20")),
        "ema_50": _number(row.get("ema_50")),
        "rsi_14": rsi,
        "rsi_status": rsi_status,
        "macd": _number(row.get("macd")),
        "macd_signal": _number(row.get("macd_signal")),
        "macd_hist": _number(row.get("macd_hist")),
        "bb_upper": _number(row.get("bb_upper")),
        "bb_mid": _number(row.get("bb_mid")),
        "bb_lower": _number(row.get("bb_lower")),
        "bb_pct": _number(row.get("bb_pct")),
        "return_1d_pct": _number(row.get("return_1d_pct")),
        "return_5d_pct": _number(row.get("return_5d_pct")),
        "return_20d_pct": _number(row.get("return_20d_pct")),
        "volume_ratio_20": volume_ratio,
        "volume_status": volume_status,
        "delivery_delta_20": delivery_delta,
        "delivery_status": delivery_status,
        "trend_vs_ema20": pct_change_status(
            None
            if _number(row.get("close")) is None or _number(row.get("ema_20")) is None
            else _number(row.get("close")) - _number(row.get("ema_20"))
        ),
    }


def market_signal_reasons(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn indicator values into explainable market observations.

    These are observations, not accusations or trading instructions.
    """
    reasons: list[dict[str, Any]] = []
    vr = snapshot.get("volume_ratio_20")
    if vr is not None and vr >= 2:
        reasons.append({
            "signal": "volume_anomaly",
            "severity": "high" if vr >= 3 else "medium",
            "text": f"Volume is about {vr:.1f}× the 20-session average.",
        })

    rsi = snapshot.get("rsi_14")
    if rsi is not None and rsi >= 70:
        reasons.append({"signal": "rsi_high", "severity": "medium", "text": f"RSI(14) is {rsi:.1f}, in an overbought range."})
    elif rsi is not None and rsi <= 30:
        reasons.append({"signal": "rsi_low", "severity": "medium", "text": f"RSI(14) is {rsi:.1f}, in an oversold range."})

    ret5 = snapshot.get("return_5d_pct")
    if ret5 is not None and abs(ret5) >= 15:
        reasons.append({"signal": "short_term_move", "severity": "medium", "text": f"The 5-session move is {ret5:+.1f}%."})

    delivery_delta = snapshot.get("delivery_delta_20")
    if delivery_delta is not None and delivery_delta >= 10:
        reasons.append({"signal": "delivery_shift", "severity": "medium", "text": f"Delivery percentage is {delivery_delta:+.1f} points above its 20-session average."})

    close = snapshot.get("close")
    ema20 = snapshot.get("ema_20")
    sma50 = snapshot.get("sma_50")
    if close is not None and ema20 is not None and sma50 is not None and close > ema20 > sma50:
        reasons.append({"signal": "trend_alignment", "severity": "low", "text": "Price is above both the 20-EMA and 50-SMA."})
    elif close is not None and ema20 is not None and sma50 is not None and close < ema20 < sma50:
        reasons.append({"signal": "trend_alignment", "severity": "low", "text": "Price is below both the 20-EMA and 50-SMA."})

    return reasons
