"""Bridge APIs removed by Pillow 10 for the legacy imageutils plugin."""

from typing import Any

from PIL import Image, ImageFont


def apply_pillow_compatibility() -> None:
    """Restore the two Pillow 9 APIs used by nonebot-plugin-imageutils 0.1."""
    if not hasattr(Image, "ANTIALIAS"):
        Image.ANTIALIAS = Image.Resampling.LANCZOS  # type: ignore[attr-defined]

    if not hasattr(ImageFont.FreeTypeFont, "getsize"):

        def getsize(
            self: ImageFont.FreeTypeFont,
            text: str,
            *args: Any,
            **kwargs: Any,
        ) -> tuple[int, int]:
            left, top, right, bottom = self.getbbox(text, *args, **kwargs)
            return right - left, bottom - top

        ImageFont.FreeTypeFont.getsize = getsize  # type: ignore[attr-defined]
