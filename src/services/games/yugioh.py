"""YGOPRODeck v7 card lookup with a seven-day SQLite cache."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from src.services.economy.common import iso_time
from src.services.economy.database import EconomyDatabase
from src.services.economy.errors import EconomyError

API_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
CACHE_TTL = timedelta(days=7)
CHINESE_ALIASES = {
    "青眼白龙": "Blue-Eyes White Dragon",
    "青眼究极龙": "Blue-Eyes Ultimate Dragon",
    "黑魔导": "Dark Magician",
    "黑魔术师": "Dark Magician",
    "黑魔导女孩": "Dark Magician Girl",
    "真红眼黑龙": "Red-Eyes Black Dragon",
    "真红眼黑炎龙": "Red-Eyes Black Flare Dragon",
    "强欲之壶": "Pot of Greed",
    "死者苏生": "Monster Reborn",
    "栗子球": "Kuriboh",
    "欧贝利斯克的巨神兵": "Obelisk the Tormentor",
    "奥西里斯的天空龙": "Slifer the Sky Dragon",
    "太阳神之翼神龙": "The Winged Dragon of Ra",
}


@dataclass(frozen=True)
class YugiohCard:
    card_id: int
    name: str
    card_type: str
    description: str
    race: str
    attribute: str | None
    level: int | None
    attack: int | None
    defense: int | None
    archetype: str | None


def _parse_card(data: dict) -> YugiohCard:
    return YugiohCard(
        card_id=int(data["id"]),
        name=str(data["name"]),
        card_type=str(data.get("type", "未知")),
        description=str(data.get("desc", "暂无效果文本")),
        race=str(data.get("race", "未知")),
        attribute=str(data["attribute"]) if data.get("attribute") else None,
        level=int(data["level"]) if data.get("level") is not None else None,
        attack=int(data["atk"]) if data.get("atk") is not None else None,
        defense=int(data["def"]) if data.get("def") is not None else None,
        archetype=str(data["archetype"]) if data.get("archetype") else None,
    )


async def search_yugioh_card(
    database: EconomyDatabase,
    query: str,
    *,
    now: datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> YugiohCard:
    original_query = query.strip()
    if not original_query:
        raise EconomyError("请输入卡名或卡片密码。")
    if len(original_query) > 80:
        raise EconomyError("卡名太长，请控制在 80 个字符以内。")

    api_query = CHINESE_ALIASES.get(original_query, original_query)
    query_key = api_query.casefold()
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)

    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT response_json, fetched_at FROM yugioh_card_cache WHERE query_key = ?",
            (query_key,),
        )
        cached = await cursor.fetchone()
    if cached is not None:
        fetched_at = datetime.fromisoformat(cached["fetched_at"])
        if current - fetched_at <= CACHE_TTL:
            return _parse_card(json.loads(cached["response_json"]))

    params = (
        {"id": api_query} if api_query.isdigit() else {"fname": api_query, "num": 5, "offset": 0}
    )
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=15, follow_redirects=True)
    try:
        response = await http_client.get(API_URL, params=params)
        if response.status_code == 400:
            raise EconomyError("没有找到这张卡，请尝试英文卡名或卡片密码。")
        response.raise_for_status()
        cards = response.json().get("data", [])
        if not cards:
            raise EconomyError("没有找到这张卡，请换一个关键词。")
        card_data = cards[0]
    except EconomyError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise EconomyError("游戏王卡片数据库暂时不可用，请稍后再试。") from exc
    finally:
        if owns_client:
            await http_client.aclose()

    timestamp = iso_time(current)
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO yugioh_card_cache(query_key, response_json, fetched_at) "
            "VALUES (?, ?, ?) ON CONFLICT(query_key) DO UPDATE SET "
            "response_json = excluded.response_json, fetched_at = excluded.fetched_at",
            (query_key, json.dumps(card_data, ensure_ascii=False), timestamp),
        )
    return _parse_card(card_data)
