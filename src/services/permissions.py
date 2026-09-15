"""Shared authorization rules for privileged bot commands."""

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from src.config import get_app_settings


def is_bot_admin(event: MessageEvent) -> bool:
    """Return whether the sender is a cross-group bot administrator."""
    return event.user_id in get_app_settings().admin_ids


def is_group_manager(event: GroupMessageEvent) -> bool:
    """Global admins retain manager rights in every group."""
    return is_bot_admin(event) or event.sender.role in {"owner", "admin"}

