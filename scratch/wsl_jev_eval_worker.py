import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.intelligence.jev.adapters.official_jev_adapter import OfficialSimpleJEVAdapter
from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask

input_file = "data/research/jev_eval_input.json"
output_file = "data/research/jev_eval_output.json"

if not os.path.isfile(input_file):
    print(f"Error: {input_file} not found")
    sys.exit(1)

with open(input_file, "r", encoding="utf-8") as f:
    samples = json.load(f)

adapter = OfficialSimpleJEVAdapter()
task = SentimentDivergenceTask()

# Warm-up / load weights
adapter.load_model()

predictions = []
latencies = []

for idx, s in enumerate(samples):
    t0 = time.perf_counter()
    try:
        res = task.classify(adapter, s)
        lat = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat)
        predictions.append(res.predicted_label)
    except Exception as exc:
        latencies.append(0.0)
        predictions.append("Inference Error")

mean_lat = sum(latencies) / len(latencies) if latencies else 0.0

with open(output_file, "w", encoding="utf-8") as f:
    json.dump({
        "total": len(predictions),
        "predictions": predictions,
        "mean_latency_ms": round(mean_lat, 2),
    }, f, indent=2)

print(f"Completed {len(predictions)} JEV inferences. Mean latency: {round(mean_lat, 2)} ms")
