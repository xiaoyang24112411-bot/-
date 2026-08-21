from pathlib import Path

import matplotlib
from PIL import Image, ImageDraw, ImageFont

from src.compat.pillow import apply_pillow_compatibility


def test_pillow_compatibility_restores_legacy_imageutils_apis() -> None:
    apply_pillow_compatibility()

    assert hasattr(Image, "ANTIALIAS")
    font_path = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
    font = ImageFont.truetype(font_path, 20)
    width, height = font.getsize("NoneBot")
    assert width > 0
    assert height > 0

    canvas = Image.new("RGB", (200, 60), "white")
    ImageDraw.Draw(canvas).text((5, 5), "NoneBot", font=font, fill="black")

