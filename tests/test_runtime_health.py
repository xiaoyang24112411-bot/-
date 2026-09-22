from unittest.mock import AsyncMock

import pytest

from src.services.economy.database import EconomyDatabase
from src.services.runtime_health import runtime_health


@pytest.mark.asyncio
async def test_connected_socket_does_not_mean_qq_online(tmp_path):
    database = EconomyDatabase(tmp_path / "health.sqlite3")
    bot = AsyncMock()
    bot.get_status.return_value = {"online": False, "good": True}
    report = await runtime_health(database, {"bot": bot})
    assert report["status"] == "degraded"
    assert report["connected_accounts"] == 1
    assert report["online_accounts"] == 0
    assert report["database"] == "ok"

    bot.get_status.return_value = {"online": True, "good": True}
    assert (await runtime_health(database, {"bot": bot}))["status"] == "ok"


@pytest.mark.asyncio
async def test_status_api_failure_and_no_accounts_are_degraded(tmp_path):
    database = EconomyDatabase(tmp_path / "health.sqlite3")
    bot = AsyncMock()
    bot.get_status.side_effect = RuntimeError("private error details")
    report = await runtime_health(database, {"bot": bot})
    assert report["status"] == "degraded"
    assert "private" not in str(report)
    assert (await runtime_health(database, {}))["status"] == "degraded"


@pytest.mark.asyncio
async def test_database_failure_does_not_report_healthy(tmp_path):
    # A directory cannot be opened as an SQLite database.
    database = EconomyDatabase(tmp_path)
    bot = AsyncMock()
    bot.get_status.return_value = {"online": True, "good": True}
    report = await runtime_health(database, {"bot": bot})
    assert report["database"] == "unavailable"
    assert report["status"] == "degraded"
