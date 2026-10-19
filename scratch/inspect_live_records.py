import json
import sys

with open("data/live/investigations.jsonl", "r", encoding="utf-8") as f:
    records = [json.loads(line) for line in f if line.strip()]

print(f"Total live records: {len(records)}")

for idx, r in enumerate(records[:10]):
    channel = r.get("channel_username") or r.get("channel") or "unknown"
    ticker = r.get("ticker")
    social = r.get("investigation", {}).get("evidence", {}).get("social", {})
    query = social.get("query", "")
    sample_text = ""
    # Look for raw text in social posts
    posts = social.get("posts", [])
    if posts and isinstance(posts, list):
        sample_text = posts[0].get("text", "")[:80]
    print(f"[{idx+1}] Channel: {channel} | Ticker: {ticker} | Query: {query}")
    if sample_text:
        print(f"    Raw Text: {ascii(sample_text)}")
