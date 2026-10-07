import io

import pytest
from PIL import Image, ImageDraw

from biodiv.ingestion.phash import HASH_BITS, dhash, hamming


def scene(seed: int = 0, size=(400, 300)) -> Image.Image:
    """A synthetic photo with structure: gradient background plus a few shapes."""
    im = Image.linear_gradient("L").resize(size).convert("RGB")
    d = ImageDraw.Draw(im)
    for i in range(6):
        x = (seed * 37 + i * 61) % (size[0] - 80)
        y = (seed * 53 + i * 41) % (size[1] - 60)
        d.rectangle([x, y, x + 70, y + 50], fill=((seed * 40 + i * 30) % 256,) * 3)
    return im


def reencode(im: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue()))


def test_hash_fits_a_signed_64_bit_integer():
    h = dhash(scene(1))
    assert -(1 << 63) <= h < (1 << 63)


def test_identical_images_hash_identically():
    assert dhash(scene(1)) == dhash(scene(1))


def test_recompression_and_resizing_barely_change_the_hash():
    original = scene(2)
    assert hamming(dhash(original), dhash(reencode(original, 40))) <= 4
    assert hamming(dhash(original), dhash(original.resize((200, 150)))) <= 4


def test_different_photos_hash_far_apart():
    distances = [hamming(dhash(scene(a)), dhash(scene(b))) for a, b in [(1, 2), (2, 3), (1, 3)]]
    assert min(distances) > 8


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [(0, 0, 0), (0b1011, 0b0010, 2), (-1, 0, HASH_BITS), (-1, -1, 0), (-(1 << 63), 0, 1)],
)
def test_hamming_handles_signed_values(a, b, expected):
    assert hamming(a, b) == expected
