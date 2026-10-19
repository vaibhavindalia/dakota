import os
import sys
import torch
from transformers import AutoConfig, AutoTokenizer

model_id = "Qwen/Qwen3.5-9B"

config = AutoConfig.from_pretrained(model_id)
print("=== CONFIG INSPECTION ===")
print(f"Model Type: {config.model_type}")
print(f"Architectures: {config.architectures}")
print(f"Hidden size: {getattr(config, 'hidden_size', None)}")
print(f"Num hidden layers: {getattr(config, 'num_hidden_layers', None)}")
print(f"Vocab size: {getattr(config, 'vocab_size', None)}")
print(f"Tie word embeddings: {getattr(config, 'tie_word_embeddings', None)}")

# If text_config exists:
if hasattr(config, "text_config"):
    tc = config.text_config
    print("\n=== TEXT CONFIG ===")
    print(f"Hidden size: {tc.hidden_size}")
    print(f"Num hidden layers: {tc.num_hidden_layers}")
    print(f"Vocab size: {tc.vocab_size}")
    print(f"Intermediate size: {tc.intermediate_size}")
    print(f"Tie word embeddings: {tc.tie_word_embeddings}")

# If vision_config exists:
if hasattr(config, "vision_config"):
    vc = config.vision_config
    print("\n=== VISION CONFIG ===")
    print(f"Depth: {getattr(vc, 'depth', None)}")
    print(f"Hidden size: {getattr(vc, 'hidden_size', None)}")

# Let's inspect safetensors metadata
import json
from pathlib import Path
cache_dir = Path(os.path.expanduser("~/.cache/huggingface/hub"))
model_dirs = list(cache_dir.glob("*Qwen*3.5*9B*"))
print(f"\nCache dirs found: {model_dirs}")

if model_dirs:
    snapshots = list(model_dirs[0].glob("snapshots/*"))
    if snapshots:
        snap = snapshots[0]
        print(f"Snapshot path: {snap}")
        index_file = snap / "model.safetensors.index.json"
        if index_file.exists():
            with open(index_file) as f:
                index_data = json.load(f)
            weight_map = index_data.get("weight_map", {})
            total_tensors = len(weight_map)
            visual_tensors = [k for k in weight_map if "visual" in k]
            llm_tensors = [k for k in weight_map if "visual" not in k]
            print(f"Total tensors in index: {total_tensors}")
            print(f"Visual tensors: {len(visual_tensors)}")
            print(f"Language model tensors: {len(llm_tensors)}")
