"""Basic connectivity response."""

import time

from nonebot import on_fullmatch
from nonebot.adapters.onebot.v11 import MessageEvent

ping = on_fullmatch(("ping", "/ping"), ignorecase=True, priority=10, block=True)


@ping.handle()
async def handle_ping(event: MessageEvent) -> None:
    if event.get_plaintext().strip().lower() == "ping":
        await ping.finish("pong")
    latency_ms = max(0, round((time.time() - event.time) * 1000))
    await ping.finish(f"pong｜约 {latency_ms} ms")
