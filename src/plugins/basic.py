"""Basic ping/pong response."""

from nonebot import on_fullmatch
from nonebot.adapters.onebot.v11 import MessageEvent

ping = on_fullmatch("ping", ignorecase=True, priority=10, block=True)


@ping.handle()
async def handle_ping(event: MessageEvent) -> None:
    await ping.finish("pong")
