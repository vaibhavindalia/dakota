"""Campaign map: cluster anonymised tip reports to surface coordination.

Input: report records from tipcheck.privacy.make_report_record()
       (ticker, ts, fingerprint, source_label) — never raw text.

Two clustering layers:
  1. Exact fingerprint matches (same template) — free, via privacy.fingerprint.
  2. Near-duplicates via TF-IDF cosine on NORMALISED text (only available in
     session memory — normalised text is not persisted either, per the plan).

Output feeds:
  - engine coordination_signals() (report counts + duplicate counts)
  - a NetworkX graph for the Streamlit campaign map

DEMO RULE: the replayed feed is synthetic and must be LABELLED as such in the UI.
"""
from __future__ import annotations

import pandas as pd

try:
    import networkx as nx
except ImportError:  # pragma: no cover
    nx = None


def make_replay_feed(seed: int = 7) -> pd.DataFrame:
    """Synthetic replayed campaign feed for the demo. LABEL AS REPLAYED DATA.

    Simulates: a coordinated burst of near-duplicate tips on one SME ticker,
    plus organic background noise on others.
    """
    import numpy as np
    from src.tipcheck.privacy import make_report_record

    rng = np.random.default_rng(seed)
    now = pd.Timestamp.now().floor("min")
    rows = []

    template = ("URGENT {t} target rs # guaranteed returns join vip telegram "
                "channel only # slots left")
    for i in range(31):  # mirrors the report's example: 31 users / 40 minutes
        ts = now - pd.Timedelta(minutes=int(rng.uniform(0, 40)))
        rows.append(make_report_record("VARANIUM", ts, template.format(t="VARANIUM"),
                                       source_label="replay"))
    for t in ["CTRL01", "CTRL03", "CTRL08"]:  # organic noise
        for i in range(int(rng.integers(0, 3))):
            ts = now - pd.Timedelta(hours=float(rng.uniform(0, 72)))
            rows.append(make_report_record(t, ts, f"any view on {t.lower()}?",
                                           source_label="replay"))

    df = pd.DataFrame(rows)
    df["n_scam_markers"] = [3 if r.ticker == "VARANIUM" else 0 for r in df.itertuples()]
    df["replayed"] = True
    return df


def campaign_clusters(reports: pd.DataFrame, window_hours: int = 6) -> pd.DataFrame:
    """Summarise coordination per ticker: report burst + duplicate templates."""
    if reports.empty:
        return pd.DataFrame(columns=["ticker", "n_reports", "n_reporters_window",
                                     "max_dup_count", "first_seen", "last_seen"])
    out = []
    cutoff = reports.ts.max() - pd.Timedelta(hours=window_hours)
    for ticker, g in reports.groupby("ticker"):
        window = g[g.ts >= cutoff]
        out.append({
            "ticker": ticker,
            "n_reports": len(g),
            "n_reporters_window": len(window),
            "max_dup_count": int(window.fingerprint.value_counts().iloc[0]) if len(window) else 0,
            "first_seen": g.ts.min(),
            "last_seen": g.ts.max(),
        })
    return pd.DataFrame(out).sort_values("n_reporters_window", ascending=False)


def campaign_graph(reports: pd.DataFrame):
    """NetworkX graph: ticker nodes sized by report count, edges between
    tickers sharing identical templates (same fingerprint)."""
    if nx is None:
        raise ImportError("pip install networkx")
    g = nx.Graph()
    for ticker, grp in reports.groupby("ticker"):
        g.add_node(ticker, reports=len(grp))
    for fp, grp in reports.groupby("fingerprint"):
        tickers = grp.ticker.unique()
        for i in range(len(tickers)):
            for j in range(i + 1, len(tickers)):
                g.add_edge(tickers[i], tickers[j], template=fp)
    return g
