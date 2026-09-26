from types import SimpleNamespace

import pytest
from nonebot.adapters.onebot.v11 import Message, MessageSegment

from src.services.meme_catalog import avatar_target, avatar_templates, catalog_page


def template(key, *, min_images=1, max_images=1, min_texts=0):
    return SimpleNamespace(key=key, info=SimpleNamespace(
        keywords=[f"模板{key}"], params=SimpleNamespace(
            min_images=min_images, max_images=max_images, min_texts=min_texts,
        ),
    ))


def test_avatar_pool_excludes_disabled_and_extra_required_parameters():
    memes = [
        template("simple"), template("disabled"), template("pair", min_images=2),
        template("caption", min_texts=1), template("text_only", min_images=0, max_images=0),
        template("optional_second", max_images=2),
    ]
    enabled = lambda key: key != "disabled"  # noqa: E731
    assert [meme.key for meme in avatar_templates(memes, enabled)] == [
        "simple", "optional_second",
    ]
    assert avatar_templates(memes, lambda key: False) == []


def test_avatar_target_supports_self_and_one_target_without_ambiguity():
    assert avatar_target(Message(), 123456) == "123456"
    assert avatar_target(Message(" 自己 "), 123456) == "123456"
    assert avatar_target(Message(" 654321 "), 123456) == "654321"
    assert avatar_target(Message(MessageSegment.at(654321)), 123456) == "654321"
    invalid = [
        MessageSegment.at("all"),
        MessageSegment.at(654321) + MessageSegment.at(765432),
        MessageSegment.at(654321) + " 765432",
        MessageSegment.image("https://example.com/a.png"),
        "他说要看头像", "9999999999999999999",
    ]
    for message in invalid:
        with pytest.raises(ValueError):
            avatar_target(Message(message), 123456)


def test_catalog_pagination_and_configured_prefix():
    memes = [template(str(index)) for index in range(20)]
    result = catalog_page(memes, "2", "!")
    assert "2/2" in result
    assert "19. !模板18" in result and "20. !模板19" in result
    assert "!模板0" not in result
    assert "用法" in catalog_page(memes, "文本", "#")
    assert "共有 2 页" in catalog_page(memes, "0", "#")
    assert "共有 2 页" in catalog_page(memes, "3", "#")
    assert "没有已启用" in catalog_page([], "1", "#")
