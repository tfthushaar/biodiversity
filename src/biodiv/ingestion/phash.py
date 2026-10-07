"""Perceptual image hashing, for spotting duplicate frames.

dHash: shrink to 9x8 greyscale, then record whether each pixel is brighter than its right-hand
neighbour. That gives 64 bits that barely change under re-compression or resizing, so two
copies of one photo hash alike while different photos do not.

Camera-trap bursts are three frames a fraction of a second apart. They are *not* duplicates (the
animal has moved), but they are the same animal, so counting individuals needs sequence-level
handling that this module does not attempt.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

HASH_BITS = 64
_SIGN = 1 << (HASH_BITS - 1)
_MASK = (1 << HASH_BITS) - 1


def dhash(image: Image.Image) -> int:
    """64-bit difference hash as a signed int, so it fits a Postgres bigint."""
    small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    px = np.asarray(small, dtype=np.int16)  # 8 rows x 9 columns
    bits = 0
    for brighter in (px[:, :-1] > px[:, 1:]).flatten():
        bits = (bits << 1) | int(brighter)
    return bits - (1 << HASH_BITS) if bits & _SIGN else bits


def hamming(a: int, b: int) -> int:
    """Number of differing bits between two (signed) 64-bit hashes."""
    return ((a ^ b) & _MASK).bit_count()
