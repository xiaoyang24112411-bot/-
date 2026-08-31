"""Safe metadata-only manga search using MangaDex's public API."""

from dataclasses import dataclass

import httpx

from .errors import InformationError


@dataclass(frozen=True)
class MangaTitle:
    manga_id: str
    title: str
    year: str
    status: str
    description: str

    @property
    def detail_url(self) -> str:
        return f"https://mangadex.org/title/{self.manga_id}"


def _localized_text(value: object, default: str) -> str:
    if not isinstance(value, dict):
        return default
    for language in ("zh", "zh-hk", "zh-ro", "ja-ro", "en", "ja"):
        text = value.get(language)
        if text:
            return str(text)
    return str(next(iter(value.values()), default))


async def search_manga(
    base_url: str,
    query: str,
    *,
    timeout: float = 20,
    client: httpx.AsyncClient | None = None,
) -> tuple[MangaTitle, ...]:
    keyword = query.strip()
    if not keyword:
        raise InformationError("请输入漫画名称，例如：漫画搜索 葬送的芙莉莲")
    if len(keyword) > 80:
        raise InformationError("漫画名称太长，请控制在 80 个字符以内。")
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        response = await http_client.get(
            f"{base_url.rstrip('/')}/manga",
            params=[
                ("title", keyword),
                ("limit", "5"),
                ("order[relevance]", "desc"),
                ("contentRating[]", "safe"),
                ("contentRating[]", "suggestive"),
            ],
            headers={"User-Agent": "qq-nonebot-starter/0.1"},
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise InformationError("MangaDex 漫画查询暂时不可用。") from exc
    finally:
        if owns_client:
            await http_client.aclose()

    results: list[MangaTitle] = []
    for item in payload.get("data", []):
        if not isinstance(item, dict) or not isinstance(item.get("attributes"), dict):
            continue
        attributes = item["attributes"]
        results.append(
            MangaTitle(
                manga_id=str(item.get("id", "")),
                title=_localized_text(attributes.get("title"), "未知标题"),
                year=str(attributes.get("year") or "年份未知"),
                status=str(attributes.get("status") or "unknown"),
                description=_localized_text(attributes.get("description"), "暂无简介"),
            )
        )
    if not results:
        raise InformationError("没有找到相关漫画资料，请换一个关键词。")
    return tuple(results)
