"""Typed clients for the open-source 60s API."""

from dataclasses import dataclass

import httpx

from .errors import InformationError


@dataclass(frozen=True)
class FuelItem:
    name: str
    price_description: str


@dataclass(frozen=True)
class FuelPrice:
    region: str
    items: tuple[FuelItem, ...]
    trend: str
    updated: str
    source_url: str


@dataclass(frozen=True)
class DailyBrief:
    date: str
    weekday: str
    news: tuple[str, ...]
    tip: str
    image_url: str
    source_url: str


@dataclass(frozen=True)
class HotItem:
    title: str
    hot_value: str
    link: str


HOT_PLATFORMS = {
    "微博": "weibo",
    "抖音": "douyin",
    "知乎": "zhihu",
    "头条": "toutiao",
    "哔哩哔哩": "bili",
    "B站": "bili",
    "小红书": "rednote",
}


async def _get_data(
    base_url: str,
    endpoint: str,
    *,
    params: dict[str, str] | None = None,
    timeout: float = 20,
    client: httpx.AsyncClient | None = None,
):
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        response = await http_client.get(f"{base_url.rstrip('/')}/{endpoint}", params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("code") != 200:
            message = (
                payload.get("message", "上游接口返回异常")
                if isinstance(payload, dict)
                else "上游接口返回异常"
            )
            raise InformationError(str(message))
        return payload.get("data")
    except InformationError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise InformationError("信息服务暂时不可用，请稍后再试。") from exc
    finally:
        if owns_client:
            await http_client.aclose()


async def fetch_fuel_price(
    base_url: str,
    region: str,
    *,
    timeout: float = 20,
    client: httpx.AsyncClient | None = None,
) -> FuelPrice:
    query = region.strip()
    if not query:
        raise InformationError("请输入省份或城市，例如：今日油价 北京")
    if len(query) > 20:
        raise InformationError("地区名称太长，请输入省份或城市。")
    data = await _get_data(
        base_url,
        "fuel-price",
        params={"region": query},
        timeout=timeout,
        client=client,
    )
    if not isinstance(data, dict):
        raise InformationError("没有查到该地区的油价。")
    items = tuple(
        FuelItem(
            name=str(item.get("name", "未知油品")),
            price_description=str(item.get("price_desc") or f"{item.get('price', '-')} 元/升"),
        )
        for item in data.get("items", [])
        if isinstance(item, dict)
    )
    if not items:
        raise InformationError("没有查到该地区的油价，请尝试只输入省份或城市。")
    trend_data = data.get("trend") if isinstance(data.get("trend"), dict) else {}
    return FuelPrice(
        region=str(data.get("region") or query),
        items=items,
        trend=str(trend_data.get("description") or "暂无下次调价预测"),
        updated=str(data.get("updated") or "未知"),
        source_url=str(data.get("link") or ""),
    )


async def fetch_daily_brief(
    base_url: str,
    *,
    timeout: float = 20,
    client: httpx.AsyncClient | None = None,
) -> DailyBrief:
    data = await _get_data(base_url, "60s", timeout=timeout, client=client)
    if not isinstance(data, dict):
        raise InformationError("今日简报尚未更新。")
    news = tuple(str(item).strip() for item in data.get("news", []) if str(item).strip())
    if not news:
        raise InformationError("今日简报尚未更新。")
    return DailyBrief(
        date=str(data.get("date") or "今日"),
        weekday=str(data.get("day_of_week") or ""),
        news=news,
        tip=str(data.get("tip") or ""),
        image_url=str(data.get("image") or data.get("cover") or ""),
        source_url=str(data.get("link") or ""),
    )


async def download_brief_image(
    image_url: str,
    *,
    timeout: float = 20,
    max_bytes: int = 8 * 1024 * 1024,
    client: httpx.AsyncClient | None = None,
) -> bytes:
    if not image_url.startswith(("https://", "http://")):
        raise InformationError("今日简报图片地址无效。")
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        response = await http_client.get(image_url)
        response.raise_for_status()
        content = response.content
        if not content or len(content) > max_bytes:
            raise InformationError("今日简报图片为空或超过 8 MB。")
        return content
    except InformationError:
        raise
    except httpx.HTTPError as exc:
        raise InformationError("今日简报图片下载失败。") from exc
    finally:
        if owns_client:
            await http_client.aclose()


async def fetch_hot_search(
    base_url: str,
    platform: str,
    *,
    limit: int = 10,
    timeout: float = 20,
    client: httpx.AsyncClient | None = None,
) -> tuple[HotItem, ...]:
    normalized = platform.strip() or "微博"
    endpoint = HOT_PLATFORMS.get(normalized)
    if endpoint is None:
        supported = "、".join(dict.fromkeys(HOT_PLATFORMS))
        raise InformationError(f"暂不支持“{normalized}”，可用平台：{supported}")
    data = await _get_data(base_url, endpoint, timeout=timeout, client=client)
    if not isinstance(data, list):
        raise InformationError(f"{normalized}热搜暂时没有数据。")
    results: list[HotItem] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        hot_value = item.get("hot_value_desc") or item.get("hot_value") or item.get("score") or ""
        results.append(
            HotItem(
                title=str(item["title"]),
                hot_value=str(hot_value),
                link=str(item.get("link") or ""),
            )
        )
        if len(results) >= limit:
            break
    if not results:
        raise InformationError(f"{normalized}热搜暂时没有数据。")
    return tuple(results)
