"""Explicit group choice commands, adapted to the project's matcher conventions."""

from nonebot import get_bots, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_community_settings
from src.services.economy.commands import command_text
from src.services.group_choices import ChoiceError, choose_one, shuffle_choices


def _rule(command: str) -> Rule:
    def matches(event) -> bool:
        return (
            get_community_settings().choices_enabled
            and isinstance(event, GroupMessageEvent)
            and event.user_id != event.self_id
            and str(event.user_id) not in get_bots()
            and getattr(event.sender, "is_bot", False) is not True
            and all(segment.type == "text" for segment in event.original_message)
            and command_text(event, command) is not None
        )
    return Rule(matches)


choose = on_message(rule=_rule("帮我选"), priority=10, block=True)
shuffle = on_message(rule=_rule("随机排序"), priority=10, block=True)


@choose.handle()
async def handle_choose(event: GroupMessageEvent) -> None:
    try:
        result = choose_one(command_text(event, "帮我选") or "")
    except ChoiceError as exc:
        await choose.finish(MessageSegment.text(str(exc)))
    await choose.finish(MessageSegment.text(f"帮你选好了：{result}\n（随机选择，仅供娱乐）"))


@shuffle.handle()
async def handle_shuffle(event: GroupMessageEvent) -> None:
    try:
        result = shuffle_choices(command_text(event, "随机排序") or "")
    except ChoiceError as exc:
        await shuffle.finish(MessageSegment.text(str(exc)))
    lines = [f"{index}. {value}" for index, value in enumerate(result, 1)]
    await shuffle.finish(MessageSegment.text("随机排序：\n" + "\n".join(lines)))
