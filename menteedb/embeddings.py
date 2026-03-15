from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np


@dataclass
class HashingEmbedder:
    """Deterministic local embedder based on hashing.

    This keeps the library dependency-light and fully offline.
    """

    dimension: int = 384

    def encode(self, text: str) -> np.ndarray:
        if not isinstance(text, str):
            raise TypeError("Embedding input must be a string.")

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], byteorder="big", signed=False)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(self.dimension, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm == 0:
            return vec
        return vec / norm
