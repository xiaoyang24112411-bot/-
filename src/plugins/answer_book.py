"""Answer book command."""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.economy.commands import command_text
from src.services.entertainment.answer_book import open_answer_book


def is_answer_book(event: GroupMessageEvent) -> bool:
    return command_text(event, "答案之书") is not None


answer_book = on_message(rule=Rule(is_answer_book), priority=10, block=True)


@answer_book.handle()
async def handle_answer_book(event: GroupMessageEvent) -> None:
    question = (command_text(event, "答案之书") or "").strip()
    if len(question) > 200:
        await answer_book.finish("问题太长啦，请控制在 200 个字符以内。")

    prefix = f"你的问题：{question}\n" if question else ""
    await answer_book.finish(
        MessageSegment.at(event.user_id) + f" {prefix}《答案之书》：\n{open_answer_book()}"
    )
