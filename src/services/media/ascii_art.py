"""Convert downloaded raster image bytes to compact text art."""

from io import BytesIO

import httpx
from PIL import Image, ImageOps

from src.services.economy.errors import EconomyError

CHARACTERS = "@%#*+=-:. "


async def download_image(url: str, max_bytes: int = 8 * 1024 * 1024) -> bytes:
    if not url.startswith(("http://", "https://")):
        raise EconomyError("暂不支持这种图片地址，请使用群内上传的图片。")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise EconomyError("图片下载失败，请重新上传后再试。") from exc
    if len(response.content) > max_bytes:
        raise EconomyError("图片超过 8 MB，无法转换。")
    return response.content


def image_to_ascii(image_bytes: bytes, width: int = 36) -> str:
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            image = ImageOps.exif_transpose(source).convert("L")
            ratio = image.height / max(image.width, 1)
            height = max(1, min(30, int(width * ratio * 0.48)))
            image = image.resize((width, height))
            pixels = tuple(image.getdata())
    except (OSError, ValueError) as exc:
        raise EconomyError("无法识别这张图片。") from exc
    scale = len(CHARACTERS) - 1
    rows = []
    for row in range(height):
        values = pixels[row * width : (row + 1) * width]
        rows.append("".join(CHARACTERS[value * scale // 255] for value in values))
    return "\n".join(rows)
