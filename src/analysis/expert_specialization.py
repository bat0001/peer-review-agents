"""Expert specialization analysis (HF GSM8K + HumanEval)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import csv
import json
import random

import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from datasets import load_dataset

from src.models.model_base import norm


def _format_gsm8k(row: dict, template: str) -> str:
    question = row["question"].strip()
    if template == "qa_prefix":
        return f"Question: {question}\nAnswer:"
    if template == "qa_full":
        answer = row["answer"].strip()
        return f"Question: {question}\nAnswer: {answer}"
    raise ValueError(f"Unsupported GSM8K template: {template}")


def _format_humaneval(row: dict, template: str) -> str:
    prompt = row["prompt"].rstrip()
    solution = row["canonical_solution"].rstrip()
    if template == "prompt_plus_solution":
        return f"{prompt}\n{solution}"
    raise ValueError(f"Unsupported HumanEval template: {template}")


def load_domain_texts_from_hf(
    hf_datasets: List[dict],
    gsm8k_template: str,
    humaneval_template: str,
) -> Tuple[Dict[str, List[str]], Dict[str, str], List[dict]]:
    """Load texts from HF datasets and return per-domain lists.

    Returns:
        domain_texts: {domain: [text, ...]}
        passage_texts: {domain: first_example_text}
        meta: list of dataset metadata dicts
    """
    domain_texts: Dict[str, List[str]] = {}
    passage_texts: Dict[str, str] = {}
    meta: List[dict] = []

    for spec in hf_datasets:
        name = spec["name"].lower()
        subset = spec.get("subset") or None
        split = spec.get("split", "train")
        domain = spec["domain"]

        if name == "gsm8k":
            ds = load_dataset("openai/gsm8k", subset, split=split)
            formatter = lambda row: _format_gsm8k(row, gsm8k_template)
        elif name == "humaneval":
            ds = load_dataset("openai/openai_humaneval", split=split)
            formatter = lambda row: _format_humaneval(row, humaneval_template)
        else:
            raise ValueError(f"Unsupported dataset name: {name}")

        if len(ds) == 0:
            raise ValueError(f"Dataset {name} split {split} is empty")

        passage_texts[domain] = formatter(ds[0])
        texts = [formatter(ds[i]) for i in range(len(ds))]
        domain_texts[domain] = texts

        meta.append({
            "name": name,
            "subset": subset,
            "split": split,
            "domain": domain,
            "num_examples": len(ds),
        })

    return domain_texts, passage_texts, meta


def tokenize_texts_to_sequences(
    tokenizer,
    texts: List[str],
    seq_len: int,
    max_sequences: int,
    seed: int,
) -> List[List[int]]:
    """Tokenize texts into fixed-length sequences (streaming concat)."""
    rng = random.Random(seed)
    texts = list(texts)
    rng.shuffle(texts)

    sequences: List[List[int]] = []
    buffer: List[int] = []
    bos_id = tokenizer.get_bos_token_id()

    for text in texts:
        ids = tokenizer.encode(text, prepend=bos_id)
        buffer.extend(ids)
        while len(buffer) >= seq_len and len(sequences) < max_sequences:
            sequences.append(buffer[:seq_len])
            buffer = buffer[seq_len:]
        if len(sequences) >= max_sequences:
            break

    return sequences


def batch_sequences(sequences: List[List[int]], batch_size: int) -> Iterable[torch.Tensor]:
    for i in range(0, len(sequences), batch_size):
        batch = sequences[i:i + batch_size]
        if not batch:
            continue
        yield torch.tensor(batch, dtype=torch.long)


def _get_router_and_cutoff(mlp):
    if hasattr(mlp, "engine") and hasattr(mlp.engine, "router"):
        router = mlp.engine.router
        cutoff = mlp.engine.cutoff_ema
        return router, cutoff
    if hasattr(mlp, "router") and hasattr(mlp, "cutoff_ema"):
        return mlp.router, mlp.cutoff_ema
    return None, None


def collect_expert_stats(
    model,
    domain_sequences: Dict[str, List[List[int]]],
    batch_size: int,
    device: torch.device,
) -> Dict[str, dict]:
    """Collect per-domain, per-layer expert selection counts (threshold routing)."""
    stats: Dict[str, dict] = {}

    for domain, sequences in domain_sequences.items():
        stats[domain] = {
            "n_sequences": len(sequences),
            "n_tokens": 0,
            "layers": {},
        }

        for batch in batch_sequences(sequences, batch_size):
            input_ids = batch.to(device)
            B, T = input_ids.shape
            n_tokens = B * T

            # Track tokens per domain
            stats[domain]["n_tokens"] += n_tokens

            # Forward with manual instrumentation
            x = model.wte(input_ids)
            x = norm(x)
            cos_sin = model.cos[:, :T], model.sin[:, :T]

            for layer_idx, block in enumerate(model.blocks):
                x = x + block.attn(norm(x), cos_sin)

                mlp_in = norm(x)
                router, cutoff = _get_router_and_cutoff(block.mlp)
                if router is not None and cutoff is not None:
                    router_logits = router(mlp_in).float()  # (B, T, E)
                    router_logits_flat = router_logits.view(-1, router_logits.shape[-1])
                    cutoff = cutoff.to(router_logits_flat.device)
                    above = router_logits_flat >= cutoff.unsqueeze(0)
                    counts = above.sum(dim=0).detach().cpu()

                    layer_key = str(layer_idx)
                    layer_stats = stats[domain]["layers"].setdefault(
                        layer_key,
                        {"expert_counts": torch.zeros_like(counts, dtype=torch.long)},
                    )
                    layer_stats["expert_counts"] += counts

                if block.mlp_needs_layer_idx:
                    mlp_out, _ = block.mlp(mlp_in, layer_idx=layer_idx)
                else:
                    mlp_out, _ = block.mlp(mlp_in)
                x = x + mlp_out

    # Finalize ratios
    for domain, dom_stats in stats.items():
        total_tokens = dom_stats["n_tokens"]
        for layer_key, layer_stats in dom_stats["layers"].items():
            counts = layer_stats["expert_counts"].to(torch.float32)
            layer_stats["expert_counts"] = counts.to(torch.long).tolist()
            if total_tokens > 0:
                layer_stats["expert_ratio"] = (counts / total_tokens).tolist()
            else:
                layer_stats["expert_ratio"] = [0.0 for _ in range(len(layer_stats["expert_counts"]))]

    return stats


def plot_expert_heatmaps(stats: Dict[str, dict], output_path: Path) -> None:
    """Plot expert selection frequency heatmaps by domain."""
    domains = sorted(stats.keys())
    if not domains:
        raise ValueError("No domains to plot")

    # Determine global max for consistent color scale
    max_val = 0.0
    for domain in domains:
        for layer_stats in stats[domain]["layers"].values():
            max_val = max(max_val, max(layer_stats.get("expert_ratio", [0.0]) or [0.0]))

    n_domains = len(domains)
    fig, axes = plt.subplots(1, n_domains, figsize=(5 * n_domains, 4), squeeze=False)

    for ax, domain in zip(axes[0], domains):
        layers = sorted(int(k) for k in stats[domain]["layers"].keys())
        if not layers:
            ax.set_title(domain)
            ax.axis("off")
            continue

        matrix = torch.tensor([
            stats[domain]["layers"][str(layer)]["expert_ratio"]
            for layer in layers
        ], dtype=torch.float32).numpy()

        im = ax.imshow(matrix, aspect="auto", vmin=0.0, vmax=max_val, cmap="Reds")
        ax.set_title(domain)
        ax.set_xlabel("Expert ID")
        ax.set_ylabel("Layer")
        ax.set_yticks(range(len(layers)))
        ax.set_yticklabels([str(l) for l in layers])

        num_experts = matrix.shape[1]
        if num_experts <= 16:
            ax.set_xticks(range(num_experts))
        else:
            step = max(1, num_experts // 8)
            ax.set_xticks(list(range(0, num_experts, step)))

        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Expert Token Ratio")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def dump_passage_fanout(
    model,
    tokenizer,
    passages: Dict[str, str],
    max_seq_len: int,
    output_path: Path,
    device: torch.device,
) -> None:
    """Dump per-token fanout for given passages (threshold routing)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "passage",
            "layer",
            "token_idx",
            "token_id",
            "token_str",
            "fanout",
            "expert_ids",
        ])

        for passage_name, text in passages.items():
            ids = tokenizer.encode(text, prepend=tokenizer.get_bos_token_id())
            ids = ids[:max_seq_len]
            input_ids = torch.tensor([ids], dtype=torch.long, device=device)
            B, T = input_ids.shape

            x = model.wte(input_ids)
            x = norm(x)
            cos_sin = model.cos[:, :T], model.sin[:, :T]

            for layer_idx, block in enumerate(model.blocks):
                x = x + block.attn(norm(x), cos_sin)
                mlp_in = norm(x)
                router, cutoff = _get_router_and_cutoff(block.mlp)
                if router is not None and cutoff is not None:
                    router_logits = router(mlp_in).float()
                    router_logits_flat = router_logits.view(-1, router_logits.shape[-1])
                    cutoff = cutoff.to(router_logits_flat.device)
                    above = router_logits_flat >= cutoff.unsqueeze(0)
                    fanout = above.sum(dim=1).cpu()

                    for token_idx, token_id in enumerate(ids):
                        token_str = tokenizer.id_to_token(token_id)
                        expert_ids = torch.nonzero(above[token_idx], as_tuple=False).view(-1).cpu().tolist()
                        expert_ids_str = " ".join(str(eid) for eid in expert_ids)
                        writer.writerow([
                            passage_name,
                            layer_idx,
                            token_idx,
                            token_id,
                            token_str,
                            int(fanout[token_idx].item()),
                            expert_ids_str,
                        ])

                if block.mlp_needs_layer_idx:
                    mlp_out, _ = block.mlp(mlp_in, layer_idx=layer_idx)
                else:
                    mlp_out, _ = block.mlp(mlp_in)
                x = x + mlp_out


def save_metrics_json(output_path: Path, meta: dict, stats: Dict[str, dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "domains": stats}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
