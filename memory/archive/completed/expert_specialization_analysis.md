# Plan: Expert Specialization Analysis (prefill-only, single GPU)

## Status: Completed (2026-01-26)

Implemented analysis script + config and ran on EC_shared and GEC_shared checkpoints.

### Runs
- EC_shared: `outputs/expert_specialization_ec_shared_step100/`
- GEC_shared: `outputs/expert_specialization_gec_shared_step100/`

### SLURM helper
- `script/expert_specialization_eval.slurm` (1 GPU, installs datasets, prefetches GSM8K+HumanEval, runs analysis)
- Run list aliases included in the SLURM script:
  - `gec_shared_warmup`
  - `ec_shared_bsz2k`
  - `ec_shared_bsz8k`
  - `ec_shared_bsz64k`
  - `ec_shared_bsz512k`

### Datasets + Templates
- GSM8K: `Question: {question}\nAnswer:`
- HumanEval: `{prompt}\n{canonical_solution}`

## Goals
- Produce a figure similar to Global LBL **panel (b) only**: expert selection frequency heatmaps by domain.
- Run **prefill-only** on a **single GPU** using a **trained checkpoint** (no training loop, no decoding).
- Optionally dump a short, human-readable report showing which tokens trigger more experts (fanout) in a passage.

## Constraints / Requirements
- **No EP / single GPU**: enforce `expert_parallel=false` and avoid distributed init.
- **Prefill only**: use forward passes; never call `generate`.
- **Checkpoint-based**: load weights from an existing checkpoint.
- **Domain labels**: CORE eval does **not** provide domain categories; we need explicit domain-labeled data or heuristics.

## Data decision points (updated)
1. Use **HF datasets**: GSM8K (math) and HumanEval (code) only.
2. Passage fanout: use the **first example** from GSM8K and HumanEval as the two passages.
3. Template choice:
   - GSM8K: plain text (no chat template); likely `Question: ...\nAnswer:` or just the question.
   - HumanEval: use the dataset `prompt` field (function signature + docstring), no chat template.
4. This requires adding the **`datasets`** dependency and downloading datasets at runtime.

---

## Implementation Plan

### 1) Add analysis config (new)
**File:** `configs/analysis/expert_specialization.yaml`

Purpose: keep analysis settings out of training config. We’ll pass `+analysis=expert_specialization` on the CLI so no defaults change.

**Planned content (snippet):**
```yaml
# @package analysis
name: expert_specialization
checkpoint_path: null
output_dir: "./outputs/expert_specialization"

# routing stats
# threshold only (inference-style); no config knob

# dataset inputs (HF datasets)
hf_datasets:
  - name: gsm8k
    subset: main
    split: train
    domain: math
  - name: humaneval
    subset: null
    split: test
    domain: code

# templates
gsm8k_template: "qa_prefix"       # fixed: "Question: {question}\nAnswer:"
humaneval_template: "prompt_plus_solution" # fixed: "{prompt}\n{canonical_solution}"

# passage fanout (first example from each dataset)
dump_passage_fanout: true

# sampling / batching
max_sequences_per_domain: 512
sequence_length: 1024
batch_size: 4
seed: 1234

# plotting
save_json: true
save_plots: true
```

### 2) Add analysis module (new)
**File:** `src/analysis/expert_specialization.py`

Purpose: reusable functions for loading domain data, collecting routing stats, and plotting.

**Key functions (snippet):**
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Iterable
import json
import re
import torch
import matplotlib.pyplot as plt

from src.models.router_utils import apply_router_activation

@dataclass
class DomainBatch:
    domain: str
    input_ids: torch.Tensor  # (B, T)


def iter_domain_texts_from_hf(hf_datasets, gsm8k_template, humaneval_template):
    # yields (domain, text)
    ...


def tokenize_and_chunk(tokenizer, texts: List[str], seq_len: int) -> Iterable[torch.Tensor]:
    # chunk into fixed-length input_ids batches
    ...


def get_router_handles(mlp):
    # Return router module + cutoff_ema + n_experts for GEC/EC variants
    ...


def compute_layer_stats(x, mlp, layer_idx):
    # x: (B, T, C) input to MLP (already pre-norm)
    # Returns: counts per expert
    ...


def collect_stats(model, tokenizer, domain_batches):
    # Manual forward loop per batch to get per-layer stats
    # returns dict: stats[domain][layer]['expert_counts'] accumulators
    ...


def plot_expert_heatmaps(expert_ratio_by_domain, out_path):
    ...
```

Notes:
- **No changes to model code**: we’ll compute router logits inside `compute_layer_stats` using the router module from each MLP.
- Routing mode is **fixed to threshold** (matches inference path). No other modes will be supported.

### 3) Add analysis entrypoint (new)
**File:** `script/expert_specialization.py`

Purpose: load checkpoint + run analysis + save plots.

**Planned structure (snippet):**
```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import hydra
from omegaconf import DictConfig, OmegaConf
import torch

from src.config import Config
from src.models import BaseGPT, ModelConfig
from src.tokenizer import get_tokenizer
from src.utils.distributed import compute_init, compute_cleanup, print0
from src.analysis.expert_specialization import (
    iter_domain_texts, tokenize_and_chunk, collect_stats,
    plot_expert_heatmaps,
)

# (copy of load_checkpoint_model from script/eval_core.py to keep scope local)

def load_checkpoint_model(checkpoint_path: str, device: torch.device):
    ...

@hydra.main(version_base=None, config_path="../configs", config_name="config")
def main(cfg: DictConfig):
    cfg_dict = OmegaConf.to_container(cfg, resolve=True)
    analysis_cfg = cfg_dict.pop("analysis", None)
    if analysis_cfg is None:
        raise ValueError("analysis config required: +analysis=expert_specialization")

    config = Config.from_dict(cfg_dict)
    if config.model.get("expert_parallel", False):
        raise ValueError("expert_parallel must be false for this analysis")

    ddp, rank, local_rank, world_size, device = compute_init(
        seed=config.training.seed,
        expert_parallel=False,
    )
    if ddp:
        raise RuntimeError("Single-GPU only: do not launch with torchrun")

    model, tokenizer, _ = load_checkpoint_model(analysis_cfg["checkpoint_path"], device)
    model.eval()

    # build domain batches
    domain_texts = list(iter_domain_texts_from_hf(
        analysis_cfg["hf_datasets"],
        analysis_cfg["gsm8k_template"],
        analysis_cfg["humaneval_template"],
    ))
    ...

    with torch.no_grad(), torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
        stats = collect_stats(...)

    # save JSON + heatmap plot
    ...

if __name__ == "__main__":
    main()
```

### 4) (Optional) token fanout inspection for a passage
- Add a small helper in `src/analysis/expert_specialization.py`:
  - Input: `text`, `tokenizer`, `model`
  - Output: list of `(token_str, fanout, expert_ids)` or a CSV file.
- This can answer: “which tokens get more experts?” by simple regex tags (digit-heavy, operator-heavy, Chinese).

**Snippet idea:**
```python
def dump_token_fanout(text, model, tokenizer, out_path):
    # tokenize to input_ids
    # run one forward pass, capture per-token fanout from threshold mask
    # decode tokens and write a table (token, fanout, flags)
    ...
```

### 5) Outputs
- `outputs/expert_specialization/metrics.json` (per-domain, per-layer counts, totals)
- `outputs/expert_specialization/expert_heatmaps.png` (multi-panel)
- Optional: `outputs/expert_specialization/passage_fanout.csv`

### 6) Run instructions (single GPU)
- Check GPU is idle: `nvidia-smi`.
- Ensure `NANOCHAT_BASE_DIR` is set (tokenizer + eval bundle paths).
- Example run:
  ```bash
  /data2/hanchi/miniconda3/envs/nanochat/bin/python \
    -m script.expert_specialization \
    +analysis=expert_specialization \
    analysis.checkpoint_path=/data2/.../checkpoint.pt
  ```

---

## Confirmed choices
- Datasets: **GSM8K** (math) + **HumanEval** (code) via HF `datasets`.
- Routing: **threshold only**, no knobs.
- Passage fanout: **first example** from GSM8K + HumanEval.
- Templates:
  - GSM8K: `Question: ...\nAnswer:` (no solution text)
  - HumanEval: `prompt` + "\n" + `canonical_solution`
- Figure: **panel (b) only** (expert selection frequency heatmap).
