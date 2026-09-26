"""Small catalog helpers shared by avatar discovery and the blind box."""

import re
from collections.abc import Callable, Iterable
from typing import Any

from nonebot.adapters.onebot.v11 import Message

PAGE_SIZE = 18


def avatar_templates(memes: Iterable[Any], enabled: Callable[[str], bool]) -> list[Any]:
    """Only select enabled templates usable with one image and no extra text."""
    return [
        meme for meme in memes
        if meme.info.params.min_images == 1
        and meme.info.params.max_images >= 1
        and meme.info.params.min_texts == 0
        and meme.info.keywords
        and enabled(meme.key)
    ]


def avatar_target(argument: Message, sender_id: int) -> str:
    """Accept an optional single @ mention, numeric QQ or '自己'."""
    if any(segment.type not in {"text", "at"} for segment in argument):
        raise ValueError("用法：/头像盲盒 [@群友]，也可以填写 QQ 号；不填默认使用自己头像。")
    mentions = [str(segment.data.get("qq", "")) for segment in argument
                if segment.type == "at"]
    text = argument.extract_plain_text().strip()
    if not mentions and text in {"", "自己"}:
        return str(sender_id)
    candidates = mentions + ([text] if text else [])
    if len(candidates) != 1 or re.fullmatch(r"[0-9]{5,19}", candidates[0]) is None:
        raise ValueError("一次只能指定一位群友：/头像盲盒 @群友；不填默认使用自己头像。")
    if not 0 < int(candidates[0]) <= 2**63 - 1:
        raise ValueError("QQ 号格式不正确。")
    return candidates[0]


def catalog_page(memes: list[Any], argument: str, prefix: str) -> str:
    text = argument.strip()
    if text and re.fullmatch(r"[0-9]{1,4}", text) is None:
        return "用法：/头像模板 [页码]，例如 /头像模板 2。"
    page = int(text or "1")
    if not memes:
        return "本群目前没有已启用的单头像模板。"
    pages = (len(memes) + PAGE_SIZE - 1) // PAGE_SIZE
    if page < 1 or page > pages:
        return f"头像模板共有 {pages} 页，请输入 /头像模板 1 至 /头像模板 {pages}。"
    start = (page - 1) * PAGE_SIZE
    entries = [f"{index}. {prefix}{meme.info.keywords[0]}"
               for index, meme in enumerate(memes[start:start + PAGE_SIZE], start + 1)]
    return (
        f"本群可用头像模板（{page}/{pages} 页，共 {len(memes)} 个）\n"
        + "\n".join(entries)
        + "\n任选指令后加 @群友；不加默认自己。\n"
        + "发送 /头像盲盒 可随机生成；/头像模板 页码 可翻页。"
    )
