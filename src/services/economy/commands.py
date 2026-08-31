"""Small OneBot message parsers shared by economy plugins."""

import re

from nonebot.adapters.onebot.v11 import GroupMessageEvent


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
