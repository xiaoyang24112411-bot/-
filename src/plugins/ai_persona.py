"""Persistent DeepSeek persona management commands."""

import re

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.ai_features import AIFeatureError
from src.services.ai_features.personas import clear_persona, get_persona, set_persona
from src.services.economy import get_economy_database
from src.services.economy.commands import command_text


def _rule(command: str) -> Rule:
    return Rule(lambda event: command_text(event, command) is not None)


def _persona_text(event: GroupMessageEvent) -> str | None:
    regular = command_text(event, "设置人格")
    if regular is not None:
        return regular
    matched = re.match(r"^/?设置人格\s*[:：]\s*(.+)$", event.get_plaintext().strip(), re.DOTALL)
    return matched.group(1).strip() if matched else None


set_ai_persona = on_message(
    rule=Rule(lambda event: _persona_text(event) is not None), priority=10, block=True
)
show_ai_persona = on_message(rule=_rule("查看人格"), priority=10, block=True)
reset_ai_persona = on_message(rule=_rule("重置人格"), priority=10, block=True)


@set_ai_persona.handle()
async def handle_set_persona(event: GroupMessageEvent) -> None:
    try:
        persona = await set_persona(
            get_economy_database(),
            event.group_id,
            event.user_id,
            _persona_text(event) or "",
        )
    except AIFeatureError as exc:
        await set_ai_persona.finish(str(exc))
    except Exception:
        logger.exception("AI persona update failed")
        await set_ai_persona.finish("人格设置失败，请稍后再试。")
    await set_ai_persona.finish(
        MessageSegment.at(event.user_id) + f" 人格已保存：{persona}\n使用 /问 开始聊天。"
    )


@show_ai_persona.handle()
async def handle_show_persona(event: GroupMessageEvent) -> None:
    persona = await get_persona(get_economy_database(), event.group_id, event.user_id)
    await show_ai_persona.finish(
        MessageSegment.at(event.user_id)
        + (f" 当前人格：{persona}" if persona else " 当前没有设置自定义人格。")
    )


@reset_ai_persona.handle()
async def handle_reset_persona(event: GroupMessageEvent) -> None:
    await clear_persona(get_economy_database(), event.group_id, event.user_id)
    await reset_ai_persona.finish(MessageSegment.at(event.user_id) + " 自定义人格已重置。")
