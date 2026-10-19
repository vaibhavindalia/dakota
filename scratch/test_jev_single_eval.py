import json
import time
import os
import sys

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.intelligence.jev.adapters.official_jev_adapter import OfficialSimpleJEVAdapter
from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask

with open("data/research/financial_eval_dev.json", "r", encoding="utf-8") as f:
    dev_data = json.load(f)

item = dev_data[0]
print(f"Record: {item['record_id']}, Ticker: {item['ticker']}")

adapter = OfficialSimpleJEVAdapter()
task = SentimentDivergenceTask()

t0 = time.time()
res = task.classify(adapter, item["sample"])
elapsed = time.time() - t0

print(f"Predicted Label: {res.predicted_label}")
print(f"Confidence: {res.confidence}")
print(f"Latency: {round(elapsed, 2)}s")
print(f"Class Scores: {res.class_scores}")
print(f"Explanation: {res.explanation}")
