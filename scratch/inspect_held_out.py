import json

with open("data/held_out_real_evaluation_results.json", "r", encoding="utf-8") as f:
    res = json.load(f)

print("Evaluation Summary:")
print("Total examples:", res.get("total_examples"))
print("Accuracy:", res.get("accuracy"))
print("Balanced accuracy:", res.get("balanced_accuracy"))
print("Macro F1:", res.get("macro_f1"))
print("Latency summary (ms):", res.get("latency_summary_ms"))
print("Peak GPU memory (MB):", res.get("peak_gpu_memory_mb"))
print("\nPer-example details:")
for p in res.get("predictions", []):
    u = p.get("usage", {})
    lat = p.get("latency_ms", 0) / 1000.0
    print(f"ID: {p.get('record_id')} | Ticker: {p.get('ticker')} | Latency: {lat:.2f}s | Tokens: {u.get('prompt_tokens')} | Pred: {p.get('predicted_label')} | True: {p.get('true_label')}")
