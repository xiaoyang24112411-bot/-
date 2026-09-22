"""Friendly aliases and sender fallback for the third-party petpet plugin."""

import asyncio
import re
from collections.abc import AsyncIterator
from pathlib import Path

from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment
from nonebot.exception import IgnoredException
from nonebot.log import logger
from nonebot.message import event_preprocessor
from nonebot.params import Depends
from nonebot_plugin_imageutils.fonts import add_font
from nonebot_plugin_petpet import depends as petpet_depends
from nonebot_plugin_petpet import download as petpet_download
from nonebot_plugin_petpet.data_source import memes

from src.compat.pydantic import apply_build_image_schema_compatibility
from src.services.petpet import (
    download_qq_avatar,
    has_explicit_target,
    normalize_command_text,
    strip_optional_command_prefix,
)

apply_build_image_schema_compatibility()

# petpet 0.3.21 hard-codes an obsolete plain-HTTP q1.qlogo.cn endpoint. Both
# modules hold a reference to that function, so replace both with our HTTPS
# multi-endpoint downloader.
petpet_download.download_avatar = download_qq_avatar
petpet_depends.download_avatar = download_qq_avatar

bundled_petpet_path = Path(__file__).resolve().parents[2] / "assets" / "petpet"
if not (petpet_download.data_path / "resource_list.json").is_file() and (
    bundled_petpet_path / "resource_list.json"
).is_file():
    petpet_download.data_path = bundled_petpet_path


async def check_local_petpet_resources() -> None:
    """Use the prefetched resource pack and never block startup on a remote proxy."""
    local_font = petpet_download.data_path / "fonts" / "consola.ttf"
    if local_font.is_file():
        await add_font("consola.ttf", local_font)
    else:
        logger.warning(f"Petpet local font is missing: {local_font}")
    logger.info("Petpet is using the prefetched local resource pack")


# The legacy plugin's startup hook resolves this global at runtime, so replacing
# it here keeps its normal lifecycle while avoiding its obsolete ghproxy default.
petpet_download.check_resources = check_local_petpet_resources

petpet_render_lock = asyncio.Lock()
active_petpet_events: set[int] = set()


async def petpet_event_scope(event: MessageEvent) -> AsyncIterator[None]:
    """Release our lock even when a different preprocessor ignores the event.

    NoneBot closes generator dependencies with its event-scoped exit stack, but
    skips event postprocessors when preprocessing fails or ignores an event.
    """
    try:
        yield
    finally:
        if id(event) in active_petpet_events:
            active_petpet_events.remove(id(event))
            petpet_render_lock.release()


def is_registered_petpet_command(text: str) -> bool:
    command = text.lstrip()
    if command.startswith("/"):
        command = command[1:]
    command = command.split(maxsplit=1)[0] if command else ""
    return bool(command) and any(
        re.fullmatch(meme.pattern, command, re.IGNORECASE) for meme in memes
    )


@event_preprocessor
async def normalize_petpet_message(
    bot: Bot, event: MessageEvent, _scope: None = Depends(petpet_event_scope)  # noqa: B008
) -> None:
    message = event.get_message()
    if not message or not message[0].is_text():
        return

    first_text = str(message[0].data.get("text", ""))
    if re.fullmatch(r"\s*/?表情列表\s*", first_text):
        message[0].data["text"] = "/头像表情包"
        return

    generic = re.match(r"^(?P<leading>\s*)/?表情\s+(?P<template>\S+)(?P<rest>.*)$", first_text)
    if generic:
        first_text = (
            generic.group("leading") + generic.group("template") + generic.group("rest")
        )
        message[0].data["text"] = first_text
    normalized, is_alias_or_common = normalize_command_text(first_text)
    if not is_alias_or_common and not is_registered_petpet_command(normalized):
        return

    if petpet_render_lock.locked():
        await bot.send(event, "当前有表情正在生成，请稍后再试。")
        raise IgnoredException("petpet renderer is busy")
    await petpet_render_lock.acquire()
    active_petpet_events.add(id(event))

    normalized = strip_optional_command_prefix(normalized)
    message[0].data["text"] = normalized
    if not has_explicit_target(message, normalized):
        message.append(MessageSegment.text(" 自己"))
