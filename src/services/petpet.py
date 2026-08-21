"""Pure message normalization helpers for petpet commands."""

import re

from nonebot.adapters.onebot.v11 import Message

ALIASES = {
    "搓头": "搓",
    "拍拍": "拍",
    "咬": "啃",
}
COMMAND_PATTERN = re.compile(
    r"^(?P<leading>\s*)(?P<prefix>/?)"
    r"(?P<command>怎么说话的|抱大腿|风车转|"
    r"摸摸|摸头|搓头|拍拍|亲亲|贴贴|蹭蹭|鼓掌|拍头|挠头|踢球|"
    r"摸|rua|搓|拍|亲|贴|蹭|啃|咬|抛|掷|滚|锤|吸|嗦)(?=\s|$)",
    re.IGNORECASE,
)


def normalize_command_text(text: str) -> tuple[str, bool]:
    """Normalize supported aliases and report whether this is a petpet command."""
    matched = COMMAND_PATTERN.match(text)
    if not matched:
        return text, False
    command = matched.group("command")
    replacement = ALIASES.get(command, command)
    normalized = text[: matched.start("command")] + replacement + text[matched.end("command") :]
    return normalized, True


def strip_optional_command_prefix(text: str) -> str:
    """Strip one optional slash after leading whitespace for the legacy matcher."""
    matched = re.match(r"^(?P<leading>\s*)/(?P<command>\S.*)$", text)
    if not matched:
        return text
    return matched.group("leading") + matched.group("command")


def has_explicit_target(message: Message, command_text: str) -> bool:
    """Check for an @ mention, image, QQ number, or the explicit word '自己'."""
    for segment in message[1:]:
        if segment.type in {"at", "image"}:
            return True

    tokens = command_text.split()
    return "自己" in tokens or any(token.isdigit() and 5 <= len(token) <= 11 for token in tokens)
