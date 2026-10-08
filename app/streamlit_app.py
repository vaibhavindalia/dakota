"""Dakota dashboard — Tip Check + SME screener + campaign map.

Run:  streamlit run app/streamlit_app.py
Week-2 target: this file is the whole demo UI. Keep it thin; all logic lives in src/.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # allow `import src`

import pandas as pd
import streamlit as st

from src.campaign import similarity
from src.engine.risk_engine import assess, GROUP_LABELS
from src.ingest.market_data import load_universe, load_ohlcv
from src.tipcheck.parser import check_tip

st.set_page_config(page_title="Dakota — Tip Check", page_icon="🛡️", layout="wide")
st.title("Dakota")
st.caption("Forward the tip. Check the stock. See the evidence. "
           "Risk indicators — not accusations, not advice.")

tab_tip, tab_screen, tab_map = st.tabs(["Tip Check", "SME Screener", "Campaign Map"])

# --------------------------------------------------------------- Tip Check
with tab_tip:
    st.subheader("Is this tip a trap?")
    text = st.text_area(
        "Paste the forwarded message (WhatsApp / Telegram / SMS)",
        placeholder="URGENT! VARANIUM target 500, guaranteed returns, join VIP group...",
        height=140,
    )
    if st.button("Check this tip", type="primary") and text.strip():
        result = check_tip(text)
        st.markdown(f"### {result['headline']}")
        for v in result["stock_verdicts"]:
            colour = {"High": "🔴", "Elevated": "🟠", "Low": "🟢"}[v["band"]]
            st.metric(f"{colour} {v['ticker']}", f"{v['score']} / 100 — {v['band']}")
            cols = st.columns(len(v["contributions"]))
            for col, (key, pts) in zip(cols, v["contributions"].items()):
                col.caption(GROUP_LABELS[key])
                col.write(f"**{pts}**")
        if result["combined_reasons"]:
            st.markdown("**Evidence**")
            for r in result["combined_reasons"]:
                st.write("•", r)
        st.markdown("**Safer next steps**")
        for s in result["next_steps"]:
            st.write("→", s)
        st.caption(result["disclaimer"])

# --------------------------------------------------------------- Screener
with tab_screen:
    st.subheader("SME Lifecycle Screener")
    uni = load_universe()
    ticker = st.selectbox("Company", uni.ticker.tolist())
    if ticker:
        v = assess(ticker)
        meta = uni[uni.ticker == ticker].iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Risk score", f"{v['score']} / 100", v["band"])
        c2.metric("Segment", str(meta.segment))
        c3.metric("Free float", f"{meta.free_float_pct:.0f}%" if pd.notna(meta.free_float_pct) else "—")
        c4.metric("Lock-in expiry", str(meta.lockin_expiry.date()) if pd.notna(meta.lockin_expiry) else "—")
        st.bar_chart(pd.Series(v["contributions"]).rename(index=GROUP_LABELS))
        for r in v["reasons"]:
            st.write("•", r)
        with st.expander("Price & volume (cached/synthetic until live data is wired)"):
            df = load_ohlcv(ticker).set_index("date")
            st.line_chart(df[["close"]])
            st.bar_chart(df[["volume"]].tail(60))

# --------------------------------------------------------------- Campaign map
with tab_map:
    st.subheader("Campaign Map")
    st.warning("Replayed synthetic data — demonstration only. "
               "Dakota never scrapes private groups.", icon="⚠️")
    feed = similarity.make_replay_feed()
    clusters = similarity.campaign_clusters(feed)
    st.dataframe(clusters, use_container_width=True)
    st.caption("Next iteration: render src.campaign.similarity.campaign_graph() "
               "with a graph layout here.")
