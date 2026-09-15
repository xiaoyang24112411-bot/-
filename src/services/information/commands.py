"""Pure parsers for information-query commands."""

import re


def parse_fuel_region(text: str) -> str | None:
    """Return the requested region, accepting canonical and compact wording."""
    normalized = text.strip()
    for command in ("今日油价", "每日油价"):
        matched = re.fullmatch(rf"/?{command}(?:\s+(.*))?", normalized, re.DOTALL)
        if matched:
            return (matched.group(1) or "").strip()

    compact = re.fullmatch(r"/?(?:今日|每日)(.+?)油价", normalized, re.DOTALL)
    if compact:
        return compact.group(1).strip()
    return None


def parse_hot_search_platform(text: str) -> str | None:
    """Return the optional platform from a hot-search command."""
    normalized = text.strip()
    for command in ("热搜查询", "热搜"):
        matched = re.fullmatch(rf"/?{command}(?:\s+(.*))?", normalized, re.DOTALL)
        if matched:
            return (matched.group(1) or "").strip()
    return None
