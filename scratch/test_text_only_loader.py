import os
import sys
import time
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
print("EXPERIMENT: Text-Only Qwen3_5ForCausalLM vs Multimodal Qwen3_5ForConditionalGeneration")
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

# 1. Test Qwen3_5ForCausalLM Loading
print("\n--- 1. Testing Qwen3_5ForCausalLM ---")
torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()
vram_pre = torch.cuda.memory_allocated() / (1024 ** 2)

t0 = time.perf_counter()
try:
    causal_model = Qwen3_5ForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map=device,
        torch_dtype=torch.bfloat16,
    )
    causal_model.eval()
    t_load_causal = time.perf_counter() - t0
    vram_alloc_causal = torch.cuda.memory_allocated() / (1024 ** 2)
    vram_res_causal = torch.cuda.memory_reserved() / (1024 ** 2)
    print(f"Loaded Qwen3_5ForCausalLM successfully in {t_load_causal:.2f}s!")
    print(f"Allocated VRAM: {vram_alloc_causal:.2f} MiB | Reserved VRAM: {vram_res_causal:.2f} MiB")

    # Module hierarchy inspection
    causal_modules = [n for n, _ in causal_model.named_modules()]
    has_visual = any("visual" in n for n in causal_modules)
    print(f"Has visual modules: {has_visual}")
    print(f"Total parameter tensors: {len(list(causal_model.parameters()))}")
    param_count = sum(p.numel() for p in causal_model.parameters())
    print(f"Total parameter count: {param_count:,}")

except Exception as e:
    print(f"FAILED to load Qwen3_5ForCausalLM: {type(e).__name__}: {e}")
    causal_model = None

# 2. Test forward pass and candidate logits on sample 0
if causal_model is not None:
    dataset = get_curated_indian_equity_dataset()
    sample = dataset[0]
    task = SentimentDivergenceTask()
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
    print(f"\nPrompt sequence length: {inputs['input_ids'].shape[1]} tokens")

    # Warmup / measurement run
    torch.cuda.synchronize()
    t_fwd0 = time.perf_counter()
    with torch.no_grad():
        out = causal_model(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"], use_cache=False)
        last_logits = out.logits[0, -1, :]
    torch.cuda.synchronize()
    fwd_latency = (time.perf_counter() - t_fwd0) * 1000.0

    peak_alloc = torch.cuda.max_memory_allocated() / (1024 ** 2)
    peak_res = torch.cuda.max_memory_reserved() / (1024 ** 2)
    print(f"Forward pass latency: {fwd_latency:.2f} ms")
    print(f"Peak VRAM during forward pass: Allocated: {peak_alloc:.2f} MiB | Reserved: {peak_res:.2f} MiB")

    # Extract candidate logits
    label_ids = {}
    logits_causal = {}
    for lbl in branch.output_labels:
        # Contextual token ID
        base_ids = tokenizer.encode(full_text, add_special_tokens=False)
        app_ids = tokenizer.encode(full_text + lbl, add_special_tokens=False)
        t_id = app_ids[-1]
        label_ids[lbl] = t_id
        logits_causal[lbl] = float(last_logits[t_id].item())
    
    print("\nCandidate Logits (Qwen3_5ForCausalLM):")
    for lbl, score in logits_causal.items():
        print(f"  ({lbl}) [token_id={label_ids[lbl]}]: {score:.4f}")

    # Compute softmax
    scores_tensor = torch.tensor([logits_causal[lbl] for lbl in branch.output_labels])
    probs = torch.softmax(scores_tensor, dim=0).tolist()
    print("\nProbabilities (Qwen3_5ForCausalLM):")
    for lbl, p in zip(branch.output_labels, probs):
        print(f"  ({lbl}): {p*100:.2f}%")

print("\n" + "=" * 70)
