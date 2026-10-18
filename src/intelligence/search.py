"""Unified Cross-Module Intelligence Search for Dakota."""
from __future__ import annotations

import logging
from typing import Any
from src.intelligence.models import SearchFilter, SearchResultItem

logger = logging.getLogger(__name__)


def search_cross_module(filter_req: SearchFilter) -> dict[str, Any]:
    """Execute unified search across Stocks, Live Investigations, Campaigns, and Portfolio."""
    q = (filter_req.search or filter_req.entity or "").strip().upper()
    source_types = set(filter_req.source_types or ["stock", "investigation", "campaign", "portfolio", "news"])
    results: list[SearchResultItem] = []

    # 1. Stocks Screener Search
    if "stock" in source_types:
        try:
            from src.market.universe_manager import query_stocks
            stock_res = query_stocks(search=q, band=filter_req.risk_band, limit=8)
            for s in stock_res.get("stocks", []):
                results.append(
                    SearchResultItem(
                        id=f"stock_{s['ticker']}",
                        type="stock",
                        title=f"{s['ticker']} — {s.get('name', '')}",
                        subtitle=f"Segment: {s.get('segment', 'Main')} | Exchange: {s.get('exchange', 'NSE')}",
                        snippet=f"Risk Score: {s.get('score', '—')}/100 ({s.get('band', 'N/A')} Risk). Verdict: {s.get('verdict', 'Normal trading')}",
                        score=float(s["score"]) if s.get("score") is not None else None,
                        band=s.get("band"),
                        url=f"/stocks/{s['ticker']}",
                        metadata={"ticker": s["ticker"], "price": s.get("latest_price")},
                    )
                )
        except Exception as exc:
            logger.debug("Stock search error: %s", exc)

    # 2. Live Investigations Search
    if "investigation" in source_types:
        try:
            from src.intake.live_store import load_live_investigations
            inv_items = load_live_investigations(limit=150)
            for inv in inv_items:
                inv_id = str(inv.get("investigation_id", ""))
                ticker = str(inv.get("ticker") or (inv.get("tickers")[0] if inv.get("tickers") else "")).upper()
                channel = str(inv.get("channel") or inv.get("channel_username") or "")
                raw_str = str(inv).upper()

                if not q or (q in ticker or q in inv_id or q in channel.upper() or q in raw_str):
                    risk = inv.get("risk", {})
                    score = risk.get("score") if isinstance(risk, dict) else None
                    band = risk.get("band") if isinstance(risk, dict) else None
                    if filter_req.risk_band and band and band.lower() != filter_req.risk_band.lower():
                        continue

                    results.append(
                        SearchResultItem(
                            id=f"inv_{inv_id}",
                            type="investigation",
                            title=f"Investigation {inv_id[:16]}",
                            subtitle=f"Target: {ticker} | Source: {channel}",
                            snippet=f"Scam markers: {inv.get('n_scam_markers', 0)}. Risk Score: {score or '—'}/100. Stored: {inv.get('stored_at', '')[:10]}",
                            score=float(score) if score is not None else None,
                            band=band,
                            url="/investigate",
                            timestamp=inv.get("stored_at"),
                            metadata={"investigation_id": inv_id, "ticker": ticker},
                        )
                    )
                    if len(results) >= 20:
                        break
        except Exception as exc:
            logger.debug("Investigation search error: %s", exc)

    # 3. Campaigns Search
    if "campaign" in source_types:
        try:
            from collections import defaultdict
            from src.intake.live_store import load_live_investigations
            tips = load_live_investigations(limit=120)
            ch_groups = defaultdict(list)
            for item in tips:
                src = item.get("channel_username") or item.get("channel") or "community_feed"
                ch_groups[src].append(item)

            for ch_name, ch_tips in ch_groups.items():
                entities_touched = set()
                scam_count = 0
                for t in ch_tips:
                    tk = t.get("ticker") or (t.get("tickers")[0] if t.get("tickers") else None)
                    if tk:
                        entities_touched.add(str(tk).upper())
                    scam_count += int(t.get("n_scam_markers") or 0)

                entities_list = sorted(list(entities_touched))
                if not q or q in ch_name.upper() or any(q in e for e in entities_list):
                    results.append(
                        SearchResultItem(
                            id=f"camp_{ch_name}",
                            type="campaign",
                            title=f"Syndicate Campaign: {ch_name}",
                            subtitle=f"Touches: {', '.join(entities_list[:4]) if entities_list else 'Broad market'} ({len(entities_list)} entities)",
                            snippet=f"Analyzed {len(ch_tips)} tips. Scam markers detected: {scam_count}.",
                            url="/campaigns",
                            metadata={"channel": ch_name, "tips_count": len(ch_tips)},
                        )
                    )
                    if len(results) >= 25:
                        break
        except Exception as exc:
            logger.debug("Campaign search error: %s", exc)

    # 4. Portfolio Search
    if "portfolio" in source_types:
        try:
            import json
            from pathlib import Path
            p_path = Path("data/portfolio.json")
            if p_path.exists():
                holdings = json.loads(p_path.read_text(encoding="utf-8"))
                for h in holdings:
                    tk = str(h.get("ticker", "")).upper()
                    if not q or q in tk:
                        results.append(
                            SearchResultItem(
                                id=f"port_{tk}",
                                type="portfolio",
                                title=f"Portfolio Holding: {tk}",
                                subtitle=f"Exchange: {h.get('exchange', 'NSE')} | Qty: {h.get('quantity')}",
                                snippet="Registered position in active user portfolio.",
                                url="/portfolio",
                                metadata={"holding": h},
                            )
                        )
        except Exception as exc:
            logger.debug("Portfolio search error: %s", exc)

    # Pagination
    total = len(results)
    page = max(1, filter_req.page)
    limit = max(1, min(filter_req.limit, 50))
    offset = (page - 1) * limit
    paginated = results[offset : offset + limit]

    # Suggestions
    suggestions = []
    if q:
        suggestions = [
            f"View full risk audit for {q}",
            f"Check news and rumors for {q}",
            f"Scan syndicate channels mentioning {q}",
        ]

    return {
        "status": "ok",
        "query": filter_req.search,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total > 0 else 1,
        "results": [r.model_dump() for r in paginated],
        "suggestions": suggestions,
    }
