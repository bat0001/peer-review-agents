"""
Parquet dataset download and iteration utilities.

Provenance:
- Adapted from nanochat dataset utilities for FineWeb parquet shards:
  https://github.com/karpathy/nanochat
- Modified for local config/environment conventions used by this repo.
"""

from __future__ import annotations

import argparse
import os
import time
from multiprocessing import Pool
from pathlib import Path

import requests
import pyarrow.parquet as pq

BASE_URL = "https://huggingface.co/datasets/karpathy/fineweb-edu-100b-shuffle/resolve/main"
MAX_SHARD = 1822


def index_to_filename(index: int) -> str:
    return f"shard_{index:05d}.parquet"


def _resolve_data_dir(data_dir: str | None) -> Path:
    if data_dir:
        return Path(data_dir)
    env_val = os.environ.get("NANOCHAT_BASE_DIR")
    if env_val is None:
        raise RuntimeError("NANOCHAT_BASE_DIR environment variable not set")
    return Path(env_val) / "base_data"


def list_parquet_files(data_dir: str | None = None) -> list[str]:
    data_dir_path = _resolve_data_dir(data_dir)
    if not data_dir_path.exists():
        raise FileNotFoundError(f"Data path does not exist: {data_dir_path}")
    parquet_files = sorted(
        f for f in os.listdir(data_dir_path)
        if f.endswith(".parquet") and not f.endswith(".tmp")
    )
    return [str(data_dir_path / f) for f in parquet_files]


def parquets_iter_batched(
    split: str,
    start: int = 0,
    step: int = 1,
    data_dir: str | None = None,
) -> Iterable[list[str]]:
    """
    Iterate through the dataset in row-group batches.

    Args:
        split: "train" or "val" (last parquet is val)
        start: start index for row-group stride (e.g. rank)
        step: stride size (e.g. world_size)
        data_dir: directory containing parquet shards
    """
    if split not in {"train", "val"}:
        raise ValueError("split must be 'train' or 'val'")

    parquet_paths = list_parquet_files(data_dir)
    if not parquet_paths:
        raise FileNotFoundError("No parquet files found")
    parquet_paths = parquet_paths[:-1] if split == "train" else parquet_paths[-1:]

    for filepath in parquet_paths:
        pf = pq.ParquetFile(filepath)
        for rg_idx in range(start, pf.num_row_groups, step):
            rg = pf.read_row_group(rg_idx)
            texts = rg.column("text").to_pylist()
            yield texts


def download_single_file(index: int, data_dir: str | None = None) -> bool:
    data_dir_path = _resolve_data_dir(data_dir)
    data_dir_path.mkdir(parents=True, exist_ok=True)

    filename = index_to_filename(index)
    filepath = data_dir_path / filename
    if filepath.exists():
        print(f"Skipping {filepath} (already exists)")
        return True

    url = f"{BASE_URL}/{filename}"
    print(f"Downloading {filename}...")

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            temp_path = filepath.with_suffix(filepath.suffix + ".tmp")
            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            temp_path.rename(filepath)
            print(f"Successfully downloaded {filename}")
            return True
        except (requests.RequestException, OSError) as exc:
            print(f"Attempt {attempt}/{max_attempts} failed for {filename}: {exc}")
            for path in (temp_path if "temp_path" in locals() else None, filepath):
                if path is not None and path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        pass
            if attempt < max_attempts:
                wait_time = 2 ** attempt
                print(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print(f"Failed to download {filename} after {max_attempts} attempts")
                return False

    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download FineWeb-Edu 100B parquet shards")
    parser.add_argument(
        "-n",
        "--num-files",
        type=int,
        default=-1,
        help="Number of shards to download (-1 = all)",
    )
    parser.add_argument(
        "-w",
        "--num-workers",
        type=int,
        default=4,
        help="Number of parallel download workers",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Directory to store parquet shards",
    )
    args = parser.parse_args()

    data_dir = _resolve_data_dir(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    num = MAX_SHARD + 1 if args.num_files == -1 else min(args.num_files, MAX_SHARD + 1)
    ids_to_download = list(range(num))
    print(f"Downloading {len(ids_to_download)} shards using {args.num_workers} workers...")
    print(f"Target directory: {data_dir}")
    print()
    with Pool(processes=args.num_workers) as pool:
        results = pool.starmap(download_single_file, [(idx, str(data_dir)) for idx in ids_to_download])

    successful = sum(1 for success in results if success)
    print(f"Done! Downloaded: {successful}/{len(ids_to_download)} shards to {data_dir}")
