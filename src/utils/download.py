"""Download helpers with file locking."""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from filelock import FileLock


def resolve_base_dir(base_dir: str | None = None) -> Path:
    if base_dir:
        root = Path(base_dir)
    else:
        env_val = os.environ.get("NANOCHAT_BASE_DIR")
        if env_val is None:
            raise RuntimeError("NANOCHAT_BASE_DIR environment variable not set")
        root = Path(env_val)
    root.mkdir(parents=True, exist_ok=True)
    return root


def download_file_with_lock(
    url: str,
    filename: str,
    postprocess_fn: Optional[Callable[[str], None]] = None,
    base_dir: str | None = None,
) -> str:
    base_dir_path = resolve_base_dir(base_dir)
    file_path = base_dir_path / filename
    lock_path = str(file_path) + ".lock"

    if file_path.exists():
        return str(file_path)

    with FileLock(lock_path):
        if file_path.exists():
            return str(file_path)

        with urllib.request.urlopen(url) as response:
            content = response.read()

        with open(file_path, "wb") as f:
            f.write(content)

        if postprocess_fn is not None:
            postprocess_fn(str(file_path))

    return str(file_path)
