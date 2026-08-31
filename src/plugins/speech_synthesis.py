"""Allow-listed Chinese Edge online voice synthesis."""

import time

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_ai_feature_settings
from src.services.ai_features import AIFeatureError
from src.services.ai_features.speech import VOICES, synthesize_speech
from src.services.economy.commands import command_text

COOLDOWN_SECONDS = 10.0
last_request_at: dict[int, float] = {}

speech_synthesis = on_message(
    rule=Rule(lambda event: command_text(event, "语音") is not None),
    priority=10,
    block=True,
)
speech_roles = on_message(
    rule=Rule(lambda event: command_text(event, "语音角色") is not None),
    priority=10,
    block=True,
)


@speech_synthesis.handle()
async def handle_speech_synthesis(event: GroupMessageEvent) -> None:
    argument = (command_text(event, "语音") or "").strip()
    role = "晓晓"
    text = argument
    parts = argument.split(maxsplit=1)
    if parts and parts[0] in VOICES:
        role = parts[0]
        text = parts[1] if len(parts) == 2 else ""

    now = time.monotonic()
    remaining = COOLDOWN_SECONDS - (now - last_request_at.get(event.user_id, 0.0))
    if remaining > 0:
        await speech_synthesis.finish(f"语音请求太快，请等待 {remaining:.0f} 秒。")
    last_request_at[event.user_id] = now

    settings = get_ai_feature_settings()
    try:
        audio = await synthesize_speech(
            text,
            role,
            max_characters=settings.tts_max_characters,
            timeout=settings.tts_timeout_seconds,
        )
    except AIFeatureError as exc:
        await speech_synthesis.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Speech synthesis failed")
        await speech_synthesis.finish("语音合成失败，请稍后再试。")
    await speech_synthesis.finish(MessageSegment.record(audio) + f"\n音色：{role}")


@speech_roles.handle()
async def handle_speech_roles() -> None:
    await speech_roles.finish(
        "可用语音角色："
        + "、".join(VOICES)
        + "\n用法：语音 [角色] 文字\n例如：语音 云希 大家晚上好"
    )
