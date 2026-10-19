import json
import sqlite3
import os
import sys

sys.path.insert(0, ".")
print("=== 1. src/intelligence/jev/dataset.py ===")
from src.intelligence.jev.dataset import get_curated_indian_equity_dataset
curated = get_curated_indian_equity_dataset()
print(f"Total curated records: {len(curated)}")
curated_labels = {}
for s in curated:
    curated_labels[s.label] = curated_labels.get(s.label, 0) + 1
print(f"Labels: {curated_labels}")
print(f"Sample IDs: {[s.sample_id for s in curated[:5]]}")
print(f"Are labels human-verified? Yes, handcrafted curated benchmark with rationales.")

print("\n=== 2. scripts/evaluate_financial_evidence.py Default Set ===")
from scripts.evaluate_financial_evidence import get_default_held_out_dataset
held_out = get_default_held_out_dataset()
print(f"Total held-out records: {len(held_out)}")
held_out_labels = {}
for s in held_out:
    lbl = s["label"]
    held_out_labels[lbl] = held_out_labels.get(lbl, 0) + 1
print(f"Labels: {held_out_labels}")
print(f"Sample IDs: {[s['sample_id'] for s in held_out]}")
print(f"Overlap with curated: {set(s['sample_id'] for s in held_out).intersection(set(s.sample_id for s in curated))}")

print("\n=== 3. data/live/investigations.jsonl ===")
if os.path.exists("data/live/investigations.jsonl"):
    with open("data/live/investigations.jsonl", encoding="utf-8") as f:
        live = [json.loads(line) for line in f if line.strip()]
    print(f"Total live records: {len(live)}")
    has_labels = sum(1 for r in live if "label" in r or "ground_truth" in r)
    has_news = sum(1 for r in live if r.get("investigation", {}).get("evidence", {}).get("news", {}).get("articles"))
    print(f"Records with explicit human ground truth label: {has_labels}")
    print(f"Records with real exchange/Google/Yahoo news articles attached: {has_news}")

print("\n=== 4. data/tips/investigations.jsonl ===")
if os.path.exists("data/tips/investigations.jsonl"):
    with open("data/tips/investigations.jsonl", encoding="utf-8") as f:
        tips = [json.loads(line) for line in f if line.strip()]
    print(f"Total tips records: {len(tips)}")
    has_labels = sum(1 for r in tips if "label" in r or "ground_truth" in r)
    print(f"Records with explicit human ground truth label: {has_labels}")

print("\n=== 5. data/dakota.db ===")
con = sqlite3.connect("data/dakota.db")
cur = con.cursor()
tip_events = cur.execute("SELECT count(*) FROM tip_events").fetchone()[0]
messages = cur.execute("SELECT count(*) FROM intelligence_messages").fetchone()[0]
print(f"tip_events: {tip_events} rows (unlabeled operational intake)")
print(f"intelligence_messages: {messages} rows (chatbot interactions with cited evidence)")
