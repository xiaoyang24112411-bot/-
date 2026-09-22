"""Offline reminder storage, lifecycle, permissions and no-duplicate delivery tests."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment

from src.config import CommunitySettings
from src.services import group_reminders as service
from src.services.economy.database import EconomyDatabase
from src.services.group_reminders import (
    CLAIM_TIMEOUT,
    MAX_LATENESS,
    RETENTION,
    ReminderError,
    begin_reminder_send,
    cancel_reminder,
    claim_due_reminders,
    create_reminder,
    deliver_due_reminders,
    finish_reminder_send,
    format_due,
    list_reminders,
    maintain_reminders,
    parse_reminder,
)

NOW = int(datetime(2026, 9, 22, 0, 0, tzinfo=timezone.utc).timestamp())


@pytest.fixture
def database(tmp_path):
    return EconomyDatabase(tmp_path / "reminders.sqlite3")


async def add(database, request_id="message-1", **kwargs):
    arguments = dict(
        bot_id=99, group_id=100, user_id=20, request_id=request_id,
        due_at=NOW + 10, body="喝水", now=NOW,
    )
    arguments.update(kwargs)
    return await create_reminder(database, **arguments)


def fake_bot(bot_id=99, *, online=True):
    return SimpleNamespace(
        self_id=str(bot_id),
        get_status=AsyncMock(return_value={"online": online, "good": True}),
        send_group_msg=AsyncMock(return_value={"message_id": 123}),
    )


def event(text="提醒我 10分钟 喝水", *, user_id=20, group_id=100, role="member"):
    message = Message(text)
    return GroupMessageEvent(
        time=NOW, self_id=99, post_type="message", message_type="group",
        sub_type="normal", message_id=1, group_id=group_id, user_id=user_id,
        message=message, raw_message=str(message), font=0,
        sender={"user_id": user_id, "nickname": "测试群友", "role": role},
    )


@pytest.mark.parametrize("argument,delay", [
    ("5秒 喝水", 5), ("10秒钟后 喝水", 10), ("30分钟后 喝水", 1800),
    ("2小时 喝水", 7200), ("1天后 喝水", 86400), ("30天 喝水", 30 * 86400),
    (" 10 分 喝水 ", 600),
])
def test_relative_parser(argument, delay):
    assert parse_reminder(argument, now=NOW) == (NOW + delay, "喝水")


def test_absolute_beijing_and_multiline_body():
    due, body = parse_reminder("2026-09-23 08:00 开会\n准备材料", now=NOW)
    assert due == NOW + 86400
    assert body == "开会\n准备材料"
    assert format_due(due) == "2026-09-23 08:00:00"
    assert parse_reminder("2026-09-22 08:00:05 开会", now=NOW)[0] == NOW + 5


@pytest.mark.parametrize("argument", [
    "4秒 喝水", "0秒 喝水", "-5分钟 喝水", "1.5小时 喝水", "31天 喝水",
    "明天 喝水", "2026-09-22 07:59 开会", "2026-02-30 10:00 开会",
    "10分钟", "10分钟喝水", "999999999999天 喝水", "2026-09-23 25:00 开会",
    "10分钟 " + "a" * 501,
])
def test_ambiguous_invalid_or_unbounded_times_rejected(argument):
    with pytest.raises(ReminderError):
        parse_reminder(argument, now=NOW)


async def test_persistence_idempotency_and_account_scope(database):
    first = await add(database)
    replay = await add(database, due_at=NOW + 60, body="不应改写")
    assert first == replay
    restarted = EconomyDatabase(database.path)
    assert (await list_reminders(restarted, 99, 100, 20)) == [first]
    other_group = await add(database, group_id=101)
    other_bot = await add(database, bot_id=88)
    assert len({first.id, other_group.id, other_bot.id}) == 3
    assert not await list_reminders(database, 99, 100, 21)
    with pytest.raises(ReminderError):
        await add(database, user_id=21)


async def test_concurrent_idempotency_and_limits_are_atomic(database):
    duplicate = await asyncio.gather(*(add(database) for _ in range(5)))
    assert len({item.id for item in duplicate}) == 1
    results = await asyncio.gather(*(
        add(database, f"request-{i}", max_per_user=2) for i in range(5)
    ), return_exceptions=True)
    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert all(isinstance(item, ReminderError) for item in results if isinstance(item, Exception))
    with pytest.raises(ReminderError):
        await add(database, "other-user", user_id=21, max_per_group=2)
    # Same user's other group/bot remains independent; no economy balance was created.
    await add(database, "other-group", group_id=101, max_per_user=2)
    async with database.connect() as connection:
        cursor = await connection.execute("SELECT COUNT(*) FROM economy_accounts")
        assert (await cursor.fetchone())[0] == 0


async def test_cancel_permissions_cross_group_bot_and_repeat(database):
    item = await add(database)
    base = dict(reminder_id=item.id, bot_id=99, group_id=100, user_id=20, now=NOW + 1)
    for changed in ({"group_id": 101}, {"bot_id": 88}, {"user_id": 21}):
        with pytest.raises(ReminderError):
            await cancel_reminder(database, **(base | changed))
    assert await cancel_reminder(database, **(base | {"user_id": 21, "manager": True})) == (
        "cancelled"
    )
    assert await cancel_reminder(database, **base) == "cancelled"
    assert not await claim_due_reminders(database, [99], now=NOW + 20)


async def test_claim_is_atomic_bounded_and_only_connected_account(database):
    for i in range(23):
        await add(database, f"batch-{i}", max_per_user=100)
    await add(database, "other-account", bot_id=88)
    batch_a, batch_b = await asyncio.gather(
        claim_due_reminders(database, [99], now=NOW + 20),
        claim_due_reminders(database, [99], now=NOW + 20),
    )
    assert len(batch_a) <= 20 and len(batch_b) <= 20
    assert len(batch_a) + len(batch_b) == 23
    assert not ({item.id for item in batch_a} & {item.id for item in batch_b})
    assert not await claim_due_reminders(database, [], now=NOW + 20)
    assert (await list_reminders(database, 88, 100, 20))[0].status == "pending"


async def test_cancel_before_send_and_uncertain_cancel_does_not_claim_success(database):
    item = await add(database)
    await claim_due_reminders(database, [99], now=NOW + 20)
    assert await cancel_reminder(
        database, reminder_id=item.id, bot_id=99, group_id=100, user_id=20, now=NOW + 20,
    ) == "cancelled"
    assert not await begin_reminder_send(database, item.id, now=NOW + 21)
    second = await add(database, "second")
    await claim_due_reminders(database, [99], now=NOW + 20)
    assert await begin_reminder_send(database, second.id, now=NOW + 21)
    with pytest.raises(ReminderError, match="无法保证取消"):
        await cancel_reminder(
            database, reminder_id=second.id, bot_id=99, group_id=100, user_id=20,
        )
    await finish_reminder_send(database, second.id, sent=True, now=NOW + 22)
    assert (await list_reminders(database, 99, 100, 20))[0].status == "sent"


async def test_offline_skips_claim_then_restart_restores_delivery(database):
    await add(database)
    bot = fake_bot(online=False)
    assert await deliver_due_reminders(database, {"99": bot}, now=NOW + 20) == 0
    assert (await list_reminders(database, 99, 100, 20))[0].status == "pending"
    assert await deliver_due_reminders(database, {}, now=NOW + 20) == 0
    bot.get_status.return_value["online"] = True
    assert await deliver_due_reminders(
        EconomyDatabase(database.path), {"99": bot}, now=NOW + 21,
    ) == 1
    assert await deliver_due_reminders(database, {"99": bot}, now=NOW + 22) == 0
    bot.send_group_msg.assert_awaited_once()
    payload = bot.send_group_msg.call_args.kwargs
    assert payload["group_id"] == 100
    assert payload["message"][0] == MessageSegment.at(20)


async def test_future_due_is_not_sent_early(database):
    await add(database)
    bot = fake_bot()
    assert await deliver_due_reminders(database, {"99": bot}, now=NOW + 9) == 0
    bot.send_group_msg.assert_not_awaited()
    assert await deliver_due_reminders(database, {"99": bot}, now=NOW + 10) == 1


async def test_text_cannot_inject_other_mentions_or_cq(database):
    await add(database, body="[CQ:at,qq=all] [CQ:image,file=file:///private]")
    bot = fake_bot()
    assert await deliver_due_reminders(database, {"99": bot}, now=NOW + 20) == 1
    message = bot.send_group_msg.call_args.kwargs["message"]
    assert [segment.type for segment in message] == ["at", "text"]
    assert message[0].data["qq"] == "20"
    assert "[CQ:at,qq=all]" in message[1].data["text"]


async def test_send_error_and_timeout_fail_without_retry(database):
    await add(database)
    bot = fake_bot()
    bot.send_group_msg.side_effect = RuntimeError("do not log private contents")
    assert await deliver_due_reminders(database, {"99": bot}, now=NOW + 20) == 0
    assert (await list_reminders(database, 99, 100, 20))[0].status == "failed"
    assert await deliver_due_reminders(database, {"99": bot}, now=NOW + 21) == 0
    bot.send_group_msg.assert_awaited_once()
    await add(database, "timeout")

    async def hang(**kwargs):
        await asyncio.Event().wait()

    bot.send_group_msg.side_effect = hang
    assert await deliver_due_reminders(
        database, {"99": bot}, now=NOW + 20, send_timeout=0.01,
    ) == 0
    assert all(item.status == "failed" for item in await list_reminders(database, 99, 100, 20))


async def test_crashed_claims_are_failed_never_replayed(database):
    item = await add(database)
    await claim_due_reminders(database, [99], now=NOW + 20)
    await begin_reminder_send(database, item.id, now=NOW + 21)
    await maintain_reminders(database, now=NOW + 21 + CLAIM_TIMEOUT + 1)
    assert (await list_reminders(database, 99, 100, 20))[0].status == "failed"
    assert not await claim_due_reminders(database, [99], now=NOW + 200)


async def test_lateness_expiry_retention_and_active_record_survival(database):
    await add(database)
    bot = fake_bot()
    expired_at = NOW + 11 + MAX_LATENESS
    assert await deliver_due_reminders(database, {"99": bot}, now=expired_at) == 0
    assert (await list_reminders(database, 99, 100, 20))[0].status == "expired"
    await add(database, "future", now=expired_at + RETENTION, due_at=expired_at + RETENTION + 20)
    await maintain_reminders(database, now=expired_at + RETENTION + 1)
    records = await list_reminders(database, 99, 100, 20)
    assert len(records) == 1 and records[0].status == "pending"


@pytest.fixture
def plugin(monkeypatch, database):
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.plugins import group_reminders

    monkeypatch.setattr(nonebot, "get_bots", lambda: {})
    monkeypatch.setattr(group_reminders, "get_community_settings", lambda: CommunitySettings())
    monkeypatch.setattr(group_reminders, "get_economy_database", lambda: database)
    monkeypatch.setattr(group_reminders.reminder, "send", AsyncMock())
    monkeypatch.setattr(group_reminders, "polling_task", None)
    return group_reminders


async def test_plugin_exact_commands_self_and_group_filters(plugin, monkeypatch):
    assert plugin.is_reminder(event())
    assert plugin.is_reminder(event("/我的提醒"))
    assert plugin.is_reminder(event("/取消提醒 1"))
    for text in ("他说提醒我喝水", "提醒我以后", "我的提醒器", "你好"):
        assert not plugin.is_reminder(event(text))
    assert not plugin.is_reminder(event(user_id=99))
    assert not plugin.is_reminder(SimpleNamespace(user_id=20))
    known_bot_event = event()
    known_bot_event.sender.is_bot = True
    assert not plugin.is_reminder(known_bot_event)
    monkeypatch.setattr(nonebot, "get_bots", lambda: {"20": object()})
    assert not plugin.is_reminder(event())


async def test_plugin_create_list_cancel_plain_text_and_no_at_others(plugin, database):
    await plugin.handle_reminder(event("提醒我 10分钟 喝水"))
    response = plugin.reminder.send.call_args.args[0]
    assert response.type == "text" and "北京时间" in response.data["text"]
    item = (await list_reminders(database, 99, 100, 20))[0]
    await plugin.handle_reminder(event("我的提醒"))
    assert f"#{item.id}" in plugin.reminder.send.call_args.args[0].data["text"]
    await plugin.handle_reminder(event(f"取消提醒 {item.id}"))
    assert "已取消" in plugin.reminder.send.call_args.args[0].data["text"]
    await plugin.handle_reminder(event("提醒我 10分钟 " + MessageSegment.at("all")))
    assert "纯文字" in plugin.reminder.send.call_args.args[0].data["text"]


async def test_plugin_manager_and_permanent_admin_cancel(plugin, database):
    for sender, role in ((21, "admin"), (2448821316, "member")):
        item = await add(database, str(sender))
        await plugin.handle_reminder(event(f"取消提醒 {item.id}", user_id=sender, role=role))
        assert "已取消" in plugin.reminder.send.call_args.args[0].data["text"]


async def test_plugin_disabled_worker_and_send_failure_are_isolated(plugin, monkeypatch):
    monkeypatch.setattr(plugin, "get_community_settings", lambda: replace(
        CommunitySettings(), reminders_enabled=False,
    ))
    await plugin.handle_reminder(event())
    assert "暂未启用" in plugin.reminder.send.call_args.args[0].data["text"]
    assert await plugin._poll_once() == 0
    plugin.reminder.send.side_effect = RuntimeError("transport failure")
    await plugin.handle_reminder(event())  # Does not escape into other matchers.


async def test_worker_lifecycle_is_idempotent_and_cancelled_cleanly(plugin, monkeypatch):
    polled = asyncio.Event()

    async def once():
        polled.set()
        return 0

    monkeypatch.setattr(plugin, "_poll_once", once)
    await plugin.start_reminder_polling()
    task = plugin.polling_task
    await plugin.start_reminder_polling()
    assert plugin.polling_task is task
    await asyncio.wait_for(polled.wait(), timeout=1)
    await plugin.stop_reminder_polling()
    assert plugin.polling_task is None and task.done()
    await plugin.stop_reminder_polling()


async def test_cancellation_during_delivery_marks_unknown_no_retry(database):
    await add(database)
    bot = fake_bot()
    started = asyncio.Event()

    async def hang(**kwargs):
        started.set()
        await asyncio.Event().wait()

    bot.send_group_msg.side_effect = hang
    task = asyncio.create_task(deliver_due_reminders(database, {"99": bot}, now=NOW + 20))
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await list_reminders(database, 99, 100, 20))[0].status == "failed"
    assert not await claim_due_reminders(database, [99], now=NOW + 21)


async def test_offline_probe_failure_leaves_pending(database):
    await add(database)
    bot = fake_bot()
    bot.get_status.side_effect = RuntimeError("no API available")
    assert await service.deliver_due_reminders(database, {"99": bot}, now=NOW + 20) == 0
    assert (await list_reminders(database, 99, 100, 20))[0].status == "pending"
    bot.send_group_msg.assert_not_awaited()
