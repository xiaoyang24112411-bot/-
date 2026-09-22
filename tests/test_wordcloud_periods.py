from datetime import datetime, timedelta, timezone

import pytest

from src.services.ai_features.wordclouds import (
    get_wordcloud_messages,
    get_wordcloud_setting,
    record_wordcloud_message,
    set_wordcloud_enabled,
)
from src.services.economy.database import EconomyDatabase

CHINA = timezone(timedelta(hours=8))


async def test_today_wordcloud_uses_beijing_midnight(tmp_path):
    database = EconomyDatabase(tmp_path / "wordcloud.sqlite3")
    await set_wordcloud_enabled(database, 1, True, 10, 30)
    midnight = datetime(2026, 9, 22, tzinfo=CHINA)
    current = midnight + timedelta(minutes=10)
    await record_wordcloud_message(
        database, 1, 10, "昨天的发言", now=midnight - timedelta(seconds=1)
    )
    await record_wordcloud_message(database, 1, 10, "午夜的发言", now=midnight)
    await record_wordcloud_message(database, 1, 10, "当前的发言", now=current)
    today = await get_wordcloud_messages(
        database, 1, 1, now=current.astimezone(timezone.utc), period="today"
    )
    assert set(today) == {"午夜的发言", "当前的发言"}
    rolling = await get_wordcloud_messages(database, 1, 1, now=current)
    assert "昨天的发言" in rolling


@pytest.mark.parametrize("elapsed_days", [0, 2, 6])
async def test_week_wordcloud_starts_monday_in_beijing(tmp_path, elapsed_days):
    database = EconomyDatabase(tmp_path / "wordcloud.sqlite3")
    await set_wordcloud_enabled(database, 1, True, 10, 30)
    monday = datetime(2026, 9, 21, tzinfo=CHINA)
    current = monday + timedelta(days=elapsed_days, minutes=10)
    await record_wordcloud_message(
        database, 1, 10, "上周日的发言", now=monday - timedelta(seconds=1)
    )
    await record_wordcloud_message(database, 1, 10, "周一零点的发言", now=monday)
    await record_wordcloud_message(database, 1, 10, "当前的发言", now=current)
    week = await get_wordcloud_messages(database, 1, 7, now=current, period="week")
    assert set(week) == {"周一零点的发言", "当前的发言"}
    rolling = await get_wordcloud_messages(database, 1, 7, now=current)
    assert "上周日的发言" in rolling


async def test_disabled_recording_expires_history_without_shortening_retention(tmp_path):
    database = EconomyDatabase(tmp_path / "wordcloud.sqlite3")
    start = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    for group_id, retention in ((1, 30), (2, 90)):
        await set_wordcloud_enabled(database, group_id, True, 10, retention)
        await record_wordcloud_message(database, group_id, 10, "较早的记录", now=start)
        await record_wordcloud_message(
            database, group_id, 10, "较新的记录", now=start + timedelta(days=10)
        )
        await set_wordcloud_enabled(database, group_id, False, 10, retention)
    current = start + timedelta(days=31)
    assert not await record_wordcloud_message(database, 1, 10, "禁止收集", now=current)
    assert await get_wordcloud_messages(database, 1, 1, now=current, period="today") == ()
    # An empty today's cloud must only remove expired data, not all older data.
    async with database.connect() as connection:
        rows = await (await connection.execute(
            "SELECT message_text FROM wordcloud_messages WHERE group_id = ?", (1,)
        )).fetchall()
    assert [row["message_text"] for row in rows] == ["较新的记录"]
    assert set(await get_wordcloud_messages(database, 2, 90, now=current)) == {
        "较早的记录", "较新的记录"
    }
    setting = await get_wordcloud_setting(database, 2)
    assert not setting.enabled and setting.retention_days == 90
