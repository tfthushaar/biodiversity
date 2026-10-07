"""Reading an uploaded image safely. The upload endpoint is open to the public internet, so every
property of the file is untrusted: its declared type, its size, and what is actually inside."""

from __future__ import annotations

import io
import warnings

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

# A small file can claim to be enormous once decoded (a "decompression bomb"). Pillow warns above
# this many pixels and refuses above twice as many; we treat the warning as an error too.
Image.MAX_IMAGE_PIXELS = 50_000_000


def read_image(upload: UploadFile, max_bytes: int) -> Image.Image:
    if upload.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"Unsupported file type {upload.content_type!r}; "
                                 "send a JPEG, PNG or WebP image.")
    data = upload.file.read(max_bytes + 1)  # never read more than the limit allows
    if len(data) > max_bytes:
        raise HTTPException(413, f"Image is larger than {max_bytes // (1024 * 1024)} MB.")
    if not data:
        raise HTTPException(400, "The file is empty.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            image.load()  # decode fully now, so a truncated or corrupt file fails here
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, SyntaxError, ValueError):
        raise HTTPException(400, "That file is not a readable image.") from None
    return image.convert("RGB")
