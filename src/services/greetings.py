"""Exact greeting recognition and process-local, race-safe reply reservations."""

import re
import time
import unicodedata
from collections.abc import Callable, Iterable
from typing import Literal

from nonebot.adapters.onebot.v11 import GroupMessageEvent

from src.config import GreetingSettings

GreetingKind = Literal["morning", "night"]


def _only_decoration(text: str) -> bool:
    # Keycap emoji include a digit; other digits/letters must not pass as decoration.
    text = re.sub(r"[0-9#*]\ufe0f?\u20e3", "", text)
    return all(
        character.isspace()
        or unicodedata.category(character).startswith(("P", "S"))
        or character in "\ufe0e\ufe0f\u200d"
        or 0xE0020 <= ord(character) <= 0xE007F  # emoji flag tag sequences
        for character in text
    )


def match_greeting(text: str, settings: GreetingSettings) -> GreetingKind | None:
    text = text.strip()
    for kind, words in (("morning", settings.morning_words), ("night", settings.night_words)):
        if any(text.startswith(word) and _only_decoration(text[len(word):]) for word in words):
            return kind
    return None


def classify_group_greeting(
    event, settings: GreetingSettings, connected_bot_ids: Iterable[str] = ()
) -> GreetingKind | None:
    if not settings.enabled or not isinstance(event, GroupMessageEvent):
        return None
    if settings.group_ids and event.group_id not in settings.group_ids:
        return None
    if (
        event.user_id == event.self_id
        or event.user_id in settings.ignored_user_ids
        or str(event.user_id) in connected_bot_ids
        or getattr(event.sender, "is_bot", False) is True
        or getattr(event, "is_bot", False) is True
    ):
        return None
    # Use the original segments: stripping @ / replies / images into plain text
    # could turn a message addressed to someone else into a greeting to the bot.
    parts: list[str] = []
    for segment in event.original_message:
        if segment.type == "text":
            parts.append(str(segment.data.get("text", "")))
        elif segment.type == "face":
            parts.append("🙂")  # Preserve position: 早[表情]安 must not match 早安.
        elif segment.type == "at" and str(segment.data.get("qq")) == str(event.self_id):
            continue
        else:
            return None
    return match_greeting("".join(parts), settings)


class GreetingCooldowns:
    """Reserve before awaiting send; cooldown starts only after a successful send.

    Designed for the project's single-process asyncio bot. Failed/cancelled sends
    release the reservation. Expired entries are pruned lazily; restart resets them.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.users: dict[tuple[int, int, GreetingKind], float] = {}
        self.groups: dict[int, float] = {}
        self.pending: set[int] = set()
        self._next_prune = 0.0

    def acquire(self, group_id: int, user_id: int, kind: GreetingKind) -> bool:
        now = self.clock()
        if now >= self._next_prune:
            self.users = {key: expiry for key, expiry in self.users.items() if expiry > now}
            self.groups = {key: expiry for key, expiry in self.groups.items() if expiry > now}
            self._next_prune = now + 60
        if (
            group_id in self.pending
            or self.groups.get(group_id, 0) > now
            or self.users.get((group_id, user_id, kind), 0) > now
        ):
            return False
        self.pending.add(group_id)
        return True

    def succeed(
        self, group_id: int, user_id: int, kind: GreetingKind, settings: GreetingSettings
    ) -> None:
        now = self.clock()
        self.users[(group_id, user_id, kind)] = now + settings.user_cooldown_seconds
        self.groups[group_id] = now + settings.group_cooldown_seconds

    def release(self, group_id: int) -> None:
        self.pending.discard(group_id)
