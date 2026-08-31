"""Playful licking-dog diary command."""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.economy.commands import command_text
from src.services.entertainment.licking_dog_diary import random_diary


def is_licking_dog_diary(event: GroupMessageEvent) -> bool:
    return command_text(event, "舔狗日记") is not None


licking_dog_diary = on_message(
    rule=Rule(is_licking_dog_diary),
    priority=10,
    block=True,
)


@licking_dog_diary.handle()
async def handle_licking_dog_diary(event: GroupMessageEvent) -> None:
    await licking_dog_diary.finish(
        MessageSegment.at(event.user_id) + f" 舔狗日记：\n{random_diary()}"
    )
