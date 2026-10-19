import os
import sys
import torch
import transformers
from transformers import AutoConfig

print(f"Transformers version: {transformers.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")

# Inspect Qwen3_5 classes
try:
    from transformers import Qwen3_5ForCausalLM
    print("Found Qwen3_5ForCausalLM in transformers!")
except ImportError:
    print("Qwen3_5ForCausalLM NOT in top-level transformers.")

try:
    from transformers.models.qwen3_5 import modeling_qwen3_5
    attrs = [a for a in dir(modeling_qwen3_5) if "Qwen" in a]
    print(f"Qwen classes in modeling_qwen3_5: {attrs}")
except Exception as e:
    print(f"Error inspecting modeling_qwen3_5: {e}")

# Inspect config
config = AutoConfig.from_pretrained("Qwen/Qwen3.5-9B")
print(f"Config architectures: {getattr(config, 'architectures', None)}")
print(f"Config model_type: {getattr(config, 'model_type', None)}")
