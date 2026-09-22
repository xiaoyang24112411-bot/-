"""Bounded, read-only probes for the database and actual QQ login status."""

import asyncio
from collections.abc import Mapping
from typing import Any, Protocol

from src.services.economy.database import EconomyDatabase


class StatusBot(Protocol):
    async def get_status(self) -> dict[str, Any]: ...


async def _database_ready(database: EconomyDatabase) -> bool:
    try:
        async with database.connect() as connection:
            cursor = await connection.execute("SELECT 1")
            return (await cursor.fetchone())[0] == 1
    except Exception:
        # The health endpoint never exposes database paths or exception details.
        return False


async def _account_online(bot: StatusBot) -> bool:
    try:
        status = await bot.get_status()
        return status.get("online") is True and status.get("good") is True
    except Exception:
        return False


async def _bounded_probe(probe) -> bool:
    try:
        return await asyncio.wait_for(probe, timeout=4)
    except asyncio.TimeoutError:
        return False


async def runtime_health(
    database: EconomyDatabase, bots: Mapping[str, StatusBot]
) -> dict[str, Any]:
    """A connected OneBot socket alone does not prove the QQ account is online."""
    results = await asyncio.gather(
        _bounded_probe(_database_ready(database)),
        *(_bounded_probe(_account_online(bot)) for bot in bots.values()),
    )
    database_ok = results[0]
    online_count = sum(results[1:])
    healthy = database_ok and bool(bots) and online_count == len(bots)
    return {
        "status": "ok" if healthy else "degraded",
        "database": "ok" if database_ok else "unavailable",
        "connected_accounts": len(bots),
        "online_accounts": online_count,
    }
