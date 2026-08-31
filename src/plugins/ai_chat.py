"""The /问 <question> DeepSeek command."""

import time
from collections import deque

from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageEvent
from nonebot.params import CommandArg

from src.config import get_deepseek_settings
from src.services.ai_features.personas import get_persona
from src.services.economy import get_economy_database
from src.services.llm import DeepSeekError, ask_deepseek

MAX_PROMPT_LENGTH = 1000
COOLDOWN_SECONDS = 15.0
last_request_at: dict[int, float] = {}
conversation_history: dict[tuple[int, int], deque[tuple[str, str]]] = {}

ask = on_command("问", aliases={"ai"}, priority=10, block=True)
clear_chat = on_command("清空对话", priority=10, block=True)


def _conversation_key(event: MessageEvent) -> tuple[int, int]:
    group_id = event.group_id if isinstance(event, GroupMessageEvent) else 0
    return group_id, event.user_id


@ask.handle()
async def handle_ask(
    event: MessageEvent,
    args: Message = CommandArg(),  # noqa: B008 - NoneBot dependency injection
) -> None:
    prompt = args.extract_plain_text().strip()
    if not prompt:
        await ask.finish("用法：/问 你的问题\n例如：/问 用一句话解释什么是 Python")

    if len(prompt) > MAX_PROMPT_LENGTH:
        await ask.finish(f"问题过长，请控制在 {MAX_PROMPT_LENGTH} 个字符以内。")

    now = time.monotonic()
    remaining = COOLDOWN_SECONDS - (now - last_request_at.get(event.user_id, 0.0))
    if remaining > 0:
        await ask.finish(f"请求太快啦，请等待 {remaining:.0f} 秒后再试。")
    last_request_at[event.user_id] = now

    key = _conversation_key(event)
    history = conversation_history.setdefault(key, deque(maxlen=8))
    persona = await get_persona(get_economy_database(), key[0], event.user_id)
    try:
        reply = await ask_deepseek(
            prompt,
            get_deepseek_settings(),
            persona=persona,
            history=tuple(history),
        )
    except DeepSeekError as exc:
        await ask.finish(str(exc))
    except Exception:
        logger.exception("DeepSeek request failed unexpectedly")
        await ask.finish("AI 服务发生未知错误，请稍后再试。")

    history.extend((("user", prompt), ("assistant", reply.text)))
    await ask.finish(reply.text)


@clear_chat.handle()
async def handle_clear_chat(event: MessageEvent) -> None:
    conversation_history.pop(_conversation_key(event), None)
    await clear_chat.finish("当前对话上下文已清空；已设置的人格会继续保留。")
