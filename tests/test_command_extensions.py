import random

import pytest

from src.services.ai_features.personas import get_persona, set_persona
from src.services.calculator import CalculatorError, calculate
from src.services.economy.accounts import get_leaderboard
from src.services.economy.common import apply_change, iso_time
from src.services.economy.database import EconomyDatabase
from src.services.games.dice import roll_range
from src.services.games.gacha import draw_arknights, draw_fgo, draw_genshin
from src.services.recall_cache import (
    CachedMessage,
    latest_recalled,
    remember_message,
    remember_recall,
    set_recall_enabled,
)
from src.services.subscriptions import (
    add_rss_subscription,
    delete_rss_subscription,
    list_rss_subscriptions,
    parse_feed,
)


def test_safe_calculator():
    assert calculate("1+2*3") == "7"
    assert calculate("(10-4)/2") == "3"
    with pytest.raises(CalculatorError):
        calculate("__import__('os').system('dir')")
    with pytest.raises(CalculatorError, match="除以零"):
        calculate("1/0")


def test_roll_and_gacha_bounds():
    assert 1 <= roll_range("1-100", random.Random(1)) <= 100
    assert -5 <= roll_range("-5~5", random.Random(2)) <= 5
    assert len(draw_genshin(10, random.Random(1))) == 10
    assert max(item.rarity for item in draw_genshin(10, random.Random(2))) >= 4
    assert max(item.rarity for item in draw_arknights(10, random.Random(3))) >= 5
    assert len(draw_fgo(330, random.Random(4))) == 330


@pytest.mark.asyncio
async def test_admin_extensions_storage(tmp_path):
    database = EconomyDatabase(tmp_path / "extensions.sqlite3")
    now = iso_time()
    async with database.transaction() as connection:
        for user_id, amount in ((10, 20), (20, 50), (30, 30)):
            await apply_change(
                connection,
                group_id=1,
                user_id=user_id,
                amount=amount,
                event_type="extension_seed",
                reference_id=f"seed-{user_id}",
                note="test",
                now=now,
            )
    leaderboard = await get_leaderboard(database, 1)
    assert [item.user_id for item in leaderboard] == [20, 30, 10]

    await set_persona(database, 1, 0, "本群默认使用简洁口吻")
    assert await get_persona(database, 1, 99) == "本群默认使用简洁口吻"
    await set_persona(database, 1, 99, "个人使用活泼口吻")
    assert await get_persona(database, 1, 99) == "个人使用活泼口吻"

    await set_recall_enabled(database, 1, True, 2448821316)
    remember_message(1, CachedMessage(123, 99, "测试撤回内容", 1))
    assert remember_recall(1, 123, 99)
    assert latest_recalled(1).text == "测试撤回内容"


@pytest.mark.asyncio
async def test_rss_parser_and_storage(tmp_path):
    content = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Example Feed</title>
    <item><guid>entry-2</guid><title>Newest</title><link>https://example.com/2</link></item>
    <item><guid>entry-1</guid><title>Older</title><link>https://example.com/1</link></item>
    </channel></rss>"""
    feed = parse_feed(content)
    assert feed.title == "Example Feed"
    assert feed.entries[0].entry_id == "entry-2"

    database = EconomyDatabase(tmp_path / "rss.sqlite3")
    item = await add_rss_subscription(
        database, group_id=1, url="https://example.com/feed.xml", created_by=99, feed=feed
    )
    assert item.last_entry_id == "entry-2"
    assert len(await list_rss_subscriptions(database, 1)) == 1
    assert await delete_rss_subscription(database, 1, str(item.id))
