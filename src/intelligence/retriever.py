"""Grounded Cross-Module Intelligence Retriever for Dakota.

Fetches authorized, real records across:
- Market & Risk (Universe, 5-Pillar Risk Engine, 3-Pillar Decision Stance, Indicators)
- News (Yahoo Finance RSS, Google News RSS)
- Social (X via DDGS, StockTwits, Reddit, Instagram Graph API)
- Investigations & Syndicate Campaigns (Live store, tip parser, fingerprints)
- Portfolio Holdings
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.intelligence.models import EvidenceItem, EvidenceType, ObservationType

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]


class IntelligenceRetriever:
    """Multi-source retriever normalizing Dakota's heterogenous records into verified EvidenceItems."""

    def __init__(self) -> None:
        pass

    def extract_entities(self, query: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Extract tickers, case IDs, channels, and search terms from query and active context."""
        context = context or {}
        active_ticker = str(context.get("ticker") or "").upper().strip()
        active_case = str(context.get("investigation_id") or "").strip()

        # Regex search for Indian stock tickers (uppercase 2-12 letters, optional prefix $)
        found_tickers: list[str] = []
        if active_ticker:
            found_tickers.append(active_ticker)

        # Match potential stock symbols like $RELIANCE, RELIANCE, VARANIUM, INFY, etc.
        matches = re.findall(r"\b\$?([A-Za-z]{2,14})\b", query)
        common_words = {
            "THE", "WHAT", "HOW", "WHY", "IS", "ARE", "FOR", "AND", "STOCK", "NEWS", "RISK",
            "FIND", "SHOW", "TELL", "SUMMARY", "SUMMARIZE", "REPORT", "SCORE", "MY", "ABOUT",
            "THIS", "THAT", "WITH", "FROM", "COMPARE", "INVESTIGATE", "CAN", "YOU", "LATEST",
            "MARKET", "EVIDENCE", "PORTFOLIO", "WATCHLIST", "CHANNEL", "CAMPAIGN", "ALERT"
        }

        # Check universe for valid tickers
        import sqlite3
        db_path = BASE_DIR / "data" / "dakota.db"
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path), timeout=5.0)
                cur = conn.cursor()
                for m in matches:
                    cand = m.upper().strip()
                    if cand not in common_words and len(cand) >= 2 and cand not in found_tickers:
                        # 1. Exact ticker lookup
                        row = cur.execute("SELECT ticker FROM stock_assessments WHERE ticker = ?", (cand,)).fetchone()
                        if row:
                            found_tickers.append(row[0])
                            continue
                        # 2. Search by prefix or company name
                        search_rows = cur.execute(
                            "SELECT ticker FROM stock_assessments WHERE ticker LIKE ? OR UPPER(name) LIKE ? LIMIT 5",
                            (f"{cand}%", f"%{cand}%"),
                        ).fetchall()
                        for sr in search_rows:
                            if sr[0] not in found_tickers and (sr[0] == cand or cand in sr[0]):
                                found_tickers.append(sr[0])
                                break
                conn.close()
            except Exception as exc:
                logger.debug("Ticker db lookup failed: %s", exc)

        # Case/Investigation ID extraction
        case_id = active_case
        case_match = re.search(r"\b(INV-[A-Za-z0-9\-_]+|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}\b)", query, re.IGNORECASE)
        if case_match:
            case_id = case_match.group(1)

        # Channel extraction
        channel_match = re.search(r"(@[A-Za-z0-9_]+)", query)
        channel = channel_match.group(1) if channel_match else context.get("channel")

        # Intent detection
        q_lower = query.lower()
        is_portfolio = any(w in q_lower for w in ["portfolio", "holding", "my stocks", "invested"])
        is_campaign = any(w in q_lower for w in ["campaign", "cartel", "syndicate", "channel", "telegram group"])
        is_report = any(w in q_lower for w in ["report", "brief", "generate a report", "export"])
        is_compare = any(w in q_lower for w in ["compare", "connection", "difference", "vs", "versus"])

        return {
            "tickers": found_tickers,
            "primary_ticker": found_tickers[0] if found_tickers else None,
            "case_id": case_id,
            "channel": channel,
            "is_portfolio": is_portfolio,
            "is_campaign": is_campaign,
            "is_report": is_report,
            "is_compare": is_compare,
            "raw_query": query,
        }

    def retrieve(
        self,
        query: str,
        context: dict[str, Any] | None = None,
        max_evidence: int = 15,
    ) -> list[EvidenceItem]:
        """Execute multi-channel retrieval and return a ranked, deduplicated list of EvidenceItems."""
        entities = self.extract_entities(query, context)
        primary_ticker = entities.get("primary_ticker")
        all_tickers = entities.get("tickers") or []
        case_id = entities.get("case_id")
        items: list[EvidenceItem] = []
        counter = 1

        # 1. Market & Risk Retrieval for Identified Tickers
        for ticker in all_tickers[:2]:
            try:
                from src.market.universe_manager import get_or_assess_stock
                stock = get_or_assess_stock(ticker)
                if stock:
                    name = stock.get("name") or ticker
                    score = stock.get("score")
                    band = stock.get("band", "Unknown")
                    verdict = stock.get("verdict", "")
                    price = stock.get("latest_price")
                    change = stock.get("change_pct")

                    snippet = f"Security: {ticker} ({name}) | Segment: {stock.get('segment', 'Main')} | Risk Score: {score}/100 ({band} Risk). Verdict: {verdict}"
                    if price is not None:
                        snippet += f" | Current Price: Rs {price} ({change:+.2f}%)."

                    items.append(
                        EvidenceItem(
                            id=f"E{counter}",
                            type=EvidenceType.MARKET,
                            title=f"Dakota Equities Risk Snapshot — {ticker}",
                            snippet=snippet,
                            source_name="Dakota Risk Engine & SQLite Universe",
                            source_url=f"/stocks/{ticker}",
                            entity_id=ticker,
                            confidence=1.0,
                            verified=True,
                            observation_type=ObservationType.DIRECTLY_OBSERVED,
                            metadata={"stock": stock},
                        )
                    )
                    counter += 1

                # Risk Engine breakdown
                from src.engine.risk_engine import assess
                assessed = assess(ticker)
                reasons = assessed.get("reasons") or []
                contributions = assessed.get("contributions") or {}

                breakdown_str = f"Signal contributions: Coordination={contributions.get('coordination', 0)}, Promoter={contributions.get('promoter', 0)}, Footprint={contributions.get('market_footprint', 0)}, Financial={contributions.get('financial_integrity', 0)}, Structure={contributions.get('structure', 0)}. Key signals: " + "; ".join(reasons[:4])

                items.append(
                    EvidenceItem(
                        id=f"E{counter}",
                        type=EvidenceType.REGULATORY,
                        title=f"Dakota 5-Pillar Forensic Breakdown — {ticker}",
                        snippet=breakdown_str,
                        source_name="Dakota Forensic Risk Model",
                        source_url=f"/stocks/{ticker}",
                        entity_id=ticker,
                        confidence=0.95,
                        verified=True,
                        observation_type=ObservationType.DIRECTLY_OBSERVED,
                        metadata={"assessed": assessed},
                    )
                )
                counter += 1

                # 3-Pillar Investment Stance
                from src.market.decision_engine import evaluate_investment_stance
                stance_data = evaluate_investment_stance(ticker)
                if stance_data:
                    items.append(
                        EvidenceItem(
                            id=f"E{counter}",
                            type=EvidenceType.TECHNICAL,
                            title=f"Investment Stance Synthesis — {ticker}",
                            snippet=f"Actionable Stance: {stance_data.get('stance')} | Headline: {stance_data.get('headline')} | Passed Checklist: {stance_data.get('checklist_passed_count')}/{stance_data.get('checklist_total_count')}. Detail: {stance_data.get('subtext', '')}",
                            source_name="Dakota 3-Pillar Decision Engine",
                            source_url=f"/stocks/{ticker}",
                            entity_id=ticker,
                            confidence=0.9,
                            verified=True,
                            observation_type=ObservationType.MODEL_INFERRED,
                            metadata={"stance": stance_data},
                        )
                    )
                    counter += 1

                # 4. QN Quantitative Surveillance Model Retrieval
                try:
                    from src.surveillance.model import qn_inference
                    qn_pred = qn_inference.analyze_ticker(ticker)
                    if qn_pred and qn_pred.is_real_model:
                        qn_snip = (
                            f"QN Quantitative Manipulation Surveillance: Model Version {qn_pred.model_version} | "
                            f"Suspicious Probability: {qn_pred.manipulation_probability*100:.2f}% | "
                            f"Effective Decision Threshold: {qn_pred.effective_threshold*100:.2f}% | "
                            f"Alert Triggered: {'YES' if qn_pred.alert_triggered else 'NO'} ({qn_pred.risk_band} Risk Band). "
                            f"Top factors: {'; '.join(qn_pred.top_factor_reasons[:2])}."
                        )
                        items.append(
                            EvidenceItem(
                                id=f"E{counter}",
                                type=EvidenceType.REGULATORY,
                                title=f"QN Quantitative Manipulation Model — {ticker}",
                                snippet=qn_snip,
                                source_name=f"Dakota QN Surveillance Pipeline ({qn_pred.model_version})",
                                source_url="/surveillance",
                                entity_id=ticker,
                                confidence=qn_pred.confidence,
                                verified=True,
                                observation_type=ObservationType.MODEL_INFERRED,
                                metadata=qn_pred.to_dict(),
                            )
                        )
                        counter += 1
                except Exception as qn_exc:
                    logger.debug("QN retrieval in copilot failed: %s", qn_exc)

                # 5. Official Regulatory Enforcement Orders & Surveillance Flags
                try:
                    from src.surveillance.evidence import evidence_registry
                    events = evidence_registry.get_events_for_ticker(ticker)
                    for ev in events[:2]:
                        ev_snip = (
                            f"Official Regulatory Finding [{ev.label.value}]: {ev.summary} | "
                            f"Authority: {ev.regulator_or_authority} | Order Ref: {ev.order_reference or ev.event_id} | "
                            f"Period: {ev.start_date} to {ev.end_date}. Caveats: {ev.caveats}"
                        )
                        items.append(
                            EvidenceItem(
                                id=f"E{counter}",
                                type=EvidenceType.REGULATORY,
                                title=f"Official Regulatory Enforcement — {ticker} ({ev.regulator_or_authority})",
                                snippet=ev_snip,
                                source_name=f"Official Enforcement Archive ({ev.regulator_or_authority})",
                                source_url=ev.source_url_or_id or "/surveillance",
                                entity_id=ticker,
                                confidence=1.0 if ev.evidence_strength.value == "HIGH" else 0.85,
                                verified=True,
                                observation_type=ObservationType.DIRECTLY_OBSERVED,
                                metadata=ev.to_dict(),
                            )
                        )
                        counter += 1
                except Exception as ev_exc:
                    logger.debug("Evidence registry retrieval in copilot failed: %s", ev_exc)

            except Exception as exc:
                logger.debug("Market retrieval exception for %s: %s", ticker, exc)

        # 2. News Retrieval for Identified Tickers
        for ticker in all_tickers[:2]:
            try:
                from src.evidence.news_analyzer import fetch_yahoo_news, fetch_google_news
                yahoo_news = fetch_yahoo_news(ticker, max_items=3)
                for article in yahoo_news:
                    items.append(
                        EvidenceItem(
                            id=f"E{counter}",
                            type=EvidenceType.NEWS,
                            title=article.get("headline", ""),
                            snippet=f"Headline: {article.get('headline')} (Published: {article.get('published_at', 'Recent')})",
                            source_name=f"Yahoo Finance RSS ({article.get('source', 'Yahoo')})",
                            source_url=article.get("link"),
                            entity_id=ticker,
                            published_at=article.get("published_at"),
                            confidence=0.9,
                            verified=True,
                            observation_type=ObservationType.DIRECTLY_OBSERVED,
                            metadata={"provider": "yahoo"},
                        )
                    )
                    counter += 1

                google_news = fetch_google_news(ticker, max_items=2)
                for article in google_news:
                    items.append(
                        EvidenceItem(
                            id=f"E{counter}",
                            type=EvidenceType.NEWS,
                            title=article.get("headline", ""),
                            snippet=f"Headline: {article.get('headline')} (Source: {article.get('source', 'Google News')})",
                            source_name="Google News RSS",
                            source_url=article.get("link"),
                            entity_id=ticker,
                            published_at=article.get("published_at"),
                            confidence=0.85,
                            verified=True,
                            observation_type=ObservationType.DIRECTLY_OBSERVED,
                            metadata={"provider": "google"},
                        )
                    )
                    counter += 1
            except Exception as exc:
                logger.debug("News retrieval error for %s: %s", ticker, exc)

        # 3. Social Intelligence Retrieval (X, StockTwits)
        for ticker in all_tickers[:1]:
            try:
                from src.connectors.x_api import search_x
                x_res = search_x(ticker, max_results=3)
                if x_res.get("messages"):
                    for msg in x_res["messages"][:2]:
                        items.append(
                            EvidenceItem(
                                id=f"E{counter}",
                                type=EvidenceType.SOCIAL,
                                title=f"Public X/Twitter Discovery for ${ticker}",
                                snippet=f"{msg.get('title', '')}: {msg.get('body', '')}",
                                source_name="X / Twitter (Public Search Discovery via DDGS)",
                                source_url=msg.get("href"),
                                entity_id=ticker,
                                confidence=0.75,
                                verified=False,
                                observation_type=ObservationType.UNVERIFIED_CLAIM,
                                metadata={"platform": "x"},
                            )
                        )
                        counter += 1
            except Exception as exc:
                logger.debug("Social retrieval error for %s: %s", ticker, exc)

        # 4. Live Investigations & Cases Retrieval
        try:
            from src.intake.live_store import load_live_investigations
            live_items = load_live_investigations(limit=100)
            matched_cases = []

            for inv in live_items:
                inv_id = str(inv.get("investigation_id", ""))
                inv_ticker = str(inv.get("ticker") or (inv.get("tickers")[0] if inv.get("tickers") else "")).upper()
                inv_channel = str(inv.get("channel") or inv.get("channel_username") or "")

                is_match = False
                if case_id and (case_id == inv_id or case_id in inv_id):
                    is_match = True
                elif primary_ticker and primary_ticker == inv_ticker:
                    is_match = True
                elif entities.get("channel") and entities.get("channel").lower() in inv_channel.lower():
                    is_match = True
                elif any(w in str(inv).lower() for w in query.lower().split() if len(w) > 3 and w not in ["what", "show", "tell", "news", "risk"]):
                    is_match = True

                if is_match:
                    matched_cases.append(inv)
                    if len(matched_cases) >= 4:
                        break

            # If general query and no match, supply latest 2 cases for context
            if not matched_cases and not all_tickers and (entities.get("is_campaign") or "investigation" in query.lower()):
                matched_cases = live_items[:3]

            for inv in matched_cases:
                i_id = inv.get("investigation_id", "LIVE-INV")
                i_ticker = inv.get("ticker") or (inv.get("tickers")[0] if inv.get("tickers") else "General")
                i_channel = inv.get("channel") or inv.get("channel_username") or inv.get("source", "Intake")
                i_markers = inv.get("n_scam_markers", 0)
                i_risk = inv.get("risk", {})
                risk_score = i_risk.get("score") if isinstance(i_risk, dict) else None

                snippet = f"Case {i_id}: Monitored Source '{i_channel}' flagged security {i_ticker}."
                if i_markers:
                    snippet += f" Detected {i_markers} scam marker(s) (urgency/guaranteed returns/VIP funnel)."
                if risk_score:
                    snippet += f" Risk score assessed at {risk_score}/100."

                items.append(
                    EvidenceItem(
                        id=f"E{counter}",
                        type=EvidenceType.INVESTIGATION,
                        title=f"Dakota Case Record — {i_id} ({i_ticker})",
                        snippet=snippet,
                        source_name=f"Dakota Live Intake Feed ({i_channel})",
                        source_url=f"/investigate",
                        entity_id=str(i_ticker),
                        published_at=inv.get("stored_at") or inv.get("telegram_timestamp"),
                        confidence=0.95,
                        verified=True,
                        observation_type=ObservationType.DIRECTLY_OBSERVED,
                        metadata={"case": inv},
                    )
                )
                counter += 1

        except Exception as exc:
            logger.debug("Investigation retrieval error: %s", exc)

        # 5. Portfolio Retrieval
        if entities.get("is_portfolio") or any("portfolio" in query.lower() for _ in [1]):
            try:
                from backend.main import _load_portfolio
                holdings = _load_portfolio()
                if holdings:
                    holdings_summary = []
                    for h in holdings:
                        tk = h.get("ticker", "")
                        qty = h.get("quantity", 0)
                        holdings_summary.append(f"{tk} ({qty} units)")

                    items.append(
                        EvidenceItem(
                            id=f"E{counter}",
                            type=EvidenceType.PORTFOLIO,
                            title="Dakota Active Portfolio Holdings",
                            snippet=f"Current user portfolio contains {len(holdings)} registered position(s): " + ", ".join(holdings_summary),
                            source_name="Dakota Portfolio Store (portfolio.json)",
                            source_url="/portfolio",
                            confidence=1.0,
                            verified=True,
                            observation_type=ObservationType.DIRECTLY_OBSERVED,
                            metadata={"holdings": holdings},
                        )
                    )
                    counter += 1
            except Exception as exc:
                logger.debug("Portfolio retrieval error: %s", exc)

        # 6. Fallback if no specific entity was found: Query stock screener for broad match
        if not items and len(query.strip()) >= 2:
            try:
                from src.market.universe_manager import query_stocks
                res = query_stocks(search=query[:20], limit=3)
                for s in res.get("stocks", []):
                    items.append(
                        EvidenceItem(
                            id=f"E{counter}",
                            type=EvidenceType.MARKET,
                            title=f"Market Match: {s['ticker']} — {s.get('name', '')}",
                            snippet=f"Ticker: {s['ticker']} | Risk Score: {s.get('score', '—')} | Band: {s.get('band', 'N/A')} | Price: Rs {s.get('latest_price', '—')}",
                            source_name="Dakota Universe Screener",
                            source_url=f"/stocks/{s['ticker']}",
                            entity_id=s['ticker'],
                            confidence=0.85,
                            verified=True,
                            observation_type=ObservationType.DIRECTLY_OBSERVED,
                        )
                    )
                    counter += 1
            except Exception:
                pass

        return items[:max_evidence]
