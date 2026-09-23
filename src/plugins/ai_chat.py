"""The /问 <question> DeepSeek command."""

import time
from collections import deque

from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from src.config import get_deepseek_settings, get_meme_settings, get_web_search_settings
from src.services.ai_features.personas import get_effective_persona
from src.services.ai_search import WebSearchError, search_web
from src.services.economy import EconomyError, get_economy_database
from src.services.llm import DeepSeekError, ask_deepseek
from src.services.media.message_image import image_url_from_event
from src.services.media.qq_image import fetch_qq_image

MAX_PROMPT_LENGTH = 1000
COOLDOWN_SECONDS = 15.0
last_request_at: dict[int, float] = {}
conversation_history: dict[tuple[int, int], deque[tuple[str, str]]] = {}

ask = on_command("问", aliases={"ai"}, priority=10, block=True)
deep_ask = on_command("深度问", priority=10, block=True)
web_ask = on_command("联网问", priority=10, block=True)
deep_web_ask = on_command("深度联网问", priority=10, block=True)
clear_chat = on_command("清空对话", aliases={"记忆清除"}, priority=10, block=True)


def _conversation_key(event: MessageEvent) -> tuple[int, int]:
    group_id = event.group_id if isinstance(event, GroupMessageEvent) else 0
    return group_id, event.user_id


@ask.handle()
async def handle_ask(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),  # noqa: B008 - NoneBot dependency injection
) -> None:
    await _handle_ask(bot, event, args, ask, command="问")


@deep_ask.handle()
async def handle_deep_ask(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:  # noqa: B008
    await _handle_ask(bot, event, args, deep_ask, command="深度问", deep=True)


@web_ask.handle()
async def handle_web_ask(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:  # noqa: B008
    await _handle_ask(bot, event, args, web_ask, command="联网问", web=True)


@deep_web_ask.handle()
async def handle_deep_web_ask(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:  # noqa: B008
    await _handle_ask(bot, event, args, deep_web_ask, command="深度联网问", deep=True, web=True)


async def _handle_ask(
    bot: Bot,
    event: MessageEvent,
    args: Message,
    matcher: type[Matcher],
    *,
    command: str,
    deep: bool = False,
    web: bool = False,
) -> None:
    prompt = args.extract_plain_text().strip()
    image = None
    if isinstance(event, GroupMessageEvent):
        try:
            image_url = await image_url_from_event(bot, event)
        except EconomyError:
            pass
        else:
            try:
                image = await fetch_qq_image(image_url, get_meme_settings().max_image_bytes)
            except EconomyError as exc:
                await matcher.finish(str(exc))
    if not prompt and image is None:
        await matcher.finish(f"用法：/{command} 你的问题")
    if not prompt:
        prompt = "请看图并用简短中文解释这张图片或表情包的内容、文字与可能的语气；不确定就说明。"

    if len(prompt) > MAX_PROMPT_LENGTH:
        await matcher.finish(f"问题过长，请控制在 {MAX_PROMPT_LENGTH} 个字符以内。")

    if web and not get_web_search_settings().api_key:
        await matcher.finish("联网搜索尚未配置 Brave Search API Key，请联系机器人管理员。")

    now = time.monotonic()
    remaining = COOLDOWN_SECONDS - (now - last_request_at.get(event.user_id, 0.0))
    if remaining > 0:
        await matcher.finish(f"请求太快啦，请等待 {remaining:.0f} 秒后再试。")
    last_request_at[event.user_id] = now

    key = _conversation_key(event)
    history = conversation_history.setdefault(key, deque(maxlen=8))
    try:
        persona = await get_effective_persona(get_economy_database(), key[0], event.user_id)
        sources = await search_web(prompt, get_web_search_settings()) if web else ()
        reply = await ask_deepseek(
            prompt,
            get_deepseek_settings(),
            persona=persona,
            history=tuple(history),
            deep=deep,
            sources=sources,
            image=image,
        )
    except (DeepSeekError, WebSearchError) as exc:
        await matcher.finish(str(exc))
    except Exception:
        logger.exception("DeepSeek request failed unexpectedly")
        await matcher.finish("AI 服务发生未知错误，请稍后再试。")

    history.extend((("user", prompt), ("assistant", reply.text)))
    await matcher.finish(reply.text)


@clear_chat.handle()
async def handle_clear_chat(event: MessageEvent) -> None:
    conversation_history.pop(_conversation_key(event), None)
    await clear_chat.finish("当前对话上下文已清空；已设置的人格会继续保留。")
