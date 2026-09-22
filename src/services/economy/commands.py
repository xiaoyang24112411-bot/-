"""Small OneBot message parsers shared by economy plugins."""

import re

from nonebot.adapters.onebot.v11 import GroupMessageEvent

from .errors import EconomyError


def parse_positive_integers(argument: str, count: int) -> tuple[int, ...]:
    """Reject signs, decimals and extra text instead of silently changing amounts."""
    parts = argument.split()
    if len(parts) != count or any(
        not re.fullmatch(r"[0-9]{1,19}", part) for part in parts
    ):
        raise EconomyError("请输入正确数量的正整数，不能包含负号、小数或其他文字。")
    values = tuple(int(part) for part in parts)
    if any(value <= 0 or value > 2**63 - 1 for value in values):
        raise EconomyError("积分和份数必须是有效范围内的正整数。")
    return values


def command_text(event: GroupMessageEvent, command: str) -> str | None:
    text = event.get_plaintext().strip()
    matched = re.match(rf"^/?{re.escape(command)}(?:\s+(.*))?$", text, re.DOTALL)
    return matched.group(1).strip() if matched and matched.group(1) else "" if matched else None


def mentioned_user(event: GroupMessageEvent) -> int | None:
    for segment in event.get_message():
        if segment.type == "at" and str(segment.data.get("qq", "")) != "all":
            try:
                return int(segment.data["qq"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


def message_request_id(event: GroupMessageEvent, action: str) -> str:
    return f"{action}:{event.group_id}:{event.message_id}"


def is_group_owner(event: GroupMessageEvent) -> bool:
    return event.sender.role == "owner"
