import os
import sys
import copy
import time
import torch
from transformers import AutoTokenizer, BitsAndBytesConfig, Qwen3_5ForCausalLM

model_id = "Qwen/Qwen3.5-9B"
device = "cuda:0"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

tokenizer = AutoTokenizer.from_pretrained(model_id)
model = Qwen3_5ForCausalLM.from_pretrained(
    model_id,
    quantization_config=bnb_config,
    device_map=device,
    torch_dtype=torch.bfloat16,
)
model.eval()

# Prompt text
prefix_text = "System: Analyze financial market evidence for RELIANCE.\nUser: Ticker: RELIANCE. Price: 2950. Volume: 5M.\n"
suffix_text = "Question: What is the prevailing sentiment? Candidates: (A) Bullish (B) Bearish (C) Neutral (D) Mixed (E) Insufficient Evidence.\nAnswer: ("
full_text = prefix_text + suffix_text

enc_full = tokenizer(full_text, return_tensors="pt").to(device)
enc_prefix = tokenizer(prefix_text, return_tensors="pt").to(device)

prefix_len = enc_prefix["input_ids"].shape[1]
full_len = enc_full["input_ids"].shape[1]
suffix_len = full_len - prefix_len
suffix_ids = enc_full["input_ids"][:, prefix_len:]

print(f"Prefix tokens: {prefix_len}, Suffix tokens: {suffix_len}, Full tokens: {full_len}")

# 1. Full Uncached Forward Pass
with torch.no_grad():
    out_full = model(input_ids=enc_full["input_ids"], attention_mask=enc_full["attention_mask"], use_cache=False)
    logits_full = out_full.logits[0, -1, :]

# 2. Prefill Prefix with use_cache=True
with torch.no_grad():
    out_pre = model(input_ids=enc_prefix["input_ids"], attention_mask=enc_prefix["attention_mask"], use_cache=True)
    past_kv = out_pre.past_key_values

# 3. Suffix Forward Pass with Cache and Full Cumulative Attention Mask
cumulative_attention_mask = torch.ones((1, full_len), dtype=torch.long, device=device)
with torch.no_grad():
    out_cached = model(
        input_ids=suffix_ids,
        attention_mask=cumulative_attention_mask,
        past_key_values=copy.deepcopy(past_kv),
        use_cache=False,
    )
    logits_cached = out_cached.logits[0, -1, :]

# 4. Compare Logits
candidate_labels = ["A", "B", "C", "D", "E"]
max_diff = 0.0
for lbl in candidate_labels:
    app_ids = tokenizer.encode(full_text + lbl, add_special_tokens=False)
    t_id = app_ids[-1]
    val_full = float(logits_full[t_id].item())
    val_cached = float(logits_cached[t_id].item())
    diff = abs(val_full - val_cached)
    if diff > max_diff:
        max_diff = diff
    print(f"Label {lbl}: Full={val_full:.6f} vs Cached={val_cached:.6f} | Diff={diff:.8f}")

print(f"Max absolute logit difference: {max_diff:.8f}")
assert max_diff < 1e-4, f"Mismatch: {max_diff}"
print(">>> SUCCESS: Exact numerical equivalence confirmed with proper cumulative attention mask! <<<")
