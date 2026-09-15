"""Multi-sided dice command."""

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.rule import Rule

from src.services.economy import EconomyError
from src.services.economy.commands import command_text
from src.services.games.dice import roll_dice, roll_range


def is_dice(event: GroupMessageEvent) -> bool:
    return command_text(event, "掷骰子") is not None


dice = on_message(rule=Rule(is_dice), priority=10, block=True)
range_roll = on_command("roll", priority=10, block=True)


@dice.handle()
async def handle_dice(event: GroupMessageEvent) -> None:
    try:
        result = roll_dice(command_text(event, "掷骰子") or "")
    except EconomyError as exc:
        await dice.finish(str(exc))
    rolls = "、".join(str(value) for value in result.rolls)
    await dice.finish(
        MessageSegment.at(event.user_id)
        + f" 掷出了 {result.count}d{result.faces}：{rolls}\n合计：{result.total}"
    )


@range_roll.handle()
async def handle_range_roll(args: Message = CommandArg()) -> None:  # noqa: B008
    try:
        result = roll_range(args.extract_plain_text())
    except EconomyError as exc:
        await range_roll.finish(str(exc))
    await range_roll.finish(f"🎲 随机结果：{result}")
