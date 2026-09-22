import asyncio
import sqlite3
from dataclasses import replace
from unittest.mock import AsyncMock

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import (
    Adapter,
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
    PrivateMessageEvent,
)

from src.config import CommunitySettings
from src.services.economy.database import EconomyDatabase
from src.services.group_polls import (
    PollError,
    cast_vote,
    close_poll,
    create_poll,
    format_poll,
    get_poll,
    list_polls,
    parse_poll_creation,
    parse_poll_id,
)

SCOPE = {"bot_id": 99, "group_id": 100}


def event(text="发起投票 吃什么 | 火锅 | 烧烤", *, user_id=20, group_id=100,
          self_id=99, message_id=1, role="member", is_bot=False):
    message = text if isinstance(text, Message) else Message(MessageSegment.text(text))
    return GroupMessageEvent(
        time=1, self_id=self_id, post_type="message", message_type="group", sub_type="normal",
        message_id=message_id, group_id=group_id, user_id=user_id, message=message,
        raw_message=str(message), font=0,
        sender={"user_id": user_id, "nickname": "群友", "role": role, "is_bot": is_bot},
    )


@pytest.fixture
def database(tmp_path):
    return EconomyDatabase(tmp_path / "polls.sqlite3")


async def new_poll(database, **kwargs):
    options = {
        **SCOPE, "user_id": 20, "title": "吃什么", "options": ("火锅", "烧烤"),
        "request_id": "1",
    }
    options.update(kwargs)
    return await create_poll(database, **options)


def test_parse_creation_and_id_boundaries():
    assert parse_poll_creation(" 吃什么 | 火锅 | 烧烤 ") == ("吃什么", ("火锅", "烧烤"))
    assert parse_poll_id("1") == 1
    assert parse_poll_id(str(2**63 - 1)) == 2**63 - 1
    for value in ("0", "-1", "+1", "1.0", "01", "１", "1 2", str(2**63)):
        with pytest.raises(PollError):
            parse_poll_id(value)


@pytest.mark.parametrize("value", [
    "", "|甲|乙", "标题|甲", "标题|甲|", "标题|甲|甲", "标题|ABC|abc",
    "标题|" + "|".join(map(str, range(11))), "标" * 101 + "|甲|乙",
    "标题|" + "甲" * 61 + "|乙", "题" * 801,
])
def test_invalid_poll_content(value):
    with pytest.raises(PollError):
        parse_poll_creation(value)


async def test_creation_idempotency_persistence_and_no_economy_mutations(database):
    first = await new_poll(database)
    repeated = await new_poll(database)
    assert first == repeated
    assert first.counts == (0, 0)
    assert first.status == "open"
    reopened = EconomyDatabase(database.path)
    assert await get_poll(reopened, **SCOPE, poll_id=first.id) == first
    assert await list_polls(reopened, **SCOPE) == [first]
    async with database.connect() as connection:
        for table in ("economy_accounts", "point_transactions", "group_poll_votes"):
            cursor = await connection.execute(f"SELECT COUNT(*) FROM {table}")
            assert (await cursor.fetchone())[0] == 0


async def test_repeated_vote_and_changed_vote_count_once(database):
    poll = await new_poll(database)
    vote = {**SCOPE, "poll_id": poll.id, "user_id": 21}
    for _ in range(3):
        current = await cast_vote(database, **vote, option_number=1)
        assert current.counts == (1, 0)
    current = await cast_vote(database, **vote, option_number=2)
    assert current.counts == (0, 1)
    await cast_vote(database, **SCOPE, poll_id=poll.id, user_id=22, option_number=1)
    assert (await get_poll(database, **SCOPE, poll_id=poll.id)).counts == (1, 1)
    for invalid in (0, -1, 3):
        with pytest.raises(PollError, match="选项编号"):
            await cast_vote(database, **vote, option_number=invalid)


async def test_concurrent_votes_and_revotes_are_atomic(database):
    poll = await new_poll(database)
    await asyncio.gather(*(
        cast_vote(database, **SCOPE, poll_id=poll.id, user_id=user, option_number=user % 2 + 1)
        for user in range(10, 30)
    ))
    assert (await get_poll(database, **SCOPE, poll_id=poll.id)).counts == (10, 10)
    await asyncio.gather(*(
        cast_vote(database, **SCOPE, poll_id=poll.id, user_id=10, option_number=index % 2 + 1)
        for index in range(12)
    ))
    assert sum((await get_poll(database, **SCOPE, poll_id=poll.id)).counts) == 20


async def test_concurrent_creation_obeys_active_limit(database):
    results = await asyncio.gather(*(
        new_poll(database, request_id=str(index), max_active=2) for index in range(8)
    ), return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in results) == 2
    assert sum(isinstance(result, PollError) for result in results) == 6
    polls = await list_polls(database, **SCOPE)
    assert len(polls) == 2
    await close_poll(database, **SCOPE, poll_id=polls[0].id, user_id=20)
    await new_poll(database, request_id="new-slot", max_active=2)
    assert len(await list_polls(database, **SCOPE)) == 2


async def test_cross_group_and_bot_access_is_denied(database):
    poll = await new_poll(database)
    for scope in ({"bot_id": 99, "group_id": 101}, {"bot_id": 98, "group_id": 100}):
        assert await list_polls(database, **scope) == []
        with pytest.raises(PollError, match="找不到"):
            await get_poll(database, **scope, poll_id=poll.id)
        with pytest.raises(PollError, match="找不到"):
            await cast_vote(database, **scope, poll_id=poll.id, user_id=21, option_number=1)
        with pytest.raises(PollError, match="找不到"):
            await close_poll(database, **scope, poll_id=poll.id, user_id=20, is_manager=True)
        # Reused OneBot message ids in other groups/bots are independent.
        assert (await new_poll(database, **scope)).id != poll.id
    async with database.transaction() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            await connection.execute(
                "INSERT INTO group_poll_votes VALUES (98,100,?,21,1,'now')", (poll.id,),
            )


async def test_close_permissions_and_no_vote_after_close(database):
    poll = await new_poll(database)
    with pytest.raises(PollError, match="只有"):
        await close_poll(database, **SCOPE, poll_id=poll.id, user_id=21)
    assert (await close_poll(database, **SCOPE, poll_id=poll.id, user_id=20)).status == "closed"
    assert await list_polls(database, **SCOPE) == []
    with pytest.raises(PollError, match="已经结束"):
        await cast_vote(database, **SCOPE, poll_id=poll.id, user_id=21, option_number=1)
    assert (await close_poll(database, **SCOPE, poll_id=poll.id, user_id=20)).status == "closed"
    second = await new_poll(database, request_id="second")
    assert (await close_poll(
        database, **SCOPE, poll_id=second.id, user_id=999, is_manager=True,
    )).status == "closed"


async def test_concurrent_closing_and_vote_keeps_closed_state(database):
    poll = await new_poll(database)
    results = await asyncio.gather(
        cast_vote(database, **SCOPE, poll_id=poll.id, user_id=21, option_number=1),
        close_poll(database, **SCOPE, poll_id=poll.id, user_id=20),
        return_exceptions=True,
    )
    assert not isinstance(results[1], Exception)
    result = await get_poll(database, **SCOPE, poll_id=poll.id)
    assert result.status == "closed"
    assert result.counts in ((0, 0), (1, 0))


@pytest.fixture
def plugin(monkeypatch, database):
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.plugins import group_polls

    monkeypatch.setattr(group_polls, "get_community_settings", lambda: CommunitySettings())
    monkeypatch.setattr(group_polls, "get_economy_database", lambda: database)
    monkeypatch.setattr(group_polls, "get_bots", lambda: {})
    return group_polls


def test_explicit_commands_only_and_bot_filters(plugin, monkeypatch):
    for text in ("发起投票 题|甲|乙", "/投票 1 2", "投票结果 1", "投票列表", "结束投票 1"):
        assert plugin.is_poll_command(event(text))
    for text in ("来投票吧", "他说投票", "投票结果怎么样", "投票1 2", "投票列表啊"):
        assert not plugin.is_poll_command(event(text))
    assert not plugin.is_poll_command(event(user_id=99))
    assert not plugin.is_poll_command(event(is_bot=True))
    monkeypatch.setattr(plugin, "get_bots", lambda: {"20": object()})
    assert not plugin.is_poll_command(event())
    monkeypatch.setattr(plugin, "get_bots", lambda: {})
    private = PrivateMessageEvent(
        time=1, self_id=99, post_type="message", message_type="private", sub_type="friend",
        user_id=20, message_id=1, message=Message("投票列表"), raw_message="投票列表", font=0,
        sender={"user_id": 20},
    )
    assert not plugin.is_poll_command(private)
    assert not plugin.is_poll_command(event(Message("投票列表") + MessageSegment.image("x")))
    monkeypatch.setattr(plugin, "get_community_settings", lambda: replace(
        CommunitySettings(), polls_enabled=False,
    ))
    assert not plugin.is_poll_command(event())


async def test_plugin_commands_and_plaintext_no_cq_injection(plugin, database, monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(plugin.group_poll, "send", send)
    await plugin.handle_poll_command(event("发起投票 [CQ:at,qq=all] | 甲 | 乙"))
    segment = send.call_args.args[0]
    assert segment.type == "text"
    assert "[CQ:at,qq=all]" in segment.data["text"]
    poll = (await list_polls(database, **SCOPE))[0]
    assert "已选择第 2 项" in await plugin._run_command(event(f"/投票 {poll.id} 2"))
    assert "1 票" in await plugin._run_command(event(f"投票结果 {poll.id}"))
    assert f"#{poll.id}" in await plugin._run_command(event("投票列表"))
    assert "已结束" in await plugin._run_command(event(f"结束投票 {poll.id}"))
    assert "已结束" in format_poll(await get_poll(database, **SCOPE, poll_id=poll.id))


@pytest.mark.parametrize("user_id,role,allowed", [
    (20, "member", True), (21, "member", False), (21, "admin", True),
    (21, "owner", True), (2448821316, "member", True),
])
async def test_plugin_end_authorization_keeps_global_admin(
    plugin, database, user_id, role, allowed,
):
    poll = await new_poll(database)
    command = event(f"结束投票 {poll.id}", user_id=user_id, role=role)
    if allowed:
        assert "已结束" in await plugin._run_command(command)
    else:
        with pytest.raises(PollError, match="只有"):
            await plugin._run_command(command)


async def test_plugin_configured_limit_and_invalid_usage(plugin, monkeypatch):
    monkeypatch.setattr(plugin, "get_community_settings", lambda: replace(
        CommunitySettings(), polls_max_active_per_group=1,
    ))
    await plugin._run_command(event())
    with pytest.raises(PollError, match="最多同时进行 1"):
        await plugin._run_command(event(message_id=2))
    for text in ("投票", "投票 1", "投票 1 2 3", "投票结果", "投票列表 1", "发起投票"):
        assert await plugin._run_command(event(text)) == plugin.USAGE
    with pytest.raises(PollError, match="过长"):
        await plugin._run_command(event("发起投票 " + "题" * 801))


async def test_failed_operation_and_failed_send_do_not_escape(plugin, monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(plugin.group_poll, "send", send)
    await plugin.handle_poll_command(event("投票 -1 2"))
    assert "正整数" in send.call_args.args[0].data["text"]
    monkeypatch.setattr(plugin, "_run_command", AsyncMock(side_effect=RuntimeError("database")))
    await plugin.handle_poll_command(event())
    assert "操作失败" in send.call_args.args[0].data["text"]
    send.side_effect = RuntimeError("send failure")
    await plugin.handle_poll_command(event())


async def test_real_dispatch_blocks_other_chat_handlers(plugin, monkeypatch):
    import nonebot.message as dispatch

    observer = nonebot.on_message(priority=90, block=False)
    seen = []

    @observer.handle()
    async def later_handler(event: GroupMessageEvent):
        seen.append(event.message_id)

    monkeypatch.setattr(dispatch, "matchers", {10: [plugin.group_poll], 90: [observer]})
    for name in ("_event_preprocessors", "_event_postprocessors",
                 "_run_preprocessors", "_run_postprocessors"):
        monkeypatch.setattr(dispatch, name, set())
    bot = Bot(Adapter(nonebot.get_driver()), "99")
    send = AsyncMock()
    monkeypatch.setattr(bot, "send", send)
    try:
        await dispatch.handle_event(bot, event())
        assert send.await_count == 1
        assert not seen
        monkeypatch.setattr(plugin, "get_community_settings", lambda: replace(
            CommunitySettings(), polls_enabled=False,
        ))
        await dispatch.handle_event(bot, event())
        assert send.await_count == 1
        assert seen == [1]
    finally:
        observer.destroy()
