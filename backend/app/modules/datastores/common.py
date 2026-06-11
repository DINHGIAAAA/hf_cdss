import hashlib
import math
import re
from pathlib import Path
from typing import Any


DATA_ROOT = Path(__file__).resolve().parents[4] / "data" / "heart_failure"
ARTIFACT_ROOT = DATA_ROOT / "artifacts"
CHUNKS_PATH = ARTIFACT_ROOT / "chunks" / "chunks.jsonl"
RELATIONSHIPS_PATH = ARTIFACT_ROOT / "relationships" / "relationships.jsonl"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    import json

    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def hashing_embedding(text: str, dimensions: int = 384) -> list[float]:
    """Create a deterministic local embedding without downloading another model."""
    vector = [0.0] * dimensions
    tokens = re.findall(r"[a-z0-9+]+", text.lower())
    features = tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:])]

    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]

