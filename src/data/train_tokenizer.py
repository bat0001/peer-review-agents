"""Train and save a RustBPE tokenizer from local parquet shards."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterator

from src.data.nanochat_dataset import parquets_iter_batched
from src.tokenizer import RustBPETokenizer


def _default_data_dir() -> str:
    base = os.environ.get("NANOCHAT_BASE_DIR")
    if base is None:
        raise RuntimeError("NANOCHAT_BASE_DIR environment variable not set")
    return str(Path(base) / "base_data")


def _default_tokenizer_dir() -> str:
    base = os.environ.get("NANOCHAT_BASE_DIR")
    if base is None:
        raise RuntimeError("NANOCHAT_BASE_DIR environment variable not set")
    return str(Path(base) / "tokenizer")


def iter_text(split: str, data_dir: str, max_chars: int) -> Iterator[str]:
    seen = 0
    for batch in parquets_iter_batched(split=split, data_dir=data_dir):
        for text in batch:
            if max_chars >= 0 and seen >= max_chars:
                return
            if max_chars >= 0:
                remaining = max_chars - seen
                if remaining <= 0:
                    return
                if len(text) > remaining:
                    text = text[:remaining]
            seen += len(text)
            yield text


def main() -> None:
    parser = argparse.ArgumentParser(description="Train RustBPE tokenizer from parquet text")
    parser.add_argument("--vocab-size", type=int, default=65536)
    parser.add_argument("--max-chars", type=int, default=2_000_000_000)
    parser.add_argument("--data-dir", type=str, default=None)
    parser.add_argument("--tokenizer-dir", type=str, default=None)
    parser.add_argument("--split", type=str, default="train", choices=["train", "val"])
    args = parser.parse_args()

    data_dir = args.data_dir or _default_data_dir()
    tokenizer_dir = args.tokenizer_dir or _default_tokenizer_dir()

    print(f"Training tokenizer from: {data_dir}")
    print(f"Output directory: {tokenizer_dir}")
    print(f"Vocab size: {args.vocab_size}")
    print(f"Max chars: {args.max_chars}")

    text_stream = iter_text(args.split, data_dir, args.max_chars)
    tokenizer = RustBPETokenizer.train_from_iterator(text_stream, args.vocab_size)
    tokenizer.save(tokenizer_dir)

    print("Tokenizer training complete.")


if __name__ == "__main__":
    main()
