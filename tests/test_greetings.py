import asyncio
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

from src import config
from src.config import GreetingSettings
from src.services.greetings import GreetingCooldowns, classify_group_greeting, match_greeting


def event(message="早安", *, user_id=20, group_id=100, sender_bot=False):
    value = Message(message)
    return GroupMessageEvent(
        time=1, self_id=99, post_type="message", message_type="group", sub_type="normal",
        message_id=1, group_id=group_id, user_id=user_id, message=value,
        raw_message=str(value), font=0,
        sender={"user_id": user_id, "nickname": "群友", "is_bot": sender_bot},
    )


@pytest.mark.parametrize("text,kind", [
    ("早安", "morning"), ("早上好！", "morning"), (" 早晨好 ☀️ ", "morning"),
    ("晚安", "night"), ("晚安～🌙😴", "night"), ("晚上好。", "night"),
    ("早安👨‍👩‍👧‍👦👍🏽", "morning"), ("晚安1️⃣", "night"),
])
def test_exact_greetings_with_trailing_decoration(text, kind):
    assert match_greeting(text, GreetingSettings()) == kind


@pytest.mark.parametrize("text", [
    "他说了晚安", "怎么还没说早安", "晚安了吗", "早安大家", "早安，今天去哪里",
    "晚安123", "早安\n晚安", "/早安", "早 安", "早🙂安", "🌞早安", "“晚安”", "",
])
def test_ordinary_chat_does_not_trigger(text):
    assert match_greeting(text, GreetingSettings()) is None


def test_custom_words_replies_and_defaults():
    settings = GreetingSettings()
    assert len(set(settings.morning_replies)) >= 5
    assert len(set(settings.night_replies)) >= 5
    assert any("本鲸" in reply or "小鲸鱼" in reply for reply in settings.morning_replies)
    assert any("本鲸" in reply or "小鲸鱼" in reply for reply in settings.night_replies)
    custom = replace(settings, morning_words=("早呀",), night_words=("好梦",))
    assert match_greeting("早呀！", custom) == "morning"
    assert match_greeting("好梦 🌙", custom) == "night"
    assert match_greeting("早安", custom) is None


def test_group_filter_self_and_known_bots():
    settings = GreetingSettings(group_ids=frozenset({100}), ignored_user_ids=frozenset({88}))
    assert classify_group_greeting(event(), settings) == "morning"
    assert classify_group_greeting(event(), replace(settings, enabled=False)) is None
    assert classify_group_greeting(event(group_id=101), settings) is None
    for user_id in (99, 88):
        assert classify_group_greeting(event(user_id=user_id), settings) is None
    assert classify_group_greeting(event(), settings, {"20": object()}) is None
    assert classify_group_greeting(event(sender_bot=True), settings) is None
    private = PrivateMessageEvent(
        time=1, self_id=99, post_type="message", message_type="private", sub_type="friend",
        user_id=20, message_id=1, message=Message("早安"), raw_message="早安", font=0,
        sender={"user_id": 20},
    )
    assert classify_group_greeting(private, settings) is None


def test_segment_positions_and_adapter_preprocessing():
    settings = GreetingSettings()
    assert classify_group_greeting(event("早安！" + MessageSegment.face(21)), settings) == "morning"
    assert classify_group_greeting(event("早" + MessageSegment.face(21) + "安"), settings) is None
    for prefix in (MessageSegment.image("x"), MessageSegment.at(20), MessageSegment.reply(5)):
        assert classify_group_greeting(event(prefix + "早安"), settings) is None
    value = event(MessageSegment.at(99) + " 晚安🌙")
    # The adapter may strip @ before matching; the original message stays intact.
    value.message = Message("晚安🌙")
    value.to_me = True
    assert classify_group_greeting(value, settings) == "night"
    quoted = event(MessageSegment.reply(5) + "晚安")
    quoted.message = Message("晚安")
    assert classify_group_greeting(quoted, settings) is None


def test_cooldown_boundaries_and_independent_users_groups_kinds():
    now = [100.0]
    cooldowns = GreetingCooldowns(lambda: now[0])
    settings = GreetingSettings(user_cooldown_seconds=1800, group_cooldown_seconds=60)
    assert cooldowns.acquire(1, 10, "morning")
    assert not cooldowns.acquire(1, 20, "night")  # pending send across all users/kinds
    now[0] = 110
    cooldowns.succeed(1, 10, "morning", settings)
    cooldowns.release(1)
    now[0] = 169.999
    assert not cooldowns.acquire(1, 20, "night")
    now[0] = 170
    assert cooldowns.acquire(1, 20, "night")
    cooldowns.release(1)
    assert cooldowns.acquire(1, 10, "night")  # different greeting kind
    cooldowns.release(1)
    assert cooldowns.acquire(2, 10, "morning")  # different group
    cooldowns.release(2)
    now[0] = 1909.999
    assert not cooldowns.acquire(1, 10, "morning")
    now[0] = 1910
    assert cooldowns.acquire(1, 10, "morning")
    cooldowns.release(1)
    now[0] = 1970  # lazy pruning runs at most once per minute
    assert cooldowns.acquire(1, 10, "morning")
    cooldowns.release(1)
    assert not cooldowns.users and not cooldowns.groups


def test_zero_cooldown_and_failed_reservation():
    settings = GreetingSettings(user_cooldown_seconds=0, group_cooldown_seconds=0)
    cooldowns = GreetingCooldowns(lambda: 100.0)
    assert cooldowns.acquire(1, 10, "morning")
    cooldowns.release(1)  # failure consumes no cooldown
    assert cooldowns.acquire(1, 10, "morning")
    cooldowns.succeed(1, 10, "morning", settings)
    cooldowns.release(1)
    assert cooldowns.acquire(1, 10, "morning")


@pytest.fixture
def clean_greeting_config(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    for name in (
        "ENABLED", "GROUP_IDS", "IGNORED_USER_IDS", "USER_COOLDOWN_SECONDS",
        "GROUP_COOLDOWN_SECONDS", "MORNING_WORDS", "NIGHT_WORDS",
        "MORNING_REPLIES", "NIGHT_REPLIES",
    ):
        monkeypatch.delenv("GREETING_" + name, raising=False)
    config.get_greeting_settings.cache_clear()
    yield
    config.get_greeting_settings.cache_clear()


def test_default_config(clean_greeting_config):
    assert config.get_greeting_settings() == GreetingSettings()


def test_env_file_and_process_override(clean_greeting_config, monkeypatch, tmp_path):
    env_file = tmp_path / "greeting.env"
    env_file.write_text(
        "GREETING_ENABLED=false\nGREETING_GROUP_IDS=100,200\n"
        "GREETING_USER_COOLDOWN_SECONDS=12\nGREETING_GROUP_COOLDOWN_SECONDS=3\n"
        'GREETING_MORNING_WORDS=\'["早呀", "早安"]\'\n'
        'GREETING_NIGHT_REPLIES=\'["好梦，明天见！", "晚安呀"]\'\n', encoding="utf-8",
    )
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.setenv("GREETING_ENABLED", "true")
    monkeypatch.setenv("GREETING_IGNORED_USER_IDS", "88，99 66")
    settings = config.get_greeting_settings()
    assert settings.enabled
    assert settings.group_ids == frozenset({100, 200})
    assert settings.ignored_user_ids == frozenset({88, 99, 66})
    assert settings.user_cooldown_seconds == 12 and settings.group_cooldown_seconds == 3
    assert settings.morning_words == ("早呀", "早安")
    assert settings.night_replies == ("好梦，明天见！", "晚安呀")


@pytest.mark.parametrize("name,value", [
    ("GREETING_MORNING_WORDS", "不是JSON"), ("GREETING_NIGHT_REPLIES", '"晚安"'),
    ("GREETING_NIGHT_REPLIES", "[]"), ("GREETING_NIGHT_REPLIES", '[" "]'),
    ("GREETING_NIGHT_REPLIES", "[5]"), ("GREETING_USER_COOLDOWN_SECONDS", "-1"),
    ("GREETING_GROUP_COOLDOWN_SECONDS", "1.5"), ("GREETING_GROUP_IDS", "100,not-an-id"),
    ("GREETING_NIGHT_WORDS", '["早安"]'),
])
def test_bad_config_fails_clearly(clean_greeting_config, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        config.get_greeting_settings()


@pytest.fixture
def plugin(monkeypatch, clean_greeting_config):
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.plugins import greetings

    monkeypatch.setattr(greetings, "settings", GreetingSettings(
        user_cooldown_seconds=1800, group_cooldown_seconds=60,
    ))
    monkeypatch.setattr(greetings, "cooldowns", GreetingCooldowns())
    monkeypatch.setattr(greetings, "get_bots", lambda: {})
    return greetings


async def test_reply_selection_and_success_cooldown(plugin, monkeypatch):
    bot = AsyncMock()
    monkeypatch.setattr(plugin.random, "choice", lambda choices: choices[-1])
    await plugin.handle_greeting(bot, event())
    segment = bot.send.call_args.args[1]
    assert segment.type == "text"
    assert segment.data["text"] == plugin.settings.morning_replies[-1]
    await plugin.handle_greeting(bot, event())
    await plugin.handle_greeting(bot, event("晚安", user_id=21))
    assert bot.send.await_count == 1
    await plugin.handle_greeting(bot, event("晚安", group_id=101))
    assert bot.send.call_args.args[1].data["text"] == plugin.settings.night_replies[-1]


@pytest.mark.parametrize("failure", [RuntimeError("send failed"), asyncio.TimeoutError()])
async def test_send_failure_releases_and_does_not_consume_cooldown(plugin, failure):
    bot = AsyncMock()
    bot.send.side_effect = failure
    await plugin.handle_greeting(bot, event())
    assert not plugin.cooldowns.pending and not plugin.cooldowns.users
    bot.send.side_effect = None
    await plugin.handle_greeting(bot, event())
    assert bot.send.await_count == 2


async def test_actual_send_timeout_is_bounded(plugin, monkeypatch):
    monkeypatch.setattr(plugin, "SEND_TIMEOUT_SECONDS", 0.01)
    bot = AsyncMock()

    async def hanging_send(*args):
        await asyncio.Event().wait()

    bot.send.side_effect = hanging_send
    await asyncio.wait_for(plugin.handle_greeting(bot, event()), timeout=1)
    assert not plugin.cooldowns.pending and not plugin.cooldowns.users


async def test_concurrent_events_send_once_and_cancellation_releases(plugin):
    entered, finish = asyncio.Event(), asyncio.Event()
    bot = AsyncMock()

    async def slow_send(*args):
        entered.set()
        await finish.wait()

    bot.send.side_effect = slow_send
    task = asyncio.create_task(plugin.handle_greeting(bot, event()))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        await plugin.handle_greeting(bot, event("晚安", user_id=21))
        assert bot.send.await_count == 1
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not plugin.cooldowns.pending and not plugin.cooldowns.users


@pytest.mark.parametrize("limited", [False, True])
@pytest.mark.parametrize("send_failed", [False, True])
async def test_real_dispatch_does_not_call_ai_or_block_other_observers(
    plugin, monkeypatch, send_failed, limited
):
    import nonebot.message as dispatch

    from src.plugins import ai_autochat

    if not limited:
        monkeypatch.setattr(plugin, "settings", GreetingSettings())

    observer = nonebot.on_message(priority=99, block=False)
    observed = []

    @observer.handle()
    async def record(event: GroupMessageEvent):
        observed.append(event.message_id)

    monkeypatch.setattr(dispatch, "matchers", {
        12: [plugin.greetings], 15: [ai_autochat.mention_chat],
        90: [ai_autochat.proactive_chat], 99: [observer],
    })
    for name in ("_event_preprocessors", "_event_postprocessors",
                 "_run_preprocessors", "_run_postprocessors"):
        monkeypatch.setattr(dispatch, name, set())
    monkeypatch.setattr(ai_autochat, "get_greeting_settings", lambda: plugin.settings)
    monkeypatch.setattr(ai_autochat, "_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(ai_autochat, "ask_deepseek", AsyncMock())
    bot = Bot(Adapter(nonebot.get_driver()), "99")
    send = AsyncMock(side_effect=RuntimeError("send failed") if send_failed else None)
    monkeypatch.setattr(bot, "send", send)
    value = event(MessageSegment.at(99) + " 早安！")
    value.message = Message("早安！")
    value.to_me = True
    try:
        await dispatch.handle_event(bot, value)
        await dispatch.handle_event(bot, value)  # cooldown hit must not fall through to AI
        assert send.await_count == (2 if send_failed or not limited else 1)
        assert observed == [1, 1]
        ai_autochat.ask_deepseek.assert_not_awaited()
        ai_autochat._enabled.assert_not_awaited()
        monkeypatch.setattr(plugin, "settings", replace(plugin.settings, enabled=False))
        assert await ai_autochat._mention_rule(value)  # switch off restores ordinary AI routing
    finally:
        observer.destroy()


async def test_default_no_cooldown_replies_to_repeated_and_concurrent_greetings(
    plugin, monkeypatch
):
    monkeypatch.setattr(plugin, "settings", GreetingSettings())
    entered, release = asyncio.Event(), asyncio.Event()
    bot = AsyncMock()

    async def send(*args):
        entered.set()
        await release.wait()

    bot.send.side_effect = send
    first = asyncio.create_task(plugin.handle_greeting(bot, event()))
    tasks = [first]
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        entered.clear()
        tasks.append(asyncio.create_task(plugin.handle_greeting(bot, event())))
        # A second event must enter send even while the first is still pending.
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert bot.send.await_count == 2
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)
    await plugin.handle_greeting(bot, event())
    await plugin.handle_greeting(bot, event("晚安", user_id=21))
    assert bot.send.await_count == 4
    assert not plugin.cooldowns.pending and not plugin.cooldowns.users
    assert not plugin.cooldowns.groups
