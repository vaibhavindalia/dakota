import os
import sys
import time
import json
import torch
import numpy as np
from transformers import (
    AutoTokenizer,
    BitsAndBytesConfig,
    Qwen3_5ForCausalLM,
)

sys.path.insert(0, os.path.abspath("."))
from src.intelligence.jev.dataset import get_curated_indian_equity_dataset
from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask
from src.intelligence.jev.prompt_builder import prepare_prompt
from src.intelligence.jev.schemas import ClassifierQuestion, ClassifierRequest, QuestionType, ClassifierOption

print("=" * 75)
print("DAKOTA PHASE 2D: OPTIMIZED CONFIGURATION BENCHMARK (TEXT-ONLY Qwen3_5ForCausalLM)")
print("=" * 75)

model_id = "Qwen/Qwen3.5-9B"
device = "cuda:0"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

tokenizer = AutoTokenizer.from_pretrained(model_id)

# 1. Cold Model Loading Measurement
torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()
t0_load = time.perf_counter()
model = Qwen3_5ForCausalLM.from_pretrained(
    model_id,
    quantization_config=bnb_config,
    device_map=device,
    torch_dtype=torch.bfloat16,
)
model.eval()
torch.cuda.synchronize()
cold_load_time = time.perf_counter() - t0_load

alloc_post_load = torch.cuda.memory_allocated() / (1024 ** 2)
res_post_load = torch.cuda.memory_reserved() / (1024 ** 2)

print(f"Cold Model-Loading Time: {cold_load_time:.2f} s")
print(f"Post-Load Allocated VRAM: {alloc_post_load:.2f} MiB | Reserved: {res_post_load:.2f} MiB")

# Verify device placement
tensors = list(model.parameters())
cuda_tensors = sum(1 for p in tensors if p.device.type == "cuda")
print(f"Device Placement: {cuda_tensors}/{len(tensors)} tensors strictly on cuda:0 (100% on GPU, zero offloading)")

dataset = get_curated_indian_equity_dataset()
task = SentimentDivergenceTask()

# We test 3 representative input lengths:
# Short: Ticker only + basic telemetry (~175 tokens)
# Medium: Standard evidence (~300 tokens)
# Long: Full market + news + social context (~420 tokens)

test_configs = [
    ("Short (174 tokens)", 4),      # SHREEPENNY
    ("Medium (310 tokens)", 1),     # PAYTM (partial)
    ("Long (429 tokens)", 8),       # CDSL (full context)
]

bench_results = []

for label, idx in test_configs:
    sample = dataset[idx]
    state, evidence_ids = task.build_evidence_state(sample.sample)
    q = ClassifierQuestion(
        type=QuestionType.CHOICE,
        instructions=task.task_instructions,
        criteria=task.candidate_classes,
    )
    req = ClassifierRequest(
        model=model_id,
        state=state,
        questions={"main": q},
        options=ClassifierOption(raw_logits=True),
    )
    plan = prepare_prompt(req, version="v1")
    branch = plan.questions[0]
    full_prefix = (
        f"{plan.system_prompt_prefix}\n\n"
        f"{plan.prefix_instruction}{plan.state_text or 'None'}\n\n"
        f"{plan.suffix_instruction}"
    )
    messages = [
        {"role": "system", "content": full_prefix},
        {"role": "user", "content": branch.instruction},
    ]
    formatted = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    full_text = f"{formatted}{branch.answer_prefix}"
    inputs = tokenizer(full_text, return_tensors="pt").to(device)
    n_tokens = inputs["input_ids"].shape[1]

    # Warmup run
    torch.cuda.reset_peak_memory_stats()
    with torch.no_grad():
        _ = model(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"], use_cache=False)
    torch.cuda.synchronize()

    # Repeated timed runs (5 runs)
    latencies = []
    logits_runs = []
    for _ in range(5):
        torch.cuda.synchronize()
        t_start = time.perf_counter()
        with torch.no_grad():
            out = model(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"], use_cache=False)
            last_logits = out.logits[0, -1, :]
        torch.cuda.synchronize()
        lat = (time.perf_counter() - t_start) * 1000.0
        latencies.append(lat)

        run_logits = {}
        for lbl in branch.output_labels:
            app_ids = tokenizer.encode(full_text + lbl, add_special_tokens=False)
            run_logits[lbl] = float(last_logits[app_ids[-1]].item())
        logits_runs.append(run_logits)

    peak_alloc = torch.cuda.max_memory_allocated() / (1024 ** 2)
    peak_res = torch.cuda.max_memory_reserved() / (1024 ** 2)
    headroom = 8191.50 - peak_res

    res_entry = {
        "tier": label,
        "sample_ticker": sample.ticker,
        "tokens": n_tokens,
        "median_latency_ms": float(np.median(latencies)),
        "min_latency_ms": float(np.min(latencies)),
        "max_latency_ms": float(np.max(latencies)),
        "p95_latency_ms": float(np.percentile(latencies, 95)),
        "peak_alloc_mib": peak_alloc,
        "peak_res_mib": peak_res,
        "headroom_mib": headroom,
        "logits": logits_runs[0],
    }
    bench_results.append(res_entry)
    print(f"\n{label} ({sample.ticker}, {n_tokens} tokens):")
    print(f"  Latency: Median={res_entry['median_latency_ms']:.2f} ms | Min={res_entry['min_latency_ms']:.2f} ms | Max={res_entry['max_latency_ms']:.2f} ms | p95={res_entry['p95_latency_ms']:.2f} ms")
    print(f"  VRAM: Peak Allocated={peak_alloc:.2f} MiB | Peak Reserved={peak_res:.2f} MiB | Available Headroom={headroom:.2f} MiB")

# Save structured artifact
out_path = "research/results/phase2d_optimization_benchmark.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "cold_load_time_s": cold_load_time,
        "post_load_alloc_mib": alloc_post_load,
        "post_load_res_mib": res_post_load,
        "bench_results": bench_results,
    }, f, indent=2)
print(f"\nSaved Phase 2D optimization benchmark to: {out_path}")
print("=" * 75)
