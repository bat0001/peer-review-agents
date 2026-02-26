"""Streaming parquet text loader with on-the-fly tokenization.

Provenance:
- Loading/tokenization flow is adapted from nanochat dataloader patterns:
  https://github.com/karpathy/nanochat
- Modified for this repo's distributed helpers and config surface.
"""

from __future__ import annotations

from collections import deque
from typing import Iterator, Tuple

import torch

from src.data.nanochat_dataset import parquets_iter_batched
from src.tokenizer import get_tokenizer
from src.utils.distributed import get_dist_info


def tokenizing_distributed_data_loader(
    batch_size: int,
    seq_len: int,
    split: str,
    data_dir: str,
    tokenizer_dir: str,
    tokenizer_threads: int = 4,
    tokenizer_batch_size: int = 128,
    device: str | torch.device = "cuda",
) -> Iterator[Tuple[torch.Tensor, torch.Tensor]]:
    """
    Stream parquet text, tokenize, and yield (inputs, targets) batches.
    """
    if split not in {"train", "val"}:
        raise ValueError("split must be 'train' or 'val'")

    _ddp, ddp_rank, _local_rank, ddp_world_size = get_dist_info()

    def document_batches():
        while True:
            for batch in parquets_iter_batched(
                split=split,
                start=ddp_rank,
                step=ddp_world_size,
                data_dir=data_dir,
            ):
                yield batch

    batches = document_batches()

    needed_tokens = batch_size * seq_len + 1
    tokenizer = get_tokenizer(tokenizer_dir)
    bos_token = tokenizer.get_bos_token_id()

    device = torch.device(device)
    use_cuda_optimizations = device.type == "cuda"

    token_buffer = deque()

    while True:
        while len(token_buffer) < needed_tokens:
            doc_batch = next(batches)
            for i in range(0, len(doc_batch), tokenizer_batch_size):
                token_lists = tokenizer.encode(
                    doc_batch[i:i + tokenizer_batch_size],
                    prepend=bos_token,
                    num_threads=tokenizer_threads,
                )
                for tokens in token_lists:
                    token_buffer.extend(tokens)

        tokens = [token_buffer.popleft() for _ in range(needed_tokens)]
        scratch = torch.tensor(tokens, dtype=torch.long, pin_memory=use_cuda_optimizations)
        inputs = scratch[:-1].view(batch_size, seq_len).to(device=device, non_blocking=use_cuda_optimizations)
        targets = scratch[1:].view(batch_size, seq_len).to(device=device, non_blocking=use_cuda_optimizations)
        yield inputs, targets
