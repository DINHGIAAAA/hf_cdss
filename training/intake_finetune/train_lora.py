from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def format_chat_text(messages: list[dict]) -> str:
    chunks: list[str] = []
    for message in messages:
        role = message["role"].upper()
        chunks.append(f"<|im_start|>{role}\n{message['content']}")
    chunks.append("<|im_start|>assistant\n")
    return "\n".join(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="LoRA fine-tune Qwen2.5 for clinical intake JSON extraction.")
    parser.add_argument("--dataset", type=Path, default=Path("training/data/intake_sft.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("training/output/hf-intake-lora"))
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--eval-fraction", type=float, default=0.1, help="Hold-out fraction for eval metrics")
    parser.add_argument("--bf16", action="store_true", help="Use bf16 when CUDA is available")
    args = parser.parse_args()

    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from trl import SFTTrainer
    except ImportError as exc:
        raise SystemExit(
            "Training dependencies missing. Install with: pip install -r training/requirements.txt"
        ) from exc

    if not args.dataset.exists():
        raise SystemExit(f"Dataset not found: {args.dataset}. Run build_dataset.py first.")

    rows = load_jsonl(args.dataset)
    split_index = max(1, int(len(rows) * (1 - max(0.0, min(args.eval_fraction, 0.5)))))
    train_rows = rows[:split_index]
    eval_rows = rows[split_index:] if split_index < len(rows) else []

    train_dataset = Dataset.from_list(
        [{"text": format_chat_text(row["messages"])} for row in train_rows]
    )
    eval_dataset = (
        Dataset.from_list([{"text": format_chat_text(row["messages"])} for row in eval_rows])
        if eval_rows
        else None
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_kwargs: dict = {"trust_remote_code": True}
    if torch.cuda.is_available():
        model_kwargs["torch_dtype"] = torch.bfloat16 if args.bf16 else torch.float16
        model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(args.base_model, **model_kwargs)
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora_config)

    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        logging_steps=10,
        save_steps=100,
        save_total_limit=2,
        report_to=[],
        evaluation_strategy="steps" if eval_dataset is not None else "no",
        eval_steps=50 if eval_dataset is not None else None,
        bf16=args.bf16 and torch.cuda.is_available(),
        fp16=not args.bf16 and torch.cuda.is_available(),
        remove_unused_columns=False,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        args=training_args,
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        packing=False,
    )
    trainer.train()
    trainer.model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    metadata = {
        "base_model": args.base_model,
        "dataset": str(args.dataset),
        "records": len(rows),
        "train_records": len(train_rows),
        "eval_records": len(eval_rows),
        "eval_fraction": args.eval_fraction,
        "output_dir": str(args.output_dir),
    }
    (args.output_dir / "train_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
