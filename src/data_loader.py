"""Data loader entrypoint (nanochat parquet streaming)."""

from typing import Iterator, Tuple

import torch

from src.data.nanochat_dataloader import tokenizing_distributed_data_loader


def create_data_loader(
    data_path: str,
    batch_size: int,
    seq_len: int,
    tokenizer_dir: str,
    tokenizer_threads: int = 4,
    tokenizer_batch_size: int = 128,
    split: str = "train",
    device: str | torch.device = "cuda",
) -> Iterator[Tuple[torch.Tensor, torch.Tensor]]:
    """
    Create a nanochat-style parquet data loader.
    """
    return tokenizing_distributed_data_loader(
        batch_size=batch_size,
        seq_len=seq_len,
        split=split,
        data_dir=data_path,
        tokenizer_dir=tokenizer_dir,
        tokenizer_threads=tokenizer_threads,
        tokenizer_batch_size=tokenizer_batch_size,
        device=device,
    )
