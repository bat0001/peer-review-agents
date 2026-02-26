#!/usr/bin/env python3
"""Expert specialization analysis (GSM8K + HumanEval)."""

import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

import hydra
from omegaconf import DictConfig, OmegaConf
import torch

from src.config import Config
from src.models import BaseGPT, ModelConfig
from src.tokenizer import get_tokenizer
from src.utils.distributed import compute_init, compute_cleanup, print0
from src.analysis.expert_specialization import (
    load_domain_texts_from_hf,
    tokenize_texts_to_sequences,
    collect_expert_stats,
    plot_expert_heatmaps,
    dump_passage_fanout,
    save_metrics_json,
)


def load_checkpoint_model(checkpoint_path: str, device: torch.device):
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    if "config" not in checkpoint:
        raise ValueError("Checkpoint missing config")

    config = Config.from_dict(checkpoint["config"])

    # Force single-GPU analysis (no EP)
    config.model["expert_parallel"] = False

    tokenizer = get_tokenizer(config.data.tokenizer_dir)
    config.model["vocab_size"] = tokenizer.get_vocab_size()

    model_config = ModelConfig(**config.model)
    model = BaseGPT(model_config)

    state_dict = checkpoint["model_state_dict"]
    model.load_state_dict(state_dict, strict=True)
    model.to(device)
    model.eval()

    return model, tokenizer, config


@hydra.main(version_base=None, config_path="configs", config_name="config")
def main(cfg: DictConfig) -> None:
    config_dict = OmegaConf.to_container(cfg, resolve=True)
    analysis_cfg = config_dict.pop("analysis", None)
    if analysis_cfg is None:
        raise ValueError("analysis config required: +analysis=expert_specialization")

    config = Config.from_dict(config_dict)

    if not analysis_cfg.get("checkpoint_path"):
        raise ValueError("analysis.checkpoint_path must be set")
    checkpoint_path = Path(analysis_cfg["checkpoint_path"])
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    ddp, rank, local_rank, world_size, device = compute_init(
        seed=config.training.seed,
        expert_parallel=False,
    )
    if ddp:
        raise RuntimeError("Single-GPU only: do not launch with torchrun")

    try:
        model, tokenizer, _ = load_checkpoint_model(str(checkpoint_path), device)

        if analysis_cfg["sequence_length"] > model.config.block_size:
            raise ValueError(
                f"sequence_length ({analysis_cfg['sequence_length']}) exceeds model block_size ({model.config.block_size})"
            )

        # Load datasets
        domain_texts, passage_texts, dataset_meta = load_domain_texts_from_hf(
            analysis_cfg["hf_datasets"],
            analysis_cfg["gsm8k_template"],
            analysis_cfg["humaneval_template"],
        )

        # Tokenize to sequences per domain
        domain_sequences = {}
        for domain, texts in domain_texts.items():
            sequences = tokenize_texts_to_sequences(
                tokenizer=tokenizer,
                texts=texts,
                seq_len=analysis_cfg["sequence_length"],
                max_sequences=analysis_cfg["max_sequences_per_domain"],
                seed=analysis_cfg["seed"],
            )
            domain_sequences[domain] = sequences

        # Collect stats
        autocast_ctx = torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16)
        with torch.no_grad(), autocast_ctx:
            stats = collect_expert_stats(
                model=model,
                domain_sequences=domain_sequences,
                batch_size=analysis_cfg["batch_size"],
                device=device,
            )

        output_dir = Path(analysis_cfg["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save metrics JSON
        # Infer routed expert count from first domain/layer if available
        n_routed_experts = None
        for dom_stats in stats.values():
            if dom_stats["layers"]:
                first_layer = sorted(dom_stats["layers"].keys())[0]
                n_routed_experts = len(dom_stats["layers"][first_layer]["expert_counts"])
                break

        meta = {
            "checkpoint_path": str(checkpoint_path),
            "gsm8k_template": analysis_cfg["gsm8k_template"],
            "humaneval_template": analysis_cfg["humaneval_template"],
            "sequence_length": analysis_cfg["sequence_length"],
            "batch_size": analysis_cfg["batch_size"],
            "max_sequences_per_domain": analysis_cfg["max_sequences_per_domain"],
            "datasets": dataset_meta,
            "n_layers": model.config.n_layer,
            "n_routed_experts": n_routed_experts,
        }
        save_metrics_json(output_dir / "metrics.json", meta, stats)

        # Plot heatmaps
        plot_expert_heatmaps(stats, output_dir / "expert_heatmaps.png")

        # Passage fanout
        if analysis_cfg.get("dump_passage_fanout", False):
            with torch.no_grad(), autocast_ctx:
                dump_passage_fanout(
                    model=model,
                    tokenizer=tokenizer,
                    passages={
                        "gsm8k_0": passage_texts.get("math", ""),
                        "humaneval_0": passage_texts.get("code", ""),
                    },
                    max_seq_len=analysis_cfg["sequence_length"],
                    output_path=output_dir / "passage_fanout.csv",
                    device=device,
                )

        print0(f"Saved analysis outputs to {output_dir}")

    finally:
        compute_cleanup()


if __name__ == "__main__":
    main()
