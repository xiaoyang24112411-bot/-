from datetime import datetime, timedelta, timezone

import pytest

from src.config import AutoChatSettings
from src.services.ai_features.autochat import (
    RecentChatBuffer,
    get_autochat_state,
    set_autochat_enabled,
    should_sample_reply,
)
from src.services.ai_features.personas import WHALE_PERSONA, get_effective_persona, set_persona
from src.services.economy.database import EconomyDatabase


def settings(**overrides) -> AutoChatSettings:
    values = {
        "minimum_messages": 3,
        "context_messages": 12,
        "trigger_percent": 10,
        "context_ttl_seconds": 1200,
        "quiet_start_hour": 0,
        "quiet_end_hour": 7,
    }
    values.update(overrides)
    return AutoChatSettings(**values)


@pytest.mark.asyncio
async def test_autochat_switch(tmp_path):
    database = EconomyDatabase(tmp_path / "autochat.sqlite3")

    state = await get_autochat_state(database, 100)
    assert not state.enabled

    state = await set_autochat_enabled(database, 100, True, 2448821316)
    assert state.enabled
    assert state.updated_by == 2448821316
    state = await set_autochat_enabled(database, 100, False, 2448821316)
    assert not state.enabled


def test_recent_context_and_sampling():
    buffer = RecentChatBuffer(maximum_messages=5)
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    buffer.append(1, 10, "甲", "第一句", now=now - timedelta(minutes=30))
    buffer.append(1, 10, "甲", "你们觉得呢？", now=now)
    buffer.append(1, 20, "乙", "我觉得可以", now=now)
    buffer.append(1, 30, "丙", "为什么呢？", now=now)
    lines = buffer.recent(1, limit=5, ttl_seconds=1200, now=now)
    assert [line.text for line in lines] == ["你们觉得呢？", "我觉得可以", "为什么呢？"]
    assert should_sample_reply(lines, settings(), china_hour=20, random_value=lambda: 0.19)
    assert not should_sample_reply(lines, settings(), china_hour=1, random_value=lambda: 0)


def test_context_expires_inactive_groups_and_can_be_cleared():
    buffer = RecentChatBuffer()
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    buffer.append(1, 10, "甲", "过期的聊天", now=now - timedelta(minutes=30))
    buffer.append(2, 20, "乙", "新的聊天", now=now)
    assert buffer.recent(2, limit=0, ttl_seconds=1200, now=now) == ()
    assert 1 not in buffer._lines
    buffer.clear(2)
    assert buffer.recent(2, limit=5, ttl_seconds=1200, now=now) == ()


def test_bot_does_not_count_as_second_group_participant():
    buffer = RecentChatBuffer()
    buffer.append(1, 10, "甲", "第一句")
    buffer.append(1, 99, "小鲸鱼", "回答")
    buffer.append(1, 10, "甲", "下一句？")
    lines = buffer.recent(1, limit=5, ttl_seconds=1200)
    assert not should_sample_reply(
        lines, settings(minimum_messages=2), china_hour=20, bot_id=99, random_value=lambda: 0
    )


def test_empty_context_never_samples_a_reply():
    assert not should_sample_reply((), settings(minimum_messages=0), china_hour=20)


@pytest.mark.asyncio
async def test_whale_persona_is_always_the_base(tmp_path):
    database = EconomyDatabase(tmp_path / "persona.sqlite3")
    default = await get_effective_persona(database, 1, 10)
    assert default == WHALE_PERSONA
    await set_persona(database, 1, 10, "说话再简洁一点")
    effective = await get_effective_persona(database, 1, 10)
    assert "小鲸鱼" in effective
    assert "说话再简洁一点" in effective
