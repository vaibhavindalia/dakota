"""TradingView-style Technical Indicator & Consensus Analyzer for Dakota.

Computes multi-indicator technical signals (Moving Averages + Oscillators),
produces consensus ratings (Strong Buy / Buy / Neutral / Sell / Strong Sell),
and performs Scam Tip vs Technical Divergence checks.
"""
from __future__ import annotations

import math
from typing import Any
import pandas as pd


def _num(val: Any) -> float | None:
    try:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def compute_supertrend(df: pd.DataFrame, length: int = 10, mult: float = 3.0) -> tuple[list[float | None], list[int]]:
    """Compute Supertrend (length, multiplier) matching TradingView Pine Script ta.supertrend()."""
    if df is None or len(df) < 2:
        n = len(df) if df is not None else 0
        return [None] * n, [1] * n

    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    prev_close = close.shift(1).bfill()

    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / length, adjust=False).mean()
    hl2 = (high + low) / 2
    basic_upper = (hl2 + mult * atr).tolist()
    basic_lower = (hl2 - mult * atr).tolist()
    c = close.tolist()

    n = len(df)
    final_upper = [0.0] * n
    final_lower = [0.0] * n
    supertrend: list[float | None] = [None] * n
    direction: list[int] = [1] * n

    for i in range(n):
        if i == 0:
            final_upper[i] = basic_upper[i]
            final_lower[i] = basic_lower[i]
            direction[i] = 1 if c[i] >= (high.iloc[0] + low.iloc[0]) / 2 else -1
            supertrend[i] = round(final_lower[i] if direction[i] == 1 else final_upper[i], 2)
            continue

        # Final Lower Band
        if basic_lower[i] > final_lower[i - 1] or c[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Final Upper Band
        if basic_upper[i] < final_upper[i - 1] or c[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Trend direction determination
        if direction[i - 1] == 1:
            if c[i] < final_lower[i]:
                direction[i] = -1
            else:
                direction[i] = 1
        else:
            if c[i] > final_upper[i]:
                direction[i] = 1
            else:
                direction[i] = -1

        val = final_lower[i] if direction[i] == 1 else final_upper[i]
        supertrend[i] = round(float(val), 2)

    return supertrend, direction


def analyze_technicals(df: pd.DataFrame, ticker: str = "") -> dict[str, Any]:
    """Analyze OHLCV data and compute comprehensive technical consensus."""
    if df is None or len(df) < 15:
        return {
            "ticker": ticker.upper(),
            "status": "insufficient_data",
            "verdict": "NEUTRAL",
            "score": 0,
            "counts": {"buy": 0, "neutral": 0, "sell": 0, "total": 0},
            "moving_averages": {"verdict": "NEUTRAL", "counts": {"buy": 0, "neutral": 0, "sell": 0}, "indicators": []},
            "oscillators": {"verdict": "NEUTRAL", "counts": {"buy": 0, "neutral": 0, "sell": 0}, "indicators": []},
            "summary_text": "Insufficient historical data for technical analysis.",
        }

    out = df.copy().sort_values("date").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    close = out["close"]
    volume = out["volume"]
    cur_price = float(close.iloc[-1])

    # -------------------------------------------------------------
    # 1. Moving Averages Calculation
    # -------------------------------------------------------------
    ma_indicators: list[dict[str, Any]] = []
    ma_buys = 0
    ma_sells = 0
    ma_neutrals = 0

    def evaluate_ma(name: str, ma_series: pd.Series, label: str):
        nonlocal ma_buys, ma_sells, ma_neutrals
        val = _num(ma_series.iloc[-1])
        if val is None:
            return
        diff_pct = ((cur_price - val) / val) * 100
        if diff_pct > 0.5:
            action = "BUY"
            ma_buys += 1
            detail = f"Price is {diff_pct:.1f}% above {label} (Bullish support)"
        elif diff_pct < -0.5:
            action = "SELL"
            ma_sells += 1
            detail = f"Price is {abs(diff_pct):.1f}% below {label} (Bearish resistance)"
        else:
            action = "NEUTRAL"
            ma_neutrals += 1
            detail = f"Price is consolidating at {label}"

        ma_indicators.append({
            "name": name,
            "label": label,
            "value": round(val, 2),
            "action": action,
            "detail": detail,
        })

    # EMAs
    out["ema_10"] = close.ewm(span=10, adjust=False).mean()
    out["ema_20"] = close.ewm(span=20, adjust=False).mean()
    out["ema_50"] = close.ewm(span=50, adjust=False).mean()
    out["ema_100"] = close.ewm(span=100, adjust=False).mean()
    out["ema_200"] = close.ewm(span=200, adjust=False).mean()

    # SMAs
    out["sma_10"] = close.rolling(10, min_periods=1).mean()
    out["sma_20"] = close.rolling(20, min_periods=1).mean()
    out["sma_50"] = close.rolling(50, min_periods=1).mean()
    out["sma_100"] = close.rolling(100, min_periods=1).mean()
    out["sma_200"] = close.rolling(200, min_periods=1).mean()

    evaluate_ma("EMA 10", out["ema_10"], "10-day EMA")
    evaluate_ma("EMA 20", out["ema_20"], "20-day EMA")
    evaluate_ma("EMA 50", out["ema_50"], "50-day EMA")
    evaluate_ma("EMA 100", out["ema_100"], "100-day EMA")
    evaluate_ma("EMA 200", out["ema_200"], "200-day EMA")

    evaluate_ma("SMA 10", out["sma_10"], "10-day SMA")
    evaluate_ma("SMA 20", out["sma_20"], "20-day SMA")
    evaluate_ma("SMA 50", out["sma_50"], "50-day SMA")
    evaluate_ma("SMA 100", out["sma_100"], "100-day SMA")
    evaluate_ma("SMA 200", out["sma_200"], "200-day SMA")

    # Golden Cross / Death Cross Check
    sma50_val = _num(out["sma_50"].iloc[-1])
    sma200_val = _num(out["sma_200"].iloc[-1])
    golden_cross = False
    death_cross = False
    if sma50_val is not None and sma200_val is not None:
        if sma50_val > sma200_val:
            golden_cross = True
            ma_indicators.append({
                "name": "Golden/Death Cross",
                "label": "50/200 SMA Cross",
                "value": round(sma50_val - sma200_val, 2),
                "action": "BUY",
                "detail": "Golden Cross active (50 SMA above 200 SMA)",
            })
            ma_buys += 1
        else:
            death_cross = True
            ma_indicators.append({
                "name": "Golden/Death Cross",
                "label": "50/200 SMA Cross",
                "value": round(sma50_val - sma200_val, 2),
                "action": "SELL",
                "detail": "Death Cross active (50 SMA below 200 SMA)",
            })
            ma_sells += 1

    # Supertrend (10, 3)
    st_vals, st_dirs = compute_supertrend(out, length=10, mult=3.0)
    latest_st = st_vals[-1] if st_vals else None
    latest_st_dir = st_dirs[-1] if st_dirs else 1
    if latest_st is not None:
        if latest_st_dir == 1:
            st_action = "BUY"
            st_detail = f"Supertrend (10, 3) is Bullish (Dynamic support at ₹{latest_st:.2f})"
            ma_buys += 1
        else:
            st_action = "SELL"
            st_detail = f"Supertrend (10, 3) is Bearish (Dynamic resistance at ₹{latest_st:.2f})"
            ma_sells += 1

        ma_indicators.append({
            "name": "Supertrend (10, 3)",
            "label": "ATR Trailing Trendline",
            "value": latest_st,
            "action": st_action,
            "detail": st_detail,
        })

    # -------------------------------------------------------------
    # 2. Oscillators Calculation
    # -------------------------------------------------------------
    osc_indicators: list[dict[str, Any]] = []
    osc_buys = 0
    osc_sells = 0
    osc_neutrals = 0

    # RSI (14)
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = losses.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi_series = 100 - (100 / (1 + rs))
    rsi_val = _num(rsi_series.iloc[-1])

    if rsi_val is not None:
        if rsi_val <= 30:
            rsi_action = "BUY"
            rsi_detail = f"RSI is oversold at {rsi_val:.1f} (Rebound expected)"
            osc_buys += 1
        elif rsi_val >= 70:
            rsi_action = "SELL"
            rsi_detail = f"RSI is overbought at {rsi_val:.1f} (Exhaustion warning)"
            osc_sells += 1
        else:
            rsi_action = "NEUTRAL"
            rsi_detail = f"RSI is balanced at {rsi_val:.1f}"
            osc_neutrals += 1

        osc_indicators.append({
            "name": "RSI (14)",
            "label": "Relative Strength Index",
            "value": round(rsi_val, 1),
            "action": rsi_action,
            "detail": rsi_detail,
        })

    # MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    macd_val = _num(macd_line.iloc[-1])
    sig_val = _num(macd_signal.iloc[-1])
    hist_val = _num(macd_hist.iloc[-1])
    if macd_val is not None and sig_val is not None and hist_val is not None:
        if hist_val > 0.05:
            macd_action = "BUY"
            macd_detail = f"MACD ({macd_val:.2f}) above Signal ({sig_val:.2f}) — Bullish expansion"
            osc_buys += 1
        elif hist_val < -0.05:
            macd_action = "SELL"
            macd_detail = f"MACD ({macd_val:.2f}) below Signal ({sig_val:.2f}) — Bearish divergence"
            osc_sells += 1
        else:
            macd_action = "NEUTRAL"
            macd_detail = "MACD line converging with Signal line"
            osc_neutrals += 1

        osc_indicators.append({
            "name": "MACD (12, 26)",
            "label": "Moving Average Convergence Divergence",
            "value": round(hist_val, 2),
            "action": macd_action,
            "detail": macd_detail,
        })

    # Bollinger Bands (20, 2)
    bb_mid = close.rolling(20, min_periods=1).mean()
    bb_std = close.rolling(20, min_periods=1).std(ddof=0)
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    bb_up_val = _num(bb_upper.iloc[-1])
    bb_low_val = _num(bb_lower.iloc[-1])
    if bb_up_val is not None and bb_low_val is not None:
        if cur_price >= bb_up_val:
            bb_action = "SELL"
            bb_detail = f"Price at ₹{cur_price:.2f} pierced Upper Band (₹{bb_up_val:.2f})"
            osc_sells += 1
        elif cur_price <= bb_low_val:
            bb_action = "BUY"
            bb_detail = f"Price at ₹{cur_price:.2f} pierced Lower Band (₹{bb_low_val:.2f})"
            osc_buys += 1
        else:
            bb_action = "NEUTRAL"
            pct_b = (cur_price - bb_low_val) / (bb_up_val - bb_low_val) if bb_up_val != bb_low_val else 0.5
            bb_detail = f"Trading inside bands ({pct_b * 100:.0f}% of range)"
            osc_neutrals += 1

        osc_indicators.append({
            "name": "Bollinger Bands",
            "label": "Volatility Bands (20, 2)",
            "value": round(cur_price, 2),
            "action": bb_action,
            "detail": bb_detail,
        })

    # Stochastic %K, %D (14, 3, 3)
    low14 = out["low"].rolling(14, min_periods=1).min()
    high14 = out["high"].rolling(14, min_periods=1).max()
    denom = high14 - low14
    stoch_k = 100 * ((close - low14) / denom.replace(0, float("nan")))
    stoch_d = stoch_k.rolling(3, min_periods=1).mean()
    k_val = _num(stoch_k.iloc[-1])
    d_val = _num(stoch_d.iloc[-1])

    if k_val is not None and d_val is not None:
        if k_val < 20 and d_val < 20 and k_val > d_val:
            stoch_action = "BUY"
            stoch_detail = f"Stochastic (%K={k_val:.1f}) oversold bullish crossover"
            osc_buys += 1
        elif k_val > 80 and d_val > 80 and k_val < d_val:
            stoch_action = "SELL"
            stoch_detail = f"Stochastic (%K={k_val:.1f}) overbought bearish crossover"
            osc_sells += 1
        elif k_val < 20:
            stoch_action = "BUY"
            stoch_detail = f"Stochastic oversold at {k_val:.1f}"
            osc_buys += 1
        elif k_val > 80:
            stoch_action = "SELL"
            stoch_detail = f"Stochastic overbought at {k_val:.1f}"
            osc_sells += 1
        else:
            stoch_action = "NEUTRAL"
            stoch_detail = f"Stochastic in neutral territory ({k_val:.1f})"
            osc_neutrals += 1

        osc_indicators.append({
            "name": "Stochastic",
            "label": "Stochastic Oscillator (14, 3, 3)",
            "value": round(k_val, 1),
            "action": stoch_action,
            "detail": stoch_detail,
        })

    # Volume Anomaly / Flow (20d)
    vol_sma20 = volume.rolling(20, min_periods=1).mean()
    vol_ratio = _num((volume / vol_sma20.replace(0, float("nan"))).iloc[-1])
    ret1d = _num((close.pct_change() * 100).iloc[-1])

    if vol_ratio is not None and ret1d is not None:
        if vol_ratio >= 1.5 and ret1d > 0:
            vol_action = "BUY"
            vol_detail = f"Volume surge ({vol_ratio:.1f}x 20d avg) confirming bullish accumulation"
            osc_buys += 1
        elif vol_ratio >= 1.5 and ret1d < 0:
            vol_action = "SELL"
            vol_detail = f"Heavy selling volume ({vol_ratio:.1f}x 20d avg) confirming distribution"
            osc_sells += 1
        else:
            vol_action = "NEUTRAL"
            vol_detail = f"Volume is normal ({vol_ratio:.1f}x average)"
            osc_neutrals += 1

        osc_indicators.append({
            "name": "Volume Flow",
            "label": "20-day Volume Expansion",
            "value": round(vol_ratio, 1),
            "action": vol_action,
            "detail": vol_detail,
        })

    # -------------------------------------------------------------
    # 3. Consensus Ratings
    # -------------------------------------------------------------
    total_buys = ma_buys + osc_buys
    total_sells = ma_sells + osc_sells
    total_neutrals = ma_neutrals + osc_neutrals
    total_indicators = total_buys + total_sells + total_neutrals

    def rating_from_counts(b: int, s: int, total: int) -> str:
        if total == 0:
            return "NEUTRAL"
        buy_ratio = b / total
        sell_ratio = s / total
        if buy_ratio >= 0.65:
            return "STRONG BUY"
        if buy_ratio >= 0.50:
            return "BUY"
        if sell_ratio >= 0.65:
            return "STRONG SELL"
        if sell_ratio >= 0.50:
            return "SELL"
        return "NEUTRAL"

    overall_verdict = rating_from_counts(total_buys, total_sells, total_indicators)
    ma_verdict = rating_from_counts(ma_buys, ma_sells, len(ma_indicators))
    osc_verdict = rating_from_counts(osc_buys, osc_sells, len(osc_indicators))

    # Normalized score: -100 (Full Sell) to +100 (Full Buy)
    net_score = round(((total_buys - total_sells) / max(total_indicators, 1)) * 100)

    summary_text = (
        f"Consensus indicates {overall_verdict} for {ticker or 'the stock'} with {total_buys} Buy, "
        f"{total_neutrals} Neutral, and {total_sells} Sell indicator signals."
    )

    return {
        "ticker": ticker.upper(),
        "status": "ok",
        "current_price": round(cur_price, 2),
        "verdict": overall_verdict,
        "score": net_score,
        "counts": {
            "buy": total_buys,
            "neutral": total_neutrals,
            "sell": total_sells,
            "total": total_indicators,
        },
        "moving_averages": {
            "verdict": ma_verdict,
            "counts": {"buy": ma_buys, "neutral": ma_neutrals, "sell": ma_sells},
            "indicators": ma_indicators,
        },
        "oscillators": {
            "verdict": osc_verdict,
            "counts": {"buy": osc_buys, "neutral": osc_neutrals, "sell": osc_sells},
            "indicators": osc_indicators,
        },
        "summary_text": summary_text,
    }


def evaluate_tip_divergence(
    ticker: str,
    technicals: dict[str, Any],
    tip_markers: int = 0,
) -> dict[str, Any]:
    """Compare tip promotion claim against technical reality to detect artificial pumps."""
    verdict = technicals.get("verdict", "NEUTRAL")
    score = technicals.get("score", 0)

    divergence_risk = "LOW"
    rationale = "Technical indicators are in agreement with general market trends."

    if tip_markers >= 2:
        if verdict in ("STRONG SELL", "SELL"):
            divergence_risk = "CRITICAL"
            rationale = (
                f"Severe Divergence: Promotional tip urges buying, but technical indicators show a {verdict} "
                f"rating ({technicals.get('counts', {}).get('sell', 0)} Sell signals). High probability of distribution/dump."
            )
        elif verdict == "NEUTRAL":
            divergence_risk = "HIGH"
            rationale = (
                f"Promotional tip promises guaranteed returns, but technical consensus is purely NEUTRAL. "
                "Lack of organic technical momentum suggests artificial hype."
            )
        else:
            # Even if BUY, check if RSI is overbought
            for osc in technicals.get("oscillators", {}).get("indicators", []):
                if osc["name"] == "RSI (14)" and osc.get("action") == "SELL":
                    divergence_risk = "HIGH"
                    rationale = (
                        "Overbought Warning: Stock has upward momentum, but RSI is in an extreme overbought region. "
                        "Promoters frequently dump into retail buying at exhaustion peaks."
                    )
                    break

    return {
        "divergence_risk": divergence_risk,
        "technical_verdict": verdict,
        "technical_score": score,
        "rationale": rationale,
    }
