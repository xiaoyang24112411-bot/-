"""Recognize QQ avatars and bound failures in the modern meme downloader."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs, urlparse


def qq_id_from_avatar_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None

    host = (parsed.hostname or "").lower()
    query = parse_qs(parsed.query)
    qq_id: str | None = None
    if host in {"q1.qlogo.cn", "q2.qlogo.cn", "q3.qlogo.cn"}:
        qq_id = (query.get("nk") or query.get("dst_uin") or [None])[0]
    elif host in {
        "qlogo2.store.qq.com",
        "qlogo3.store.qq.com",
        "qlogo4.store.qq.com",
    }:
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "qzone" and parts[1] == parts[2]:
            qq_id = parts[1]
    return qq_id if qq_id and qq_id.isdigit() else None


class MemeImageDownloadError(RuntimeError):
    """Image fetching failed; the command should give a friendly response."""


async def fetch_meme_image(
    event: Any,
    bot: Any,
    state: Any,
    image: Any,
    *,
    native_fetch: Callable[..., Awaitable[bytes | None]],
    avatar_fetch: Callable[..., Awaitable[bytes]],
    timeout: float = 30,
) -> bytes | None:
    """Give all avatar fallbacks together a deadline; preserve cancellation."""

    async def fetch() -> bytes | None:
        # An embedded image takes precedence over an unrelated original URL.
        if not (image.raw or image.path) and (qq_id := qq_id_from_avatar_url(image.url)):
            try:
                return await avatar_fetch(qq_id, timeout=5)
            except Exception:
                # The protocol adapter can still have access to the original image.
                pass
        return await native_fetch(event, bot, state, image)

    try:
        return await asyncio.wait_for(fetch(), timeout=timeout)
    except Exception as exc:
        raise MemeImageDownloadError("meme image download failed") from exc
