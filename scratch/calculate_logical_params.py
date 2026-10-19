import os
import json
from pathlib import Path
from safetensors import safe_open

snap = Path(r"C:\Users\vdish\.cache\huggingface\hub\models--Qwen--Qwen3.5-9B\snapshots\c202236235762e1c871ad0ccb60c8ee5ba337b9a")
index_file = snap / "model.safetensors.index.json"

with open(index_file) as f:
    data = json.load(f)

weight_map = data["weight_map"]

# Collect tensor shapes across all shard files
safetensor_files = set(weight_map.values())
tensor_shapes = {}

for sf in safetensor_files:
    file_path = snap / sf
    with safe_open(str(file_path), framework="pt") as f:
        for k in f.keys():
            tensor_shapes[k] = f.get_slice(k).get_shape()

total_logical_params = 0
llm_logical_params = 0
visual_logical_params = 0

embed_params = 0
lm_head_params = 0

for k, shape in tensor_shapes.items():
    n_params = 1
    for dim in shape:
        n_params *= dim
    
    total_logical_params += n_params
    if "visual" in k:
        visual_logical_params += n_params
    else:
        llm_logical_params += n_params
        if "embed_tokens" in k:
            embed_params += n_params
        elif "lm_head" in k:
            lm_head_params += n_params

print("=" * 60)
print("EXACT LOGICAL PARAMETER BREAKDOWN (UNQUANTIZED):")
print("=" * 60)
print(f"Total Logical Parameters: {total_logical_params:,} ({total_logical_params / 1e9:.3f}B)")
print(f"Language Model Logical Parameters: {llm_logical_params:,} ({llm_logical_params / 1e9:.3f}B)")
print(f"Vision Model Logical Parameters: {visual_logical_params:,} ({visual_logical_params / 1e9:.3f}B)")
print(f"  - embed_tokens: {embed_params:,} ({embed_params / 1e9:.3f}B)")
print(f"  - lm_head: {lm_head_params:,} ({lm_head_params / 1e9:.3f}B)")
print(f"  - Layers/Norms/MLP: {llm_logical_params - embed_params - lm_head_params:,} ({(llm_logical_params - embed_params - lm_head_params) / 1e9:.3f}B)")
print("=" * 60)
print("EXPLANATION OF 5.49B REPORTED IN PHASE 2D:")
print("In BitsAndBytes 4-bit NF4, linear weights are packed as uint8 (2 weights per byte).")
print(f"Packed linear layers: {(llm_logical_params - embed_params - lm_head_params) / 2:,} params")
print(f"Non-packed BF16 (embed + lm_head): {embed_params + lm_head_params:,} params")
packed_sum = (llm_logical_params - embed_params - lm_head_params) / 2 + embed_params + lm_head_params
print(f"Sum of packed tensor numel(): {packed_sum:,} ({packed_sum / 1e9:.3f}B)")
print("=" * 60)
