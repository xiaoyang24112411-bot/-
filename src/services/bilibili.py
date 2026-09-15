"""Bilibili subscription client and persistence."""

from dataclasses import dataclass

import httpx

from src.config import SubscriptionSettings
from src.services.economy.common import iso_time
from src.services.economy.database import EconomyDatabase


class BilibiliError(RuntimeError):
    """Raised when Bilibili state cannot be queried."""


@dataclass(frozen=True)
class BilibiliState:
    uid: int
    display_name: str
    dynamic_id: str
    dynamic_text: str
    dynamic_url: str
    live_status: int
    live_title: str
    live_url: str


@dataclass(frozen=True)
class BilibiliSubscription:
    group_id: int
    uid: int
    display_name: str
    last_dynamic_id: str
    last_live_status: int


def _headers(settings: SubscriptionSettings) -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/128 Safari/537.36"
        ),
        "Referer": "https://space.bilibili.com/",
    }
    if settings.bilibili_sessdata:
        headers["Cookie"] = f"SESSDATA={settings.bilibili_sessdata}"
    return headers


def _api_data(payload: object) -> object:
    if not isinstance(payload, dict) or payload.get("code") != 0:
        message = payload.get("message") if isinstance(payload, dict) else "返回格式错误"
        raise BilibiliError(f"B站接口暂时不可用：{message}")
    return payload.get("data")


async def fetch_bilibili_state(uid: int, settings: SubscriptionSettings) -> BilibiliState:
    if uid <= 0:
        raise BilibiliError("UID 必须是正整数。")
    try:
        async with httpx.AsyncClient(
            timeout=20, headers=_headers(settings), follow_redirects=True
        ) as client:
            dynamic_response = await client.get(
                f"{settings.bilibili_api_base_url}/x/polymer/web-dynamic/v1/feed/space",
                params={"host_mid": str(uid)},
            )
            dynamic_response.raise_for_status()
            dynamic_data = _api_data(dynamic_response.json())
            live_response = await client.post(
                f"{settings.bilibili_live_api_base_url}/room/v1/Room/get_status_info_by_uids",
                data={"uids[]": str(uid)},
            )
            live_response.raise_for_status()
            live_data = _api_data(live_response.json())
    except BilibiliError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise BilibiliError("B站查询失败；若接口限制访客，请配置 BILIBILI_SESSDATA。") from exc

    items = dynamic_data.get("items", []) if isinstance(dynamic_data, dict) else []
    first = items[0] if items and isinstance(items[0], dict) else {}
    modules = first.get("modules", {}) if isinstance(first, dict) else {}
    author = modules.get("module_author", {}) if isinstance(modules, dict) else {}
    dynamic = modules.get("module_dynamic", {}) if isinstance(modules, dict) else {}
    description = dynamic.get("desc", {}) if isinstance(dynamic, dict) else {}
    major = dynamic.get("major", {}) if isinstance(dynamic, dict) else {}
    dynamic_text = str(description.get("text") or "").strip()
    if not dynamic_text and isinstance(major, dict):
        for block in major.values():
            if isinstance(block, dict) and block.get("title"):
                dynamic_text = str(block["title"]).strip()
                break
    dynamic_id = str(first.get("id_str") or first.get("id") or "")

    live_item = {}
    if isinstance(live_data, dict):
        live_item = live_data.get(str(uid)) or live_data.get(uid) or {}
    display_name = str(author.get("name") or live_item.get("uname") or f"UID {uid}")
    room_id = str(live_item.get("room_id") or "")
    return BilibiliState(
        uid=uid,
        display_name=display_name,
        dynamic_id=dynamic_id,
        dynamic_text=dynamic_text or "发布了新动态",
        dynamic_url=f"https://t.bilibili.com/{dynamic_id}" if dynamic_id else "",
        live_status=int(live_item.get("live_status") or 0),
        live_title=str(live_item.get("title") or "正在直播"),
        live_url=f"https://live.bilibili.com/{room_id}" if room_id else "",
    )


async def add_bilibili_subscription(
    database: EconomyDatabase,
    *,
    group_id: int,
    created_by: int,
    state: BilibiliState,
) -> None:
    now = iso_time()
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO bili_subscriptions"
            "(group_id, uid, display_name, last_dynamic_id, last_live_status, enabled, "
            "created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?) "
            "ON CONFLICT(group_id, uid) DO UPDATE SET display_name = excluded.display_name, "
            "last_dynamic_id = excluded.last_dynamic_id, "
            "last_live_status = excluded.last_live_status, enabled = 1, "
            "updated_at = excluded.updated_at",
            (
                group_id,
                state.uid,
                state.display_name,
                state.dynamic_id,
                state.live_status,
                created_by,
                now,
                now,
            ),
        )


async def list_bilibili_subscriptions(
    database: EconomyDatabase, group_id: int | None = None
) -> tuple[BilibiliSubscription, ...]:
    query = (
        "SELECT group_id, uid, display_name, last_dynamic_id, last_live_status "
        "FROM bili_subscriptions WHERE enabled = 1"
    )
    params: tuple[int, ...] = ()
    if group_id is not None:
        query += " AND group_id = ?"
        params = (group_id,)
    query += " ORDER BY group_id, uid"
    async with database.connect() as connection:
        cursor = await connection.execute(query, params)
        rows = await cursor.fetchall()
    return tuple(BilibiliSubscription(**dict(row)) for row in rows)


async def delete_bilibili_subscription(
    database: EconomyDatabase, group_id: int, uid: int
) -> bool:
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "DELETE FROM bili_subscriptions WHERE group_id = ? AND uid = ?", (group_id, uid)
        )
    return cursor.rowcount > 0


async def mark_bilibili_state(
    database: EconomyDatabase, group_id: int, state: BilibiliState
) -> None:
    async with database.transaction() as connection:
        await connection.execute(
            "UPDATE bili_subscriptions SET display_name = ?, last_dynamic_id = ?, "
            "last_live_status = ?, updated_at = ? WHERE group_id = ? AND uid = ?",
            (
                state.display_name,
                state.dynamic_id,
                state.live_status,
                iso_time(),
                group_id,
                state.uid,
            ),
        )
