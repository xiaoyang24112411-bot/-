"""Random ChangYa/SingDuck user singing clip."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_information_settings
from src.services.ai_features import AIFeatureError
from src.services.ai_features.singing import fetch_random_singing
from src.services.economy.commands import command_text

random_singing = on_message(
    rule=Rule(
        lambda event: (
            command_text(event, "随机唱鸭") is not None or command_text(event, "唱鸭") is not None
        )
    ),
    priority=10,
    block=True,
)


@random_singing.handle()
async def handle_random_singing(event: GroupMessageEvent) -> None:
    settings = get_information_settings()
    try:
        clip = await fetch_random_singing(
            settings.api_60s_base_url,
            fallback_urls=settings.api_60s_fallback_urls,
            timeout=max(30, settings.timeout_seconds),
        )
    except AIFeatureError as exc:
        await random_singing.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Random singing lookup failed")
        await random_singing.finish("随机唱鸭获取失败，请稍后再试。")

    description = f"\n歌曲：{clip.song_name}｜原唱：{clip.singer}\n演唱用户：{clip.performer}"
    if clip.detail_url:
        description += "\n原始作品页：" + clip.detail_url
    await random_singing.finish(MessageSegment.record(clip.audio) + description)
