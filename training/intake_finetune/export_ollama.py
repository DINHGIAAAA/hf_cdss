from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export LoRA adapter instructions for Ollama.")
    parser.add_argument("--adapter-dir", type=Path, default=Path("training/output/hf-intake-lora"))
    parser.add_argument("--base-model", default="qwen2.5:7b")
    parser.add_argument("--output", type=Path, default=Path("training/output/Modelfile.hf-intake"))
    args = parser.parse_args()

    metadata_path = args.adapter_dir / "train_metadata.json"
    metadata = {}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    modelfile = f"""FROM {args.base_model}

# Merge the LoRA adapter with ollama create after exporting merged weights, or use a merged GGUF.
# Adapter directory: {args.adapter_dir}
# Training metadata: {json.dumps(metadata, ensure_ascii=False)}

PARAMETER temperature 0
PARAMETER num_ctx 4096
"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(modelfile, encoding="utf-8")
    print(f"Wrote {args.output}")
    print("Next: merge LoRA into base weights (llama.cpp/MLX) or use HF merged checkpoint, then `ollama create hf-intake -f training/output/Modelfile.hf-intake`")


if __name__ == "__main__":
    main()
