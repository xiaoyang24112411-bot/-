"""Bounded Brave Search context for explicit, source-backed AI questions."""

import html
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from src.config import WebSearchSettings


class WebSearchError(RuntimeError):
    """A safe, user-facing search failure."""


@dataclass(frozen=True)
class SearchSource:
    title: str
    url: str
    excerpt: str


def _clean(value: object, limit: int) -> str:
    text = re.sub(r"<[^>]*>", " ", html.unescape(str(value)))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _valid_url(value: object) -> str:
    url = str(value).strip()
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or len(url) > 300:
        return ""
    return url


async def search_web(
    query: str,
    settings: WebSearchSettings,
    client: httpx.AsyncClient | None = None,
) -> tuple[SearchSource, ...]:
    """Get up to three short excerpts; never fetch arbitrary result URLs."""
    if not settings.api_key:
        raise WebSearchError("联网搜索尚未配置 Brave Search API Key，请联系机器人管理员。")
    query = query.strip()
    if not query or len(query) > 300:
        raise WebSearchError("联网问题不能为空，且不能超过 300 字。")

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=settings.timeout_seconds)
    try:
        response = await http_client.get(
            settings.base_url,
            headers={"Accept": "application/json", "X-Subscription-Token": settings.api_key},
            params={
                "q": query,
                "count": 5,
                "maximum_number_of_urls": 3,
                "maximum_number_of_snippets": 6,
                "maximum_number_of_tokens": 2048,
                "safesearch": "moderate",
            },
        )
        if response.status_code in {401, 403}:
            raise WebSearchError("Brave Search API Key 无效或套餐不可用。")
        if response.status_code == 429:
            raise WebSearchError("联网搜索请求过于频繁，请稍后再试。")
        response.raise_for_status()
        payload = response.json()
        generic = payload.get("grounding", {}).get("generic", [])
        if not isinstance(generic, list):
            raise WebSearchError("联网搜索返回的数据格式异常。")
        sources: list[SearchSource] = []
        seen: set[str] = set()
        for item in generic:
            if not isinstance(item, dict):
                continue
            url = _valid_url(item.get("url", ""))
            snippets = item.get("snippets")
            if not url or url in seen or not isinstance(snippets, list):
                continue
            excerpt = _clean(" ".join(str(value) for value in snippets[:2]), 700)
            if not excerpt:
                continue
            sources.append(SearchSource(_clean(item.get("title", "网页"), 100), url, excerpt))
            seen.add(url)
            if len(sources) >= 3:
                break
        if not sources:
            raise WebSearchError("没有找到可引用的网页资料，请换个问法。")
        return tuple(sources)
    except WebSearchError:
        raise
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        raise WebSearchError("联网搜索暂时不可用，请稍后再试。") from exc
    finally:
        if owns_client:
            await http_client.aclose()
