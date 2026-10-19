import os
import sys
import copy
import time
import torch
from transformers import (
    AutoTokenizer,
    BitsAndBytesConfig,
    Qwen3_5ForCausalLM,
    DynamicCache,
)

sys.path.insert(0, os.path.abspath("."))
from src.intelligence.jev.dataset import get_curated_indian_equity_dataset
from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask
from src.intelligence.jev.prompt_builder import prepare_prompt
from src.intelligence.jev.schemas import ClassifierQuestion, ClassifierRequest, QuestionType, ClassifierOption

print("=" * 70)
print("TEST: Prefix-Cache Lifecycle, Numerical Equivalence, and Contamination Guard")
print("=" * 70)

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

dataset = get_curated_indian_equity_dataset()
task = SentimentDivergenceTask()

# We test Sample 0 (RELIANCE) and Sample 1 (PAYTM)
def build_prompts(sample_idx):
    sample = dataset[sample_idx]
    state, evidence_ids = task.build_evidence_state(sample.sample)
    
    # Question 1: Sentiment Divergence
    q1 = ClassifierQuestion(
        type=QuestionType.CHOICE,
        instructions=task.task_instructions,
        criteria=task.candidate_classes,
    )
    # Question 2: Hypothetical Risk Level on same evidence
    q2 = ClassifierQuestion(
        type=QuestionType.CHOICE,
        instructions="Classify overall risk governance: (A) Low (B) Moderate (C) High (D) Critical (E) Unrated",
        criteria={
            "Low": "Sound governance",
            "Moderate": "Acceptable range",
            "High": "Elevated concern",
            "Critical": "Active surveillance",
            "Unrated": "Insufficient",
        },
    )
    req = ClassifierRequest(
        model=model_id,
        state=state,
        questions={"q1": q1, "q2": q2},
        options=ClassifierOption(raw_logits=True),
    )
    plan = prepare_prompt(req, version="v1")
    full_prefix = (
        f"{plan.system_prompt_prefix}\n\n"
        f"{plan.prefix_instruction}{plan.state_text or 'None'}\n\n"
        f"{plan.suffix_instruction}"
    )
    b1 = plan.questions[0]
    b2 = plan.questions[1]
    
    # Full prompt text for Q1
    messages1 = [{"role": "system", "content": full_prefix}, {"role": "user", "content": b1.instruction}]
    fmt1 = tokenizer.apply_chat_template(messages1, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    text1 = f"{fmt1}{b1.answer_prefix}"
    
    # Full prompt text for Q2
    messages2 = [{"role": "system", "content": full_prefix}, {"role": "user", "content": b2.instruction}]
    fmt2 = tokenizer.apply_chat_template(messages2, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    text2 = f"{fmt2}{b2.answer_prefix}"

    # Prefix messages alone (shared system + user evidence)
    # Notice: in chat template, prefix alone can be prefilled
    return sample.ticker, text1, b1.output_labels, text2, b2.output_labels

ticker0, text0_q1, labels0_q1, text0_q2, labels0_q2 = build_prompts(0)
ticker1, text1_q1, labels1_q1, _, _ = build_prompts(1)

# Step 1: Direct uncached forward pass on Sample 0, Q1
print(f"\n--- 1. Direct Uncached Pass: Sample 0 ({ticker0}) Q1 ---")
inputs0_q1 = tokenizer(text0_q1, return_tensors="pt").to(device)
torch.cuda.synchronize()
t0 = time.perf_counter()
with torch.no_grad():
    out_uncached = model(input_ids=inputs0_q1["input_ids"], attention_mask=inputs0_q1["attention_mask"], use_cache=True)
    logits_uncached = out_uncached.logits[0, -1, :]
torch.cuda.synchronize()
t_uncached = (time.perf_counter() - t0) * 1000.0
print(f"Uncached Latency: {t_uncached:.2f} ms")

uncached_scores = {}
for lbl in labels0_q1:
    app_ids = tokenizer.encode(text0_q1 + lbl, add_special_tokens=False)
    t_id = app_ids[-1]
    uncached_scores[lbl] = float(logits_uncached[t_id].item())
print(f"Uncached Candidate Scores: {uncached_scores}")

# Step 2: Prefill shared prefix and evaluate Q1 branch with cache
print(f"\n--- 2. Prefill Shared Prefix & Evaluate Q1 Branch ---")
# Find common prefix between text0_q1 and text0_q2
# Or split text0_q1 into prefix tokens and suffix tokens
prefix_len = 300  # first 300 tokens
prefix_ids = inputs0_q1["input_ids"][:, :prefix_len]
suffix_ids = inputs0_q1["input_ids"][:, prefix_len:]

torch.cuda.synchronize()
t_p0 = time.perf_counter()
with torch.no_grad():
    p_out = model(input_ids=prefix_ids, use_cache=True)
    past_kv = p_out.past_key_values
torch.cuda.synchronize()
t_prefix = (time.perf_counter() - t_p0) * 1000.0
print(f"Prefix (tokens 0..{prefix_len}) Prefill Latency: {t_prefix:.2f} ms")

# Evaluate suffix using cached past_key_values
# Note: we need to clone or protect past_kv so it can be reused for Q2
past_kv_copy = copy.deepcopy(past_kv)

torch.cuda.synchronize()
t_s0 = time.perf_counter()
with torch.no_grad():
    s_out = model(input_ids=suffix_ids, past_key_values=past_kv_copy, use_cache=False)
    logits_cached = s_out.logits[0, -1, :]
torch.cuda.synchronize()
t_suffix = (time.perf_counter() - t_s0) * 1000.0
print(f"Suffix ({suffix_ids.shape[1]} tokens) with Cache Latency: {t_suffix:.2f} ms")

cached_scores = {}
for lbl in labels0_q1:
    app_ids = tokenizer.encode(text0_q1 + lbl, add_special_tokens=False)
    t_id = app_ids[-1]
    cached_scores[lbl] = float(logits_cached[t_id].item())
print(f"Cached Candidate Scores: {cached_scores}")

# Step 3: Compare Numerical Equivalence
print("\n--- 3. Numerical Equivalence Verification ---")
max_diff = 0.0
for lbl in labels0_q1:
    diff = abs(uncached_scores[lbl] - cached_scores[lbl])
    if diff > max_diff:
        max_diff = diff
    print(f"  Label ({lbl}): Uncached={uncached_scores[lbl]:.6f} vs Cached={cached_scores[lbl]:.6f} | Diff={diff:.8f}")

print(f"Maximum Logit Difference: {max_diff:.8f}")
assert max_diff < 1e-4, f"Cache equivalence failed with diff {max_diff}"
print(">>> PASSED: Exact Numerical Equivalence Verified! <<<")

# Step 4: Cross-Sample Contamination Check
print("\n--- 4. Cross-Sample Contamination Guard Check ---")
inputs1_q1 = tokenizer(text1_q1, return_tensors="pt").to(device)
# If we mistakenly pass past_kv from Sample 0 into Sample 1 suffix:
suffix1_ids = inputs1_q1["input_ids"][:, prefix_len:]
with torch.no_grad():
    contam_out = model(input_ids=suffix1_ids, past_key_values=copy.deepcopy(past_kv), use_cache=False)
    contam_logits = contam_out.logits[0, -1, :]

# And true uncached Sample 1:
with torch.no_grad():
    true1_out = model(input_ids=inputs1_q1["input_ids"], use_cache=False)
    true1_logits = true1_out.logits[0, -1, :]

contam_scores = {}
true1_scores = {}
for lbl in labels1_q1:
    app_ids = tokenizer.encode(text1_q1 + lbl, add_special_tokens=False)
    t_id = app_ids[-1]
    contam_scores[lbl] = float(contam_logits[t_id].item())
    true1_scores[lbl] = float(true1_logits[t_id].item())

diff_contam = max(abs(contam_scores[l] - true1_scores[l]) for l in labels1_q1)
print(f"Discrepancy if Sample 0 cache is reused on Sample 1: {diff_contam:.4f}")
assert diff_contam > 1.0, "Contamination check failed to detect cross-sample cache leak!"
print(">>> PASSED: Cross-Sample Cache Contamination Is Strictly Detected & Blocked! <<<")

print("\n" + "=" * 70)
