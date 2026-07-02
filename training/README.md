# Phase 1 — Clinical intake LoRA (n2c2 + MIMIC-IV demo)

Fine-tune `Qwen2.5-7B-Instruct` for JSON clinical intake using **real** datasets only.

## Prerequisites

1. **n2c2 2018 Track 2** (medication + ADE) — register at [n2c2 DBMI portal](https://n2c2.dbmi.hms.harvard.edu/data-sets) and download text + `.ann` files.
2. **MIMIC-IV Demo** — register at [PhysioNet](https://physionet.org/content/mimiciv/2.2/), download and extract `mimic-iv-clinical-database-demo-2.2/hosp/`.

Do **not** commit raw data to git. Place under `training/data/raw/`.

## Setup

```bash
python -m venv .venv-train
.venv-train\Scripts\activate   # Windows
pip install -r training/requirements.txt
pip install -r backend/requirements.txt
```

## 1. Build SFT JSONL

```bash
set PYTHONPATH=%CD%;%CD%\backend

python training/intake_finetune/build_dataset.py ^
  --n2c2-dir training/data/raw/n2c2_2018_track2 ^
  --mimic-hosp-dir training/data/raw/mimic-iv-demo/hosp ^
  --output training/data/intake_sft.jsonl
```

Fixture-only smoke test (no credentials):

```bash
python training/intake_finetune/build_dataset.py ^
  --n2c2-dir training/intake_finetune/fixtures/n2c2 ^
  --mimic-hosp-dir training/intake_finetune/fixtures/mimic_demo/hosp ^
  --output training/data/intake_sft_fixture.jsonl
```

## 2. LoRA train (GPU recommended)

```bash
python training/intake_finetune/train_lora.py ^
  --dataset training/data/intake_sft.jsonl ^
  --output-dir training/output/hf-intake-lora ^
  --base-model Qwen/Qwen2.5-7B-Instruct ^
  --epochs 1 ^
  --batch-size 1 ^
  --gradient-accumulation 8 ^
  --bf16
```

## 3. Deploy to Ollama

1. Merge LoRA adapter into base weights (HF `merge_and_unload` or export GGUF).
2. Generate helper Modelfile:

```bash
python training/intake_finetune/export_ollama.py
```

3. Point backend to the new model:

```env
HF_CDSS_LLM_MODEL=hf-intake
```

## Tests

```bash
set PYTHONPATH=%CD%
pytest training/tests -q
```

## Output schema

Matches `backend/app/prompts/clinical_intake.py` and `PatientProfile` intake JSON used in production.
