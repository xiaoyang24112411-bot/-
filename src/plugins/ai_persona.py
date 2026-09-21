"""Persistent DeepSeek persona management commands."""

import re

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.ai_features import AIFeatureError
from src.services.ai_features.personas import (
    WHALE_PERSONA,
    clear_persona,
    get_persona,
    set_persona,
)
from src.services.economy import get_economy_database
from src.services.economy.commands import command_text
from src.services.permissions import is_group_manager


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
set_group_persona = on_message(rule=_rule("修改设定"), priority=10, block=True)


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
        + (
            f" 当前附加人格：{persona}\n基础人格始终为“小鲸鱼”。"
            if persona
            else f" 当前使用默认小鲸鱼人格：\n{WHALE_PERSONA}"
        )
    )


@reset_ai_persona.handle()
async def handle_reset_persona(event: GroupMessageEvent) -> None:
    await clear_persona(get_economy_database(), event.group_id, event.user_id)
    await reset_ai_persona.finish(
        MessageSegment.at(event.user_id) + " 自定义人格已重置，继续使用默认小鲸鱼人格。"
    )


@set_group_persona.handle()
async def handle_set_group_persona(event: GroupMessageEvent) -> None:
    if not is_group_manager(event):
        await set_group_persona.finish("只有群主、群管理员或机器人终极管理员可以修改本群设定。")
    try:
        persona = await set_persona(
            get_economy_database(),
            event.group_id,
            0,
            command_text(event, "修改设定") or "",
        )
    except AIFeatureError as exc:
        await set_group_persona.finish(str(exc))
    except Exception:
        logger.exception("Group AI persona update failed")
        await set_group_persona.finish("本群 AI 设定修改失败，请稍后再试。")
    await set_group_persona.finish(f"本群默认 AI 设定已保存：{persona}")
