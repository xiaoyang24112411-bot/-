"""Local high-quality copywriting command."""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.rule import Rule

from src.services.economy.commands import command_text
from src.services.information import InformationError
from src.services.information.quotes import random_quote


def _category(event: GroupMessageEvent) -> str | None:
    for command in ("高质量文案", "随机文案"):
        argument = command_text(event, command)
        if argument is not None:
            return argument
    return None


quality_quote = on_message(
    rule=Rule(lambda event: _category(event) is not None), priority=10, block=True
)


@quality_quote.handle()
async def handle_quality_quote(event: GroupMessageEvent) -> None:
    try:
        quote = random_quote(_category(event) or "")
    except InformationError as exc:
        await quality_quote.finish(str(exc))
    await quality_quote.finish(f"【{quote.category}】\n{quote.text}")
