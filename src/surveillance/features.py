"""Market Feature Extraction Pipeline for Indian Stock Surveillance.

Computes point-in-time statistical, microstructure, and price-volume features:
- Multi-horizon returns (1d, 5d, 20d, 60d)
- Abnormal volume z-scores against 20d and 60d rolling baselines
- Volatility and volatility contraction/expansion ratios
- Price-volume divergence (Pearson correlation between returns and delta volume)
- Circuit limit hit intensity (upper/lower price bands)
- Amihud illiquidity metric
- Gap frequency and magnitude
- Market relative return
Strictly enforces no-future-lookahead invariants.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "return_1d",
    "return_5d",
    "return_20d",
    "return_60d",
    "volume_zscore_20d",
    "volume_zscore_60d",
    "volume_ratio_20d_60d",
    "volatility_20d",
    "volatility_ratio_5d_20d",
    "price_volume_corr_20d",
    "upper_circuit_count_20d",
    "lower_circuit_count_20d",
    "amihud_illiquidity_20d",
    "gap_mean_20d",
    "market_relative_return_20d",
    "delivery_pct",
]


def compute_window_features(
    df: pd.DataFrame,
    as_of_date: Optional[str] = None,
    lookback_bars: int = 65,
) -> Dict[str, float]:
    """Compute point-in-time surveillance features on historical OHLCV series.

    Input DataFrame must have columns: ['open', 'high', 'low', 'close', 'volume'].
    Optional columns: ['delivery_pct', 'upper_circuit', 'lower_circuit'].
    """
    if df.empty or len(df) < 5:
        # Return default missing representation
        return {col: 0.0 for col in FEATURE_COLUMNS}

    # Filter strictly up to as_of_date (prevent lookahead bias)
    work_df = df.copy()
    if as_of_date:
        as_of_str = str(as_of_date)[:10]
        if "trade_date" in work_df.columns:
            work_df = work_df[work_df["trade_date"].astype(str).str[:10] <= as_of_str]
        elif "date" in work_df.columns:
            work_df = work_df[pd.to_datetime(work_df["date"]).dt.strftime("%Y-%m-%d") <= as_of_str]
        elif "Date" in work_df.columns:
            work_df = work_df[pd.to_datetime(work_df["Date"]).dt.strftime("%Y-%m-%d") <= as_of_str]
        elif hasattr(work_df.index, "strftime"):
            work_df = work_df[work_df.index.strftime("%Y-%m-%d") <= as_of_str]

    if len(work_df) < 5:
        return {col: 0.0 for col in FEATURE_COLUMNS}

    # Ensure strict chronological order
    if "trade_date" in work_df.columns:
        work_df = work_df.sort_values("trade_date").reset_index(drop=True)
    elif "date" in work_df.columns:
        work_df = work_df.sort_values("date").reset_index(drop=True)
    elif "Date" in work_df.columns:
        work_df = work_df.sort_values("Date").reset_index(drop=True)

    # Take trailing lookback
    work_df = work_df.tail(lookback_bars).copy()
    closes = work_df["close"].values.astype(float)
    volumes = work_df["volume"].values.astype(float)
    highs = work_df["high"].values.astype(float) if "high" in work_df.columns else closes
    lows = work_df["low"].values.astype(float) if "low" in work_df.columns else closes
    opens = work_df["open"].values.astype(float) if "open" in work_df.columns else closes

    n = len(closes)
    curr_close = closes[-1]

    # 1. Multi-horizon returns
    ret_1d = float((curr_close / closes[-2] - 1.0) if n >= 2 and closes[-2] > 0 else 0.0)
    ret_5d = float((curr_close / closes[-6] - 1.0) if n >= 6 and closes[-6] > 0 else ret_1d)
    ret_20d = float((curr_close / closes[-21] - 1.0) if n >= 21 and closes[-21] > 0 else ret_5d)
    ret_60d = float((curr_close / closes[-61] - 1.0) if n >= 61 and closes[-61] > 0 else ret_20d)

    # 2. Volume Z-scores
    v_slice_20 = volumes[-min(20, n):]
    v_mean_20 = float(np.mean(v_slice_20))
    v_std_20 = float(np.std(v_slice_20))
    curr_vol = volumes[-1]
    vol_z_20 = float((curr_vol - v_mean_20) / (v_std_20 + 1e-6)) if v_std_20 > 0 else 0.0

    v_slice_60 = volumes[-min(60, n):]
    v_mean_60 = float(np.mean(v_slice_60))
    v_std_60 = float(np.std(v_slice_60))
    vol_z_60 = float((curr_vol - v_mean_60) / (v_std_60 + 1e-6)) if v_std_60 > 0 else vol_z_20
    vol_ratio_20_60 = float(v_mean_20 / (v_mean_60 + 1e-6)) if v_mean_60 > 0 else 1.0

    # 3. Volatility
    daily_returns = np.diff(closes) / (closes[:-1] + 1e-6)
    r_slice_20 = daily_returns[-min(20, len(daily_returns)):]
    volat_20 = float(np.std(r_slice_20)) * np.sqrt(252.0) if len(r_slice_20) > 1 else 0.0

    r_slice_5 = daily_returns[-min(5, len(daily_returns)):]
    volat_5 = float(np.std(r_slice_5)) * np.sqrt(252.0) if len(r_slice_5) > 1 else volat_20
    volat_ratio_5_20 = float(volat_5 / (volat_20 + 1e-6)) if volat_20 > 0 else 1.0

    # 4. Price-Volume Divergence / Correlation
    if len(r_slice_20) > 3 and len(v_slice_20) > 4:
        vol_changes = np.diff(v_slice_20) / (v_slice_20[:-1] + 1e-6)
        min_len = min(len(r_slice_20), len(vol_changes))
        if min_len > 3 and np.std(r_slice_20[-min_len:]) > 1e-6 and np.std(vol_changes[-min_len:]) > 1e-6:
            corr = float(np.corrcoef(r_slice_20[-min_len:], vol_changes[-min_len:])[0, 1])
            pv_corr = 0.0 if np.isnan(corr) else corr
        else:
            pv_corr = 0.0
    else:
        pv_corr = 0.0

    # 5. Circuit limit hits
    # In Indian markets, 5%, 10%, or 20% bands
    daily_high_low_spread = (highs - lows) / (closes + 1e-6)
    # Consecutive days where high == low and abs(return) >= 0.045
    uc_hits = 0
    lc_hits = 0
    slice_start = max(0, n - 20)
    for i in range(slice_start, n):
        if i == 0:
            continue
        bar_ret = (closes[i] / closes[i - 1] - 1.0)
        spread = daily_high_low_spread[i]
        # Upper circuit: price moves up near limit, zero/tiny spread
        if bar_ret >= 0.048 and spread < 0.015:
            uc_hits += 1
        elif bar_ret <= -0.048 and spread < 0.015:
            lc_hits += 1

    # 6. Amihud Illiquidity (price impact per rupee of volume)
    if len(r_slice_20) > 0 and v_mean_20 > 0:
        turnover = closes[-min(20, n):] * v_slice_20
        k = min(len(r_slice_20), len(turnover))
        if k > 1:
            r_aligned = np.abs(r_slice_20[-k:])
            t_aligned = turnover[-k:]
            valid = t_aligned > 1000.0
            if np.any(valid):
                amihud = float(np.mean(r_aligned[valid] / (t_aligned[valid] + 1e-6)) * 1e6)
            else:
                amihud = 0.0
        else:
            amihud = 0.0
    else:
        amihud = 0.0

    # 7. Gaps
    if n >= 2:
        prev_closes = closes[-min(20, n) - 1 : -1]
        cur_opens = opens[-min(20, n) :]
        min_l = min(len(prev_closes), len(cur_opens))
        gaps = np.abs(cur_opens[-min_l:] - prev_closes[-min_l:]) / (prev_closes[-min_l:] + 1e-6)
        gap_mean = float(np.mean(gaps))
    else:
        gap_mean = 0.0

    # 8. Delivery percentage
    deliv_pct = 40.0  # sensible historical median for Indian equities
    if "delivery_pct" in work_df.columns and not work_df["delivery_pct"].dropna().empty:
        valid_del = work_df["delivery_pct"].dropna().values
        if len(valid_del) > 0:
            deliv_pct = float(valid_del[-1])

    # 9. Market-relative return (benchmark proxy return ~0.08 annualized -> 0.006 per 20d)
    mkt_rel_ret_20d = float(ret_20d - 0.006)

    features = {
        "return_1d": round(ret_1d, 4),
        "return_5d": round(ret_5d, 4),
        "return_20d": round(ret_20d, 4),
        "return_60d": round(ret_60d, 4),
        "volume_zscore_20d": round(vol_z_20, 3),
        "volume_zscore_60d": round(vol_z_60, 3),
        "volume_ratio_20d_60d": round(vol_ratio_20_60, 3),
        "volatility_20d": round(volat_20, 4),
        "volatility_ratio_5d_20d": round(volat_ratio_5_20, 3),
        "price_volume_corr_20d": round(pv_corr, 3),
        "upper_circuit_count_20d": float(uc_hits),
        "lower_circuit_count_20d": float(lc_hits),
        "amihud_illiquidity_20d": round(min(amihud, 100.0), 4),
        "gap_mean_20d": round(gap_mean, 4),
        "market_relative_return_20d": round(mkt_rel_ret_20d, 4),
        "delivery_pct": round(deliv_pct, 1),
    }

    # Ensure all values are finite
    for k, v in features.items():
        if np.isnan(v) or np.isinf(v):
            features[k] = 0.0

    return features
