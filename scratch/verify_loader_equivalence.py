import os
import sys
import torch
from transformers import (
    AutoTokenizer,
    BitsAndBytesConfig,
    Qwen3_5ForCausalLM,
    Qwen3_5ForConditionalGeneration,
)

sys.path.insert(0, os.path.abspath("."))
from src.intelligence.jev.dataset import get_curated_indian_equity_dataset
from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask
from src.intelligence.jev.prompt_builder import prepare_prompt
from src.intelligence.jev.schemas import ClassifierQuestion, ClassifierRequest, QuestionType, ClassifierOption

print("=" * 70)
print("VERIFICATION: Logit Equivalence between ConditionalGeneration and CausalLM")
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
dataset = get_curated_indian_equity_dataset()
task = SentimentDivergenceTask()

# We test 3 samples: 0 (RELIANCE), 1 (PAYTM), 8 (CDSL)
test_indices = [0, 1, 8]
prompts = []

for idx in test_indices:
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
    prompts.append((idx, sample.ticker, full_text, branch.output_labels))

print(f"Prepared {len(prompts)} test prompts.")

# First load ConditionalGeneration, run prompts, record logits
print("\nLoading Qwen3_5ForConditionalGeneration...")
model_cond = Qwen3_5ForConditionalGeneration.from_pretrained(
    model_id,
    quantization_config=bnb_config,
    device_map=device,
    torch_dtype=torch.bfloat16,
)
model_cond.eval()

logits_cond = {}
for idx, ticker, full_text, output_labels in prompts:
    inputs = tokenizer(full_text, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model_cond(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"], use_cache=False)
        last_logits = out.logits[0, -1, :]
    
    sample_logits = {}
    base_ids = tokenizer.encode(full_text, add_special_tokens=False)
    for lbl in output_labels:
        app_ids = tokenizer.encode(full_text + lbl, add_special_tokens=False)
        t_id = app_ids[-1]
        sample_logits[lbl] = float(last_logits[t_id].item())
    logits_cond[idx] = sample_logits
    print(f"  [CondGen] Sample {idx} ({ticker}): {sample_logits}")

# Free ConditionalGeneration
del model_cond
torch.cuda.empty_cache()

# Now load CausalLM, run prompts, record logits
print("\nLoading Qwen3_5ForCausalLM...")
model_causal = Qwen3_5ForCausalLM.from_pretrained(
    model_id,
    quantization_config=bnb_config,
    device_map=device,
    torch_dtype=torch.bfloat16,
)
model_causal.eval()

logits_causal = {}
for idx, ticker, full_text, output_labels in prompts:
    inputs = tokenizer(full_text, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model_causal(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"], use_cache=False)
        last_logits = out.logits[0, -1, :]
    
    sample_logits = {}
    for lbl in output_labels:
        app_ids = tokenizer.encode(full_text + lbl, add_special_tokens=False)
        t_id = app_ids[-1]
        sample_logits[lbl] = float(last_logits[t_id].item())
    logits_causal[idx] = sample_logits
    print(f"  [CausalLM] Sample {idx} ({ticker}): {sample_logits}")

# Compute differences
print("\n" + "=" * 70)
print("NUMERICAL COMPARISON:")
max_diff_overall = 0.0
for idx, ticker, _, output_labels in prompts:
    print(f"\nSample {idx} ({ticker}):")
    for lbl in output_labels:
        c_val = logits_cond[idx][lbl]
        caus_val = logits_causal[idx][lbl]
        diff = abs(c_val - caus_val)
        if diff > max_diff_overall:
            max_diff_overall = diff
        print(f"  Label ({lbl}): CondGen={c_val:.4f} vs CausalLM={caus_val:.4f} | Diff={diff:.8f}")

print(f"\nMAX ABSOLUTE LOGIT DIFFERENCE ACROSS ALL SAMPLES & LABELS: {max_diff_overall:.8f}")
if max_diff_overall < 1e-4:
    print(">>> VERIFIED: Qwen3_5ForCausalLM produces NUMERICALLY IDENTICAL logits to Qwen3_5ForConditionalGeneration! <<<")
else:
    print(">>> WARNING: Discrepancy detected between loaders! <<<")
