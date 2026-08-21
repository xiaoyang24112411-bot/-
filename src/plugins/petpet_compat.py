"""Friendly aliases and sender fallback for the third-party petpet plugin."""

import asyncio
import re

from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment
from nonebot.exception import IgnoredException
from nonebot.log import logger
from nonebot.message import event_postprocessor, event_preprocessor
from nonebot_plugin_imageutils.fonts import add_font
from nonebot_plugin_petpet import download as petpet_download
from nonebot_plugin_petpet.data_source import memes

from src.compat.pydantic import apply_build_image_schema_compatibility
from src.services.petpet import (
    has_explicit_target,
    normalize_command_text,
    strip_optional_command_prefix,
)

apply_build_image_schema_compatibility()


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


def is_registered_petpet_command(text: str) -> bool:
    command = text.lstrip()
    if command.startswith("/"):
        command = command[1:]
    command = command.split(maxsplit=1)[0] if command else ""
    return bool(command) and any(
        re.fullmatch(meme.pattern, command, re.IGNORECASE) for meme in memes
    )


@event_preprocessor
async def normalize_petpet_message(bot: Bot, event: MessageEvent) -> None:
    message = event.get_message()
    if not message or not message[0].is_text():
        return

    first_text = str(message[0].data.get("text", ""))
    normalized, is_alias_or_common = normalize_command_text(first_text)
    if not is_alias_or_common and not is_registered_petpet_command(normalized):
        return

    if petpet_render_lock.locked():
        await bot.send(event, "当前有表情正在生成，请稍后再试。")
        raise IgnoredException
    await petpet_render_lock.acquire()
    active_petpet_events.add(id(event))

    normalized = strip_optional_command_prefix(normalized)
    message[0].data["text"] = normalized
    if not has_explicit_target(message, normalized):
        message.append(MessageSegment.text(" 自己"))


@event_postprocessor
async def release_petpet_render_lock(event: MessageEvent) -> None:
    event_id = id(event)
    if event_id not in active_petpet_events:
        return
    active_petpet_events.remove(event_id)
    if petpet_render_lock.locked():
        petpet_render_lock.release()
