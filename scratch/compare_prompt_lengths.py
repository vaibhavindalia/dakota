import os
import sys
sys.path.insert(0, os.path.abspath("."))

from src.intelligence.jev.dataset import get_curated_indian_equity_dataset
from src.intelligence.jev.evaluation.baselines import extract_sample_text
from src.intelligence.jev.tasks.sentiment import SentimentDivergenceTask
from src.intelligence.jev.prompt_builder import prepare_prompt
from src.intelligence.jev.schemas import ClassifierQuestion, ClassifierRequest, QuestionType, ClassifierOption
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3.5-9B")
dataset = get_curated_indian_equity_dataset()
task = SentimentDivergenceTask()

print(f"Total dataset samples: {len(dataset)}")
print(f"{'Idx':<4} | {'Ticker':<10} | {'JEV Prompt Tokens':<18} | {'Gen Prompt Tokens':<18} | {'Ratio (JEV/Gen)':<15}")
print("-" * 75)

jev_tokens_list = []
gen_tokens_list = []

for idx, s in enumerate(dataset):
    # 1. JEV Prompt Construction
    state, evidence_ids = task.build_evidence_state(s.sample)
    q = ClassifierQuestion(
        type=QuestionType.CHOICE,
        instructions=task.task_instructions,
        criteria=task.candidate_classes,
    )
    req = ClassifierRequest(
        model="Qwen/Qwen3.5-9B",
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
    jev_formatted = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    jev_text = f"{jev_formatted}{branch.answer_prefix}"
    jev_tokens = len(tokenizer.encode(jev_text))
    jev_tokens_list.append(jev_tokens)

    # 2. Generative Baseline Prompt Construction
    text = extract_sample_text(s.sample)
    classes = ["Bullish", "Bearish", "Neutral", "Mixed", "Insufficient Evidence"]
    gen_prompt = (
        f"Analyze the following Indian equity market evidence and classify the prevailing sentiment "
        f"into exactly one of the candidate classes: {', '.join(classes)}.\n\n"
        f"Context:\n{text}\n\n"
        f"Reply with the single candidate class name only:"
    )
    gen_messages = [
        {"role": "system", "content": "You are a professional financial equity analyst."},
        {"role": "user", "content": gen_prompt},
    ]
    gen_formatted = tokenizer.apply_chat_template(
        gen_messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    gen_tokens = len(tokenizer.encode(gen_formatted))
    gen_tokens_list.append(gen_tokens)

    ratio = jev_tokens / gen_tokens if gen_tokens > 0 else 0
    print(f"{idx:<4} | {s.ticker:<10} | {jev_tokens:<18} | {gen_tokens:<18} | {ratio:<15.2f}")

print("-" * 75)
print(f"Mean JEV tokens: {sum(jev_tokens_list)/len(jev_tokens_list):.1f} (min: {min(jev_tokens_list)}, max: {max(jev_tokens_list)})")
print(f"Mean Gen tokens: {sum(gen_tokens_list)/len(gen_tokens_list):.1f} (min: {min(gen_tokens_list)}, max: {max(gen_tokens_list)})")
