"""Global blocking must persist and reject messages before normal matchers run."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment
from nonebot.exception import FinishedException, IgnoredException

from src.services.economy.database import EconomyDatabase
from src.services.global_blacklist import block_user, is_blocked, list_blocked, unblock_user


def event(message, *, user_id=2448821316, group_id=100):
    value = Message(message)
    return GroupMessageEvent(
        time=int(time.time()), self_id=99, post_type="message", message_type="group",
        sub_type="normal", message_id=1, group_id=group_id, user_id=user_id,
        message=value, original_message=value.copy(), raw_message=str(value), font=0,
        sender={"user_id": user_id, "nickname": "测试群友"}, to_me=False,
    )


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.plugins import global_blacklist

    database = EconomyDatabase(tmp_path / "economy.sqlite3")
    monkeypatch.setattr(global_blacklist, "get_economy_database", lambda: database)
    monkeypatch.setattr(global_blacklist.management, "finish", AsyncMock(
        side_effect=FinishedException
    ))
    return global_blacklist, database


@pytest.mark.asyncio
async def test_block_persists_across_groups_and_new_database_instance(tmp_path):
    path = tmp_path / "economy.sqlite3"
    database = EconomyDatabase(path)
    assert await block_user(database, 123456789, 2448821316)
    assert not await block_user(database, 123456789, 2448821316)
    fresh = EconomyDatabase(path)
    assert await is_blocked(fresh, 123456789)
    assert not await is_blocked(fresh, 987654321)
    assert await list_blocked(fresh, 1) == (1, [123456789])
    assert await unblock_user(fresh, 123456789)
    assert not await unblock_user(fresh, 123456789)
    assert not await is_blocked(database, 123456789)


@pytest.mark.asyncio
async def test_preprocessor_silently_blocks_in_every_group(plugin):
    blacklist, database = plugin
    await block_user(database, 123456789, 2448821316)
    for group_id in (100, 200):
        with pytest.raises(IgnoredException):
            await blacklist.reject_blocked_messages(event("ping", user_id=123456789,
                                                          group_id=group_id))
    await blacklist.reject_blocked_messages(event("ping", user_id=987654321))
    await blacklist.reject_blocked_messages(event("ping", user_id=2448821316))


@pytest.mark.asyncio
async def test_owner_can_block_by_qq_or_at_and_release(plugin):
    blacklist, database = plugin
    bot = SimpleNamespace(self_id="99")
    with pytest.raises(FinishedException):
        await blacklist.handle_management(bot, event("拉黑 123456789"))
    assert await is_blocked(database, 123456789)
    with pytest.raises(FinishedException):
        await blacklist.handle_management(bot, event(MessageSegment.text("放出 ")
                                                      + MessageSegment.at(123456789)))
    assert not await is_blocked(database, 123456789)
    with pytest.raises(FinishedException):
        await blacklist.handle_management(bot, event("/拉黑 987654321"))
    assert await is_blocked(database, 987654321)
    assert blacklist._is_management_command(event("黑名单"))
    with pytest.raises(FinishedException):
        await blacklist.handle_management(bot, event("黑名单"))
    assert "987654321" in blacklist.management.finish.call_args.args[0]


@pytest.mark.asyncio
async def test_nonowner_cannot_manage_and_invalid_targets_are_rejected(plugin):
    blacklist, database = plugin
    bot = SimpleNamespace(self_id="99")
    await blacklist.handle_management(bot, event("拉黑 123456789", user_id=111111111))
    assert not await is_blocked(database, 123456789)
    for command in ("拉黑 2448821316", "拉黑 99", "拉黑 123456789 987654321",
                    "拉黑 123456789 @其他人"):
        with pytest.raises(FinishedException):
            await blacklist.handle_management(bot, event(command))
    assert not await is_blocked(database, 123456789)
