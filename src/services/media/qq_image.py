"""Bounded retrieval and validation of OneBot QQ image segments."""

from io import BytesIO
from urllib.parse import urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

from src.services.economy.errors import EconomyError

IMAGE_EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}
TRUSTED_HOST_SUFFIXES = ("qpic.cn", "qq.com", "qq.com.cn", "gtimg.cn")


def _trusted_image_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        return (
            parts.scheme == "https"
            and parts.port in (None, 443)
            and parts.username is None
            and parts.password is None
            and any(
                host == suffix or host.endswith("." + suffix) for suffix in TRUSTED_HOST_SUFFIXES
            )
        )
    except ValueError:
        return False


def inspect_image(data: bytes, max_bytes: int) -> str:
    if not data or len(data) > max_bytes:
        raise EconomyError("图片为空或超过大小限制。")
    try:
        with Image.open(BytesIO(data)) as image:
            extension = IMAGE_EXTENSIONS.get(image.format or "")
            frames = getattr(image, "n_frames", 1)
            if not extension or image.width * image.height > 20_000_000 or frames > 100:
                raise EconomyError("仅支持 2000 万像素、100 帧以内的 JPG、PNG、GIF、WebP 图片。")
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise EconomyError("无法识别这张图片，请换一张再试。") from exc
    return extension


async def fetch_qq_image(
    url: str, max_bytes: int = 8 * 1024 * 1024, client: httpx.AsyncClient | None = None
) -> tuple[bytes, str]:
    if not _trusted_image_url(url):
        raise EconomyError("只支持从 QQ 群消息中读取的 HTTPS 图片链接。")
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False)
    try:
        async with http_client.stream("GET", url) as response:
            response.raise_for_status()
            if response.headers.get("content-length", "").isdigit():
                if int(response.headers["content-length"]) > max_bytes:
                    raise EconomyError("图片超过大小限制。")
            data = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                if len(data) + len(chunk) > max_bytes:
                    raise EconomyError("图片超过大小限制。")
                data.extend(chunk)
        image = bytes(data)
        return image, inspect_image(image, max_bytes)
    except httpx.HTTPError as exc:
        raise EconomyError("读取 QQ 图片失败，请重新发送后再试。") from exc
    finally:
        if owns_client:
            await http_client.aclose()
