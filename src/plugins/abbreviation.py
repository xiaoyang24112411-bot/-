"""Network abbreviation lookup command."""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg

from src.services.abbreviation import AbbreviationError, explain_abbreviation

abbreviation = on_command("缩写", priority=10, block=True)


@abbreviation.handle()
async def handle_abbreviation(args: Message = CommandArg()) -> None:  # noqa: B008
    try:
        results = await explain_abbreviation(args.extract_plain_text())
    except AbbreviationError as exc:
        await abbreviation.finish(str(exc))
    lines: list[str] = []
    for result in results:
        lines.append(f"{result.name}：{'、'.join(result.translations)}")
    await abbreviation.finish("\n".join(lines))
