"""Free, deterministic group morning/night replies, independent of AI switches."""

import asyncio
import random

from nonebot import get_bots, logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_greeting_settings
from src.services.greetings import GreetingCooldowns, classify_group_greeting

settings = get_greeting_settings()
cooldowns = GreetingCooldowns()
SEND_TIMEOUT_SECONDS = 15


def is_greeting(event) -> bool:
    return classify_group_greeting(event, settings, get_bots()) is not None


# Run before AI @ replies (15), but leave wordcloud/recall observers running.
greetings = on_message(rule=Rule(is_greeting), priority=12, block=False)


@greetings.handle()
async def handle_greeting(bot: Bot, event: GroupMessageEvent) -> None:
    kind = classify_group_greeting(event, settings, get_bots())
    if kind is None:
        return
    limited = settings.user_cooldown_seconds > 0 or settings.group_cooldown_seconds > 0
    # With both limits disabled, do not drop concurrent greetings as "pending".
    if limited and not cooldowns.acquire(event.group_id, event.user_id, kind):
        return
    try:
        replies = settings.morning_replies if kind == "morning" else settings.night_replies
        # Explicit text prevents custom [CQ:...] strings from becoming rich messages.
        await asyncio.wait_for(
            bot.send(event, MessageSegment.text(random.choice(replies))),
            timeout=SEND_TIMEOUT_SECONDS,
        )
        if limited:
            cooldowns.succeed(event.group_id, event.user_id, kind, settings)
        logger.info("Greeting sent: group={} kind={}", event.group_id, kind)
    except Exception as exc:
        # Do not echo API exceptions, credentials or group message contents to logs.
        logger.warning(
            "Greeting send failed: group={} kind={} error={}",
            event.group_id, kind, type(exc).__name__,
        )
    finally:
        if limited:
            cooldowns.release(event.group_id)
