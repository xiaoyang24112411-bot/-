from nonebot.adapters.onebot.v11 import Message, MessageSegment

from src.services.petpet import (
    has_explicit_target,
    normalize_command_text,
    strip_optional_command_prefix,
)


def test_petpet_aliases() -> None:
    assert normalize_command_text("搓头 @某人") == ("搓 @某人", True)
    assert normalize_command_text("拍拍") == ("拍", True)
    assert normalize_command_text("拍头") == ("拍头", True)
    assert normalize_command_text("怎么说话的") == ("怎么说话的", True)
    assert normalize_command_text("咬 @某人") == ("啃 @某人", True)
    assert normalize_command_text("摸摸") == ("摸摸", True)
    assert normalize_command_text("拍拍手") == ("拍拍手", False)


def test_common_gif_commands_are_recognized() -> None:
    commands = {
        "亲亲": "亲亲",
        "贴贴": "贴贴",
        "蹭蹭": "蹭蹭",
        "啃": "啃",
        "抛": "抛",
        "滚": "滚",
        "锤": "锤",
        "吸": "吸",
        "鼓掌": "鼓掌",
        "拍头": "拍头",
        "挠头": "挠头",
        "抱大腿": "抱大腿",
        "踢球": "踢球",
    }

    for command, normalized in commands.items():
        assert normalize_command_text(command) == (normalized, True)


def test_optional_petpet_slash_is_stripped_for_legacy_matcher() -> None:
    assert strip_optional_command_prefix("/摸摸 自己") == "摸摸 自己"
    assert strip_optional_command_prefix("  /搓头 123456") == "  搓头 123456"
    assert strip_optional_command_prefix("摸摸 自己") == "摸摸 自己"


def test_petpet_target_detection() -> None:
    assert has_explicit_target(Message("摸摸 自己"), "摸摸 自己")
    assert has_explicit_target(Message("拍 123456"), "拍 123456")
    assert has_explicit_target(
        Message([MessageSegment.text("搓 "), MessageSegment.at(123456)]), "搓 "
    )
    assert has_explicit_target(Message("亲亲 自己"), "亲亲 自己")
    assert has_explicit_target(Message("小天使 自己"), "小天使 自己")
    assert has_explicit_target(Message("小天使 123456"), "小天使 123456")
    assert not has_explicit_target(Message("摸摸"), "摸摸")
    assert not has_explicit_target(Message("鼓掌"), "鼓掌")
    assert not has_explicit_target(Message("小天使"), "小天使")
