import random
from dataclasses import replace
from unittest.mock import AsyncMock

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import Adapter, Bot, GroupMessageEvent, Message
from nonebot.exception import FinishedException

from src import config
from src.config import CommunitySettings, get_community_settings
from src.services.group_choices import ChoiceError, choose_one, parse_choices, shuffle_choices


def test_choice_and_shuffle_only_use_unique_input():
    assert parse_choices("火锅 | 烧烤｜火锅 | 面条") == ("火锅", "烧烤", "面条")
    source = "火锅 | 烧烤 | 面条"
    assert choose_one(source, random.Random(1)) in {"火锅", "烧烤", "面条"}
    assert set(shuffle_choices(source, random.Random(1))) == {"火锅", "烧烤", "面条"}
    assert len(shuffle_choices(source)) == 3


@pytest.mark.parametrize("argument", ["", "只有一个", "a|a", "a||b", "a| ",
                                      "a|" + "b" * 61, "|".join(map(str, range(21))),
                                      "x" * 1501])
def test_bad_choices_are_rejected(argument):
    with pytest.raises(ChoiceError):
        choose_one(argument)


@pytest.fixture
def settings(monkeypatch, tmp_path):
    names = (
        "GROUP_CHOICES_ENABLED", "GROUP_POLLS_ENABLED", "GROUP_REMINDERS_ENABLED",
        "GROUP_POLLS_MAX_ACTIVE", "GROUP_REMINDER_POLL_SECONDS", "GROUP_REMINDER_MAX_PER_USER",
        "GROUP_REMINDER_MAX_PER_GROUP",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    get_community_settings.cache_clear()
    yield
    get_community_settings.cache_clear()


def test_community_defaults_and_environment(settings, monkeypatch):
    assert get_community_settings() == CommunitySettings()
    get_community_settings.cache_clear()
    monkeypatch.setenv("GROUP_CHOICES_ENABLED", "false")
    monkeypatch.setenv("GROUP_POLLS_MAX_ACTIVE", "8")
    monkeypatch.setenv("GROUP_REMINDER_MAX_PER_USER", "20")
    values = get_community_settings()
    assert not values.choices_enabled and values.polls_max_active_per_group == 8
    assert values.reminders_max_active_per_user == 20


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "61"])
def test_community_invalid_poll_interval(settings, monkeypatch, value):
    monkeypatch.setenv("GROUP_REMINDER_POLL_SECONDS", value)
    with pytest.raises(ValueError, match="GROUP_REMINDER_POLL_SECONDS"):
        get_community_settings()


def event(text, user_id=20):
    return GroupMessageEvent(
        time=1, self_id=99, post_type="message", message_type="group", sub_type="normal",
        message_id=1, group_id=100, user_id=user_id, message=Message(text),
        raw_message=text, font=0, sender={"user_id": user_id},
    )


@pytest.fixture
def plugin(monkeypatch, settings):
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.plugins import group_choices

    monkeypatch.setattr(group_choices, "get_bots", lambda: {})
    return group_choices


async def test_rule_does_not_capture_ordinary_chat_or_bots(plugin, monkeypatch):
    bot = Bot(Adapter(nonebot.get_driver()), "99")
    assert await plugin.choose.rule(bot, event("帮我选 a | b"), {})
    assert await plugin.choose.rule(bot, event("/帮我选 a | b"), {})
    assert not await plugin.choose.rule(bot, event("请帮我选 a | b"), {})
    assert not await plugin.choose.rule(bot, event("帮我选 a | b", user_id=99), {})
    monkeypatch.setattr(plugin, "get_community_settings", lambda: replace(
        CommunitySettings(), choices_enabled=False,
    ))
    assert not await plugin.choose.rule(bot, event("帮我选 a | b"), {})


async def test_plugin_outputs_plain_text_not_cq_injection(plugin, monkeypatch):
    monkeypatch.setattr(plugin, "choose_one", lambda _: "[CQ:at,qq=all]")
    monkeypatch.setattr(plugin.choose, "finish", AsyncMock(side_effect=FinishedException))
    with pytest.raises(FinishedException):
        await plugin.handle_choose(event("帮我选 a | b"))
    message = plugin.choose.finish.call_args.args[0]
    assert message.type == "text"
    assert "[CQ:at,qq=all]" in message.data["text"]
