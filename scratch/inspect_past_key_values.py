import os
import sys
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

inputs = tokenizer("Hello world, this is a test prefix.", return_tensors="pt").to(device)
with torch.no_grad():
    out = model(input_ids=inputs["input_ids"], use_cache=True)

past_kv = out.past_key_values
print(f"Type of past_key_values: {type(past_kv)}")
if hasattr(past_kv, "key_cache"):
    print(f"Key cache length: {len(past_kv.key_cache)}")
    print(f"Key cache[0] shape: {past_kv.key_cache[0].shape if past_kv.key_cache[0] is not None else None}")

# Check if there are delta net states or conv states
print(f"Attributes on past_kv: {dir(past_kv)}")
if hasattr(past_kv, "recurrent_state"):
    print(f"Has recurrent_state!")
