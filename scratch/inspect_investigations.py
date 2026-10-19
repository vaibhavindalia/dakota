import json

print("--- Inspect data/tips/investigations.jsonl ---")
with open("data/tips/investigations.jsonl", "r", encoding="utf-8") as f:
    lines = [json.loads(line) for line in f if line.strip()]
print(f"Total investigation lines in data/tips: {len(lines)}")
if lines:
    first = lines[0]
    print("Keys in first record:", list(first.keys()))
    print("Sample excerpt:", json.dumps({k: first[k] for k in list(first.keys())[:6]}, indent=2))

print("\n--- Inspect data/telegram/processed_messages.json ---")
try:
    with open("data/telegram/processed_messages.json", "r", encoding="utf-8") as f:
        tg_data = json.load(f)
    print(f"Processed telegram messages: {len(tg_data)}")
    if tg_data:
        print("Sample:", json.dumps(tg_data[0] if isinstance(tg_data, list) else list(tg_data.items())[:3], indent=2))
except Exception as e:
    print("Error reading telegram processed messages:", e)

print("\n--- Inspect data/live/investigations.jsonl count ---")
with open("data/live/investigations.jsonl", "r", encoding="utf-8") as f:
    live_count = sum(1 for line in f if line.strip())
print(f"Total live investigation lines: {live_count}")
with open("data/live/investigations.jsonl", "r", encoding="utf-8") as f:
    sample_live = json.loads(f.readline())
print("Live record keys:", list(sample_live.keys()))
