"""The /问 <question> DeepSeek command."""

import time

from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.params import CommandArg

from src.config import get_deepseek_settings
from src.services.llm import DeepSeekError, ask_deepseek

MAX_PROMPT_LENGTH = 1000
COOLDOWN_SECONDS = 15.0
last_request_at: dict[int, float] = {}

ask = on_command("问", aliases={"ai"}, priority=10, block=True)


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

    try:
        reply = await ask_deepseek(prompt, get_deepseek_settings())
    except DeepSeekError as exc:
        await ask.finish(str(exc))
    except Exception:
        logger.exception("DeepSeek request failed unexpectedly")
        await ask.finish("AI 服务发生未知错误，请稍后再试。")

    await ask.finish(reply.text)

