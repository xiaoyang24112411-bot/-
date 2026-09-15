"""Persistent RSS subscription storage and safe feed fetching."""

import asyncio
import ipaddress
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from src.services.economy.common import iso_time
from src.services.economy.database import EconomyDatabase


class SubscriptionError(RuntimeError):
    """Raised for invalid subscriptions or unavailable feeds."""


@dataclass(frozen=True)
class FeedEntry:
    entry_id: str
    title: str
    link: str


@dataclass(frozen=True)
class Feed:
    title: str
    entries: tuple[FeedEntry, ...]


@dataclass(frozen=True)
class RSSSubscription:
    id: int
    group_id: int
    feed_url: str
    title: str
    last_entry_id: str


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ET.Element, names: set[str]) -> str:
    for child in element:
        if _tag(child) in names and child.text:
            return child.text.strip()
    return ""


def parse_feed(content: bytes) -> Feed:
    if len(content) > 2 * 1024 * 1024:
        raise SubscriptionError("RSS 内容超过 2 MB，已拒绝处理。")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise SubscriptionError("该地址没有返回有效的 RSS/Atom XML。") from exc

    root_tag = _tag(root)
    if root_tag in {"rss", "rdf"}:
        channel = next((item for item in root.iter() if _tag(item) == "channel"), root)
        title = _child_text(channel, {"title"}) or "RSS 订阅"
        candidates = [item for item in root.iter() if _tag(item) == "item"]
    elif root_tag == "feed":
        channel = root
        title = _child_text(root, {"title"}) or "Atom 订阅"
        candidates = [item for item in root if _tag(item) == "entry"]
    else:
        raise SubscriptionError("无法识别该订阅源格式。")

    entries: list[FeedEntry] = []
    for item in candidates[:30]:
        entry_title = _child_text(item, {"title"}) or "无标题"
        entry_id = _child_text(item, {"guid", "id"})
        link = _child_text(item, {"link"})
        if not link:
            link_node = next((child for child in item if _tag(child) == "link"), None)
            if link_node is not None:
                link = str(link_node.attrib.get("href", "")).strip()
        entry_id = entry_id or link or entry_title
        entries.append(FeedEntry(entry_id[:500], entry_title[:300], link[:1000]))
    if not entries:
        raise SubscriptionError("订阅源中暂时没有文章。")
    return Feed(title[:200], tuple(entries))


async def _validate_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise SubscriptionError("RSS 地址必须是公开的 http/https URL。")
    try:
        port = parsed.port
    except ValueError as exc:
        raise SubscriptionError("RSS 地址端口格式不正确。") from exc
    if port not in {None, 80, 443}:
        raise SubscriptionError("RSS 地址只允许使用 80 或 443 端口。")
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            parsed.hostname,
            port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise SubscriptionError("无法解析 RSS 地址的域名。") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise SubscriptionError("RSS 地址不能指向本机、内网或保留网络。")
    return parsed.geturl()


async def fetch_feed(url: str, *, timeout: float = 20) -> Feed:
    current = await _validate_public_url(url)
    headers = {"User-Agent": "QQBot-RSS/1.0 (+NoneBot2)"}
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            for _ in range(4):
                response = await client.get(current, follow_redirects=False)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise SubscriptionError("RSS 服务返回了无效跳转。")
                    current = await _validate_public_url(urljoin(current, location))
                    continue
                response.raise_for_status()
                return parse_feed(response.content)
    except SubscriptionError:
        raise
    except httpx.HTTPError as exc:
        raise SubscriptionError("RSS 地址暂时无法访问。") from exc
    raise SubscriptionError("RSS 地址跳转次数过多。")


async def add_rss_subscription(
    database: EconomyDatabase,
    *,
    group_id: int,
    url: str,
    created_by: int,
    feed: Feed,
) -> RSSSubscription:
    now = iso_time()
    latest = feed.entries[0].entry_id
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO rss_subscriptions"
            "(group_id, feed_url, title, last_entry_id, enabled, created_by, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?, ?) ON CONFLICT(group_id, feed_url) DO UPDATE SET "
            "title = excluded.title, last_entry_id = excluded.last_entry_id, enabled = 1, "
            "updated_at = excluded.updated_at",
            (group_id, url.strip(), feed.title, latest, created_by, now, now),
        )
        cursor = await connection.execute(
            "SELECT id, group_id, feed_url, title, last_entry_id FROM rss_subscriptions "
            "WHERE group_id = ? AND feed_url = ?",
            (group_id, url.strip()),
        )
        row = await cursor.fetchone()
    assert row is not None
    return RSSSubscription(**dict(row))


async def list_rss_subscriptions(
    database: EconomyDatabase, group_id: int | None = None
) -> tuple[RSSSubscription, ...]:
    query = (
        "SELECT id, group_id, feed_url, title, last_entry_id FROM rss_subscriptions "
        "WHERE enabled = 1"
    )
    params: tuple[int, ...] = ()
    if group_id is not None:
        query += " AND group_id = ?"
        params = (group_id,)
    query += " ORDER BY group_id, id"
    async with database.connect() as connection:
        cursor = await connection.execute(query, params)
        rows = await cursor.fetchall()
    return tuple(RSSSubscription(**dict(row)) for row in rows)


async def delete_rss_subscription(
    database: EconomyDatabase, group_id: int, identifier: str
) -> bool:
    value = identifier.strip()
    if not value:
        raise SubscriptionError("用法：/rss del 订阅编号或链接")
    async with database.transaction() as connection:
        if value.isdigit():
            cursor = await connection.execute(
                "DELETE FROM rss_subscriptions WHERE group_id = ? AND id = ?",
                (group_id, int(value)),
            )
        else:
            cursor = await connection.execute(
                "DELETE FROM rss_subscriptions WHERE group_id = ? AND feed_url = ?",
                (group_id, value),
            )
    return cursor.rowcount > 0


async def mark_rss_entry(
    database: EconomyDatabase, subscription_id: int, entry_id: str, title: str
) -> None:
    async with database.transaction() as connection:
        await connection.execute(
            "UPDATE rss_subscriptions SET last_entry_id = ?, title = ?, updated_at = ? "
            "WHERE id = ?",
            (entry_id, title, iso_time(), subscription_id),
        )
