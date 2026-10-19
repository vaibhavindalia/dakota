"""Build annotation-ready financial evidence dataset from data/live/investigations.jsonl.

Strictly preserves:
- Stable record ID (ANN-LIVE-001 ...)
- Original text / tip description / matched text
- Source name, URL, or internal reference
- Publication and collection timestamps
- Company/ticker or macroeconomic entity
- Human-reviewed label field (empty for annotation)
- Annotation rationale field (empty for annotation)
- Evidence IDs
- Duplicate / overlap group detection via content fingerprinting
"""
import ast
import hashlib
import json
import os
from collections import defaultdict

def main():
    jsonl_path = "data/live/investigations.jsonl"
    if not os.path.isfile(jsonl_path):
        print(f"File not found: {jsonl_path}")
        return

    with open(jsonl_path, "r", encoding="utf-8") as f:
        raw_lines = [json.loads(line) for line in f if line.strip()]

    records = []
    fingerprints = defaultdict(list)

    for idx, item in enumerate(raw_lines):
        rec_id = f"ANN-LIVE-{idx+1:03d}"
        
        # Ticker resolution
        ticker = (
            item.get("ticker")
            or item.get("impact", {}).get("entity")
            or item.get("entity")
            or "UNKNOWN"
        )
        if isinstance(ticker, list):
            ticker = ticker[0] if ticker else "UNKNOWN"
        ticker = str(ticker).upper()

        # Text resolution
        ch_name = item.get("channel_username") or item.get("channel") or "Telegram"
        msg_type = item.get("classification", {}).get("message_type") or "tip"
        matched_text = item.get("impact", {}).get("matched_text") or ""
        pt = item.get("price_target")
        urgency = item.get("urgency", False)

        claim_parts = [f"Source: {ch_name}"]
        if matched_text:
            claim_parts.append(f"Entity: {matched_text}")
        if pt:
            claim_parts.append(f"Target: ₹{pt}")
        if urgency:
            claim_parts.append("(Urgent call)")
        claim_parts.append(f"Type: {msg_type}")
        original_text = " | ".join(claim_parts)

        timestamp = item.get("captured_at") or item.get("telegram_timestamp") or "2026-10-08T12:00:00Z"

        # Fingerprint
        fp = item.get("fingerprint") or hashlib.sha256(original_text.encode("utf-8")).hexdigest()[:12]
        fingerprints[fp].append(rec_id)

        # Evidence collection: Reddit, News, BSE
        inv = item.get("investigation", {})
        ev = inv.get("evidence", {})
        
        sources = []
        news_headlines = []

        # 1. News
        news_data = ev.get("news", {})
        for art in news_data.get("articles", []):
            title = art.get("title") or art.get("headline") or ""
            url = art.get("url") or ""
            if title:
                news_headlines.append(title)
                sources.append({"name": "News", "url": url, "title": title})

        # 2. Reddit social discussions
        reddit_data = ev.get("social", {}).get("reddit", {})
        for r_res in reddit_data.get("results", []):
            title = r_res.get("title") or ""
            url = r_res.get("url") or ""
            sub = r_res.get("subreddit") or "reddit"
            if title:
                sources.append({"name": f"Reddit (r/{sub})", "url": url, "title": title})
                if len(news_headlines) < 5:
                    news_headlines.append(f"[r/{sub}] {title}")

        # 3. BSE Corporate Announcements
        company_data = inv.get("investigations", [{}])[0].get("company", {}) if inv.get("investigations") else {}
        bse_data = company_data.get("bse", {})
        bse_anns = bse_data.get("announcements")
        if isinstance(bse_anns, str) and bse_anns.startswith("{'Table'"):
            try:
                parsed = ast.literal_eval(bse_anns)
                for ann in parsed.get("Table", [])[:3]:
                    h = ann.get("HEADLINE") or ann.get("NEWSSUB") or ""
                    u = ann.get("NSURL") or ""
                    if h:
                        sources.append({"name": "BSE India Filing", "url": u, "title": h})
                        if len(news_headlines) < 8:
                            news_headlines.append(f"[BSE] {h}")
            except Exception:
                pass

        evidence_ids = [f"E_LIVE_TG_{ticker}_{idx+1:03d}"]
        if sources:
            evidence_ids.append(f"E_DISC_{ticker}_{idx+1:03d}")

        # Telemetry from investigation
        inv_item = ((inv or {}).get("investigations") or [{}])[0] if (inv or {}).get("investigations") else {}
        market = (inv_item or {}).get("market") or {}
        snapshot = market.get("snapshot") or {}

        records.append({
            "record_id": rec_id,
            "ticker": ticker,
            "original_text": original_text,
            "news_headlines": news_headlines[:8],
            "sources": sources[:10],
            "published_at": timestamp,
            "collected_at": timestamp,
            "duplicate_group": fp,
            "human_reviewed_label": None,
            "annotation_rationale": None,
            "evidence_ids": evidence_ids,
            "sample": {
                "ticker": ticker,
                "as_of": timestamp,
                "latest_price": snapshot.get("close"),
                "change_pct": snapshot.get("return_1d_pct"),
                "volume": snapshot.get("volume"),
                "delivery_pct": snapshot.get("delivery_pct"),
                "is_surveillance": False,
                "risk_score": (item.get("risk") or {}).get("score", 0.0),
                "news_headlines": news_headlines[:8],
                "social_signals": [original_text]
            }
        })

    for r in records:
        r["duplicate_count"] = len(fingerprints[r["duplicate_group"]])
        r["duplicate_peers"] = [x for x in fingerprints[r["duplicate_group"]] if x != r["record_id"]]

    output_data = {
        "metadata": {
            "total_records": len(records),
            "unique_fingerprints": len(fingerprints),
            "records_with_external_evidence": sum(1 for r in records if r["sources"]),
            "human_verified_count": 0,
            "allowed_labels": [
                "Bullish",
                "Bearish",
                "Neutral",
                "Mixed",
                "Ambiguous",
                "Insufficient Evidence"
            ],
            "annotation_instructions": (
                "Review each record's original_text, news_headlines, and telemetry. "
                "Assign one of allowed_labels to 'human_reviewed_label' and document the rationale in 'annotation_rationale'. "
                "Do not label uncorroborated promotional claims as Bullish without positive fundamental/news corroboration."
            )
        },
        "records": records
    }

    out_file = "data/annotation_ready_financial_evidence.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"Successfully generated {out_file} with {len(records)} records ({len(fingerprints)} unique fingerprints, {output_data['metadata']['records_with_external_evidence']} with external sources).")

if __name__ == "__main__":
    main()
