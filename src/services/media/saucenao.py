"""Optional SauceNAO reverse-image lookup."""

from dataclasses import dataclass

import httpx

from src.services.economy.errors import EconomyError

API_URL = "https://saucenao.com/search.php"


@dataclass(frozen=True)
class SourceResult:
    similarity: float
    title: str
    source_url: str
    author: str


async def search_image_source(image_url: str, api_key: str) -> SourceResult:
    if not api_key:
        raise EconomyError("SauceNAO API Key 尚未配置，请联系机器人管理员。")
    params = {"output_type": 2, "api_key": api_key, "url": image_url, "numres": 3}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(API_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise EconomyError("图片来源查询服务暂时不可用。") from exc
    results = payload.get("results") or []
    if not results:
        raise EconomyError("没有找到可靠的图片来源。")
    best = results[0]
    header = best.get("header", {})
    data = best.get("data", {})
    urls = data.get("ext_urls") or []
    return SourceResult(
        similarity=float(header.get("similarity", 0)),
        title=str(data.get("title") or data.get("material") or "未知作品"),
        source_url=str(urls[0]) if urls else "",
        author=str(data.get("member_name") or data.get("creator") or "未知作者"),
    )
