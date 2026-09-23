"""Exercise matcher handlers without a live QQ connection or model requests."""

import asyncio
import time
from collections import Counter
from unittest.mock import AsyncMock

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment
from nonebot.exception import FinishedException

from src.config import AutoChatSettings, DeepSeekCostSettings
from src.services.ai_features import autochat as autochat_service
from src.services.ai_features.autochat import (
    AutoChatState,
    PeakAutochatState,
    RecentChatBuffer,
)
from src.services.deepseek_pricing import BillingPeriod
from src.services.economy.database import EconomyDatabase
from src.services.llm import DeepSeekError, DeepSeekReply


def event(message="hi", *, to_me=True, user_id=20, group_id=100, message_id=1):
    value = Message(message)
    return GroupMessageEvent(
        time=int(time.time()), self_id=99, post_type="message", message_type="group",
        sub_type="normal", message_id=message_id, group_id=group_id, user_id=user_id,
        message=value, original_message=value.copy(), raw_message=str(value), font=0,
        sender={"user_id": user_id, "nickname": "测试群友"}, to_me=to_me,
    )


@pytest.fixture
def plugin(monkeypatch):
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.plugins import ai_autochat

    monkeypatch.setattr(ai_autochat, "context_buffer", RecentChatBuffer())
    monkeypatch.setattr(ai_autochat, "enabled_cache", {100: (True, time.monotonic() + 60)})
    monkeypatch.setattr(ai_autochat, "switch_revisions", {})
    monkeypatch.setattr(ai_autochat, "mention_revisions", {})
    monkeypatch.setattr(ai_autochat, "switch_locks", {})
    monkeypatch.setattr(ai_autochat, "peak_switch_locks", {})
    monkeypatch.setattr(ai_autochat, "active_requests", Counter())
    monkeypatch.setattr(ai_autochat, "_peak_suspended", AsyncMock(return_value=False))
    monkeypatch.setattr(
        ai_autochat, "get_peak_autochat_state",
        AsyncMock(return_value=PeakAutochatState(None, None)),
    )
    monkeypatch.setattr(ai_autochat, "get_economy_database", lambda: None)
    monkeypatch.setattr(ai_autochat, "get_effective_persona", AsyncMock(return_value="小鲸鱼"))
    monkeypatch.setattr(ai_autochat, "get_deepseek_settings", lambda: None)
    monkeypatch.setattr(ai_autochat, "get_auto_chat_settings", lambda: AutoChatSettings(
        minimum_messages=3, context_messages=12, trigger_percent=100,
        context_ttl_seconds=1200, quiet_start_hour=0, quiet_end_hour=0,
    ))
    monkeypatch.setattr(ai_autochat, "ask_deepseek", AsyncMock(
        return_value=DeepSeekReply(text="你好", model="test")
    ))
    for matcher in (
        ai_autochat.mention_chat, ai_autochat.proactive_chat,
        ai_autochat.enable_autochat, ai_autochat.disable_autochat,
        ai_autochat.autochat_status, ai_autochat.enable_peak_autochat,
        ai_autochat.disable_peak_autochat, ai_autochat.peak_autochat_status,
    ):
        monkeypatch.setattr(matcher, "send", AsyncMock())
        monkeypatch.setattr(matcher, "finish", AsyncMock(side_effect=FinishedException))
    monkeypatch.setattr(ai_autochat, "set_autochat_enabled", AsyncMock())
    monkeypatch.setattr(ai_autochat, "set_peak_autochat_enabled", AsyncMock())
    return ai_autochat


async def test_mentions_after_adapter_strips_at_and_raw_fallback(plugin):
    assert await plugin._mention_rule(event())
    assert await plugin._mention_rule(event(MessageSegment.at(99) + "hi", to_me=False))
    assert not await plugin._mention_rule(event(MessageSegment.at("all"), to_me=False))
    assert not await plugin._mention_rule(event(user_id=99))


async def test_disabled_mentions_explain_how_to_enable(plugin):
    plugin.enabled_cache[100] = (False, time.monotonic() + 60)
    assert await plugin._mention_rule(event())
    with pytest.raises(FinishedException):
        await plugin.handle_mention_chat(event())
    notice = plugin.mention_chat.finish.call_args.args[0]
    assert "2448821316" in notice and "开启自主回答" in notice
    plugin.ask_deepseek.assert_not_awaited()


async def test_peak_mentions_do_not_call_model(plugin, monkeypatch):
    monkeypatch.setattr(plugin, "_peak_suspended", AsyncMock(return_value=True))
    with pytest.raises(FinishedException):
        await plugin.handle_mention_chat(event())
    assert "峰价" in plugin.mention_chat.finish.call_args.args[0]
    plugin.ask_deepseek.assert_not_awaited()


async def test_only_controller_can_change_peak_switch(plugin):
    with pytest.raises(FinishedException):
        await plugin.handle_enable_peak_autochat(event())
    plugin.set_peak_autochat_enabled.assert_not_awaited()


async def test_peak_commands_only_change_the_current_group(plugin):
    controller = event(user_id=2448821316, group_id=200)
    with pytest.raises(FinishedException):
        await plugin.handle_enable_peak_autochat(controller)
    plugin.set_peak_autochat_enabled.assert_awaited_with(None, 200, True, 2448821316)
    assert "本群" in plugin.enable_peak_autochat.finish.call_args.args[0]

    with pytest.raises(FinishedException):
        await plugin.handle_disable_peak_autochat(event(user_id=2448821316))
    plugin.set_peak_autochat_enabled.assert_awaited_with(None, 100, False, 2448821316)
    assert "本群" in plugin.disable_peak_autochat.finish.call_args.args[0]

    plugin.get_peak_autochat_state.return_value = PeakAutochatState(True, 2448821316)
    with pytest.raises(FinishedException):
        await plugin.handle_peak_autochat_status(controller)
    plugin.get_peak_autochat_state.assert_awaited_with(None, 200)
    assert "本群高峰期自主回答：已开启" in plugin.peak_autochat_status.finish.call_args.args[0]


@pytest.mark.asyncio
async def test_peak_policy_honors_each_group_and_environment_default(tmp_path, monkeypatch):
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.plugins import ai_autochat

    database = EconomyDatabase(tmp_path / "peak-policy.sqlite3")
    monkeypatch.setattr(ai_autochat, "get_economy_database", lambda: database)
    monkeypatch.setattr(
        ai_autochat, "get_deepseek_cost_settings", lambda: DeepSeekCostSettings(True)
    )
    monkeypatch.setattr(ai_autochat, "deepseek_billing_period", lambda: BillingPeriod.PEAK)

    assert await ai_autochat._peak_suspended(100)
    await autochat_service.set_peak_autochat_enabled(database, 100, True, 2448821316)
    assert not await ai_autochat._peak_suspended(100)
    assert await ai_autochat._peak_suspended(200)
    await autochat_service.set_peak_autochat_enabled(database, 100, False, 2448821316)
    assert await ai_autochat._peak_suspended(100)

    monkeypatch.setattr(
        ai_autochat, "get_deepseek_cost_settings", lambda: DeepSeekCostSettings(False)
    )
    assert not await ai_autochat._peak_suspended(200)  # no override: env fallback
    assert await ai_autochat._peak_suspended(100)  # explicit off overrides env
    monkeypatch.setattr(ai_autochat, "deepseek_billing_period", lambda: BillingPeriod.OFF_PEAK)
    assert not await ai_autochat._peak_suspended(100)


@pytest.mark.parametrize("proactive", [False, True])
async def test_turning_off_peak_during_model_request_blocks_reply(
    plugin, monkeypatch, proactive
):
    allowed = True
    started, release = asyncio.Event(), asyncio.Event()

    async def suspended(group_id):
        assert group_id == 100
        return not allowed

    async def set_peak(database, group_id, enabled, updated_by):
        nonlocal allowed
        assert (group_id, updated_by) == (100, 2448821316)
        allowed = enabled

    async def slow_reply(*args, **kwargs):
        started.set()
        await release.wait()
        return DeepSeekReply("峰价旧回复", "test")

    monkeypatch.setattr(plugin, "_peak_suspended", suspended)
    monkeypatch.setattr(plugin, "set_peak_autochat_enabled", AsyncMock(side_effect=set_peak))
    monkeypatch.setattr(plugin, "ask_deepseek", AsyncMock(side_effect=slow_reply))
    monkeypatch.setattr(plugin, "should_sample_reply", lambda *args, **kwargs: True)
    handler = plugin.handle_proactive_chat if proactive else plugin.handle_mention_chat
    task = asyncio.create_task(handler(event(to_me=not proactive)))
    await asyncio.wait_for(started.wait(), timeout=2)
    try:
        with pytest.raises(FinishedException):
            await plugin.handle_disable_peak_autochat(event(user_id=2448821316))
    finally:
        release.set()
        await asyncio.wait_for(task, timeout=2)

    if proactive:
        plugin.proactive_chat.send.assert_not_awaited()
    else:
        sent = str(plugin.mention_chat.send.call_args.args[0])
        assert "峰价" in sent and "峰价旧回复" not in sent


async def test_only_controller_can_change_switch(plugin):
    with pytest.raises(FinishedException):
        await plugin.handle_disable_autochat(event())
    plugin.set_autochat_enabled.assert_not_awaited()
    assert plugin.enabled_cache[100][0]


async def test_disable_and_reenable_drops_inflight_mention(plugin, monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_reply(*args, **kwargs):
        started.set()
        await release.wait()
        return DeepSeekReply("旧回复", "test")

    monkeypatch.setattr(plugin, "ask_deepseek", slow_reply)
    task = asyncio.create_task(plugin.handle_mention_chat(event()))
    await asyncio.wait_for(started.wait(), timeout=2)
    try:
        controller = event(user_id=2448821316)
        with pytest.raises(FinishedException):
            await plugin.handle_disable_autochat(controller)
        with pytest.raises(FinishedException):
            await plugin.handle_enable_autochat(controller)
    finally:
        release.set()
        await asyncio.wait_for(task, timeout=2)
    plugin.mention_chat.send.assert_not_awaited()
    assert not plugin.active_requests
    assert plugin.context_buffer.recent(100, limit=12, ttl_seconds=1200) == ()


async def test_proactive_requests_do_not_overlap_or_add_cooldown(plugin, monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_reply(*args, **kwargs):
        started.set()
        await release.wait()
        return DeepSeekReply("参与讨论", "test")

    model = AsyncMock(side_effect=slow_reply)
    monkeypatch.setattr(plugin, "ask_deepseek", model)
    monkeypatch.setattr(plugin, "should_sample_reply", lambda *args, **kwargs: True)
    task = asyncio.create_task(plugin.handle_proactive_chat(event(to_me=False)))
    await asyncio.wait_for(started.wait(), timeout=2)
    try:
        await plugin.handle_proactive_chat(event("第二条", to_me=False, message_id=2))
        assert model.await_count == 1
    finally:
        release.set()
        await asyncio.wait_for(task, timeout=2)
    assert not plugin.active_requests
    await plugin.handle_proactive_chat(event("第三条", to_me=False, message_id=3))
    assert model.await_count == 2
    assert plugin.proactive_chat.send.await_count == 2


async def test_disable_suppresses_inflight_proactive_reply(plugin, monkeypatch):
    async def disable_before_response(*args, **kwargs):
        with pytest.raises(FinishedException):
            await plugin.handle_disable_autochat(event(user_id=2448821316))
        return DeepSeekReply("不应发送", "test")

    monkeypatch.setattr(plugin, "ask_deepseek", disable_before_response)
    monkeypatch.setattr(plugin, "should_sample_reply", lambda *args, **kwargs: True)
    await plugin.handle_proactive_chat(event(to_me=False))
    plugin.proactive_chat.send.assert_not_awaited()
    assert not plugin.active_requests


async def test_mention_replaces_inflight_proactive_reply(plugin, monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_proactive(prompt, *args, **kwargs):
        if "明确 @" not in prompt:
            started.set()
            await release.wait()
        return DeepSeekReply("你好", "test")

    monkeypatch.setattr(plugin, "ask_deepseek", slow_proactive)
    monkeypatch.setattr(plugin, "should_sample_reply", lambda *args, **kwargs: True)
    task = asyncio.create_task(plugin.handle_proactive_chat(event(to_me=False)))
    await asyncio.wait_for(started.wait(), timeout=2)
    try:
        await plugin.handle_mention_chat(event(message_id=2))
    finally:
        release.set()
        await asyncio.wait_for(task, timeout=2)
    plugin.mention_chat.send.assert_awaited_once()
    plugin.proactive_chat.send.assert_not_awaited()
    assert not plugin.active_requests


async def test_slow_switch_read_cannot_restore_disabled_cache(plugin, monkeypatch):
    plugin.enabled_cache.clear()

    async def outdated_read(*args):
        with pytest.raises(FinishedException):
            await plugin.handle_disable_autochat(event(user_id=2448821316))
        return AutoChatState(True, 2448821316)

    monkeypatch.setattr(plugin, "get_autochat_state", outdated_read)
    assert not await plugin._enabled(100)
    assert not plugin.enabled_cache[100][0]


@pytest.mark.parametrize("proactive", [False, True])
async def test_model_failure_releases_inflight_request(plugin, monkeypatch, proactive):
    monkeypatch.setattr(
        plugin, "ask_deepseek", AsyncMock(side_effect=DeepSeekError("服务暂不可用"))
    )
    monkeypatch.setattr(plugin, "should_sample_reply", lambda *args, **kwargs: True)
    handler = plugin.handle_proactive_chat if proactive else plugin.handle_mention_chat
    await handler(event(to_me=not proactive))
    assert not plugin.active_requests
    if proactive:
        plugin.proactive_chat.send.assert_not_awaited()
    else:
        assert "服务暂不可用" in str(plugin.mention_chat.send.call_args.args[0])


@pytest.mark.parametrize("proactive", [False, True])
async def test_cancellation_releases_inflight_request(plugin, monkeypatch, proactive):
    started = asyncio.Event()

    async def waiting_reply(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(plugin, "ask_deepseek", waiting_reply)
    monkeypatch.setattr(plugin, "should_sample_reply", lambda *args, **kwargs: True)
    handler = plugin.handle_proactive_chat if proactive else plugin.handle_mention_chat
    task = asyncio.create_task(handler(event(to_me=not proactive)))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not plugin.active_requests


async def test_rapid_enable_disable_keeps_database_and_cache_in_order(
    plugin, monkeypatch, tmp_path
):
    database = EconomyDatabase(tmp_path / "switch-race.sqlite3")
    real_get = autochat_service.get_autochat_state
    assert not (await real_get(database, 100)).enabled
    first_committed, release_read = asyncio.Event(), asyncio.Event()
    disable_started, disable_write_started = asyncio.Event(), asyncio.Event()
    delayed = False

    async def paused_post_commit_read(*args):
        nonlocal delayed
        if not delayed:
            delayed = True
            first_committed.set()
            await release_read.wait()
        return await real_get(*args)

    async def tracked_write(db, group_id, enabled, updated_by):
        if not enabled:
            disable_write_started.set()
        return await autochat_service.set_autochat_enabled(db, group_id, enabled, updated_by)

    async def change(handler, *, started=None):
        if started is not None:
            started.set()
        with pytest.raises(FinishedException):
            await handler(event(user_id=2448821316))

    monkeypatch.setattr(autochat_service, "get_autochat_state", paused_post_commit_read)
    monkeypatch.setattr(plugin, "get_economy_database", lambda: database)
    monkeypatch.setattr(plugin, "set_autochat_enabled", tracked_write)
    plugin.context_buffer.append(100, 20, "群友", "关闭后应清理")
    enable_task = asyncio.create_task(change(plugin.handle_enable_autochat))
    tasks = [enable_task]
    try:
        await asyncio.wait_for(first_committed.wait(), timeout=2)
        assert (await real_get(database, 100)).enabled
        tasks.append(asyncio.create_task(change(
            plugin.handle_disable_autochat, started=disable_started
        )))
        await asyncio.wait_for(disable_started.wait(), timeout=2)
        # The second handler is running, but cannot write while the first
        # handler is between its real SQLite commit and cache update.
        assert not disable_write_started.is_set()
    finally:
        release_read.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
    assert not (await real_get(database, 100)).enabled
    assert not await plugin._enabled(100)
    assert plugin.switch_revisions[100] == 2
    assert plugin.context_buffer.recent(100, limit=12, ttl_seconds=1200) == ()
    assert not plugin.switch_locks[100].locked()
