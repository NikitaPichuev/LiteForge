from __future__ import annotations

import os
import pathlib


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
KEYS_FILE = PROJECT_ROOT / "keys.txt"


def read_key_lines(path: pathlib.Path = KEYS_FILE) -> list[str]:
    if not path.exists():
        raise RuntimeError(f"{path.name} not found")

    keys: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        keys.append(line if line.startswith("0x") else "0x" + line)

    if not keys:
        raise RuntimeError(f"{path.name} is empty")
    return keys


def get_active_key_index() -> int:
    raw = os.environ.get("KEY_INDEX", "1").strip()
    try:
        index = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid KEY_INDEX: {raw}") from exc
    if index < 1:
        raise RuntimeError(f"KEY_INDEX must be >= 1, got {index}")
    return index


def read_private_key() -> str:
    keys = read_key_lines()
    index = get_active_key_index()
    if index > len(keys):
        raise RuntimeError(f"KEY_INDEX={index} is out of range for keys.txt with {len(keys)} keys.")
    return keys[index - 1]
