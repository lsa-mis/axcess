"""Images sent to a local model: no larger than the model needs.

A vision model splits an image into pieces it reads one by one, so the time
an answer takes grows with the pixel count. A 1536 x 1024 infographic took
Bonsai-2-9B about 163 s on integrated graphics and ran past the 2-minute
limit for a fix suggestion (end-to-end test, 2026-11-17). At most 1024 px
on the longer side keeps text in a screenshot or infographic legible while
sending about 2.3 times fewer pieces.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

MAX_SIDE = 1024


def fit_for_model(data: bytes, max_side: int = MAX_SIDE) -> tuple[bytes, str | None]:
    """The image, scaled down to ``max_side`` if larger, and its MIME type.

    Unchanged (with no type) when it cannot be read as an image: the model
    service then decides, as before.
    """
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = (im.format or "").upper()
            if max(im.size) <= max_side:
                return data, Image.MIME.get(fmt)
            im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            if im.mode in ("RGBA", "LA", "P"):
                im.convert("RGBA").save(out, format="PNG")
                return out.getvalue(), "image/png"
            im.convert("RGB").save(out, format="JPEG", quality=90)
            return out.getvalue(), "image/jpeg"
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return data, None
