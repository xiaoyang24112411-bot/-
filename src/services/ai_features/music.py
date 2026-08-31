"""Metadata-only song search using Apple's public iTunes Search API."""

from dataclasses import dataclass

import httpx

from .errors import AIFeatureError

API_URL = "https://itunes.apple.com/search"


@dataclass(frozen=True)
class SongResult:
    title: str
    artist: str
    album: str
    duration_seconds: int
    track_url: str


async def search_songs(
    query: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[SongResult, ...]:
    keyword = query.strip()
    if not keyword:
        raise AIFeatureError("请输入歌名，例如：点歌 稻香")
    if len(keyword) > 80:
        raise AIFeatureError("歌曲关键词不能超过 80 个字符。")
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=20, follow_redirects=True)
    try:
        response = await http_client.get(
            API_URL,
            params={
                "term": keyword,
                "country": "CN",
                "media": "music",
                "entity": "song",
                "limit": 5,
                "lang": "zh_cn",
                "explicit": "No",
            },
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise AIFeatureError("Apple 音乐检索暂时不可用，请稍后再试。") from exc
    finally:
        if owns_client:
            await http_client.aclose()

    results = tuple(
        SongResult(
            title=str(item.get("trackName") or "未知歌曲"),
            artist=str(item.get("artistName") or "未知歌手"),
            album=str(item.get("collectionName") or "未知专辑"),
            duration_seconds=max(0, int(item.get("trackTimeMillis") or 0) // 1000),
            track_url=str(item.get("trackViewUrl") or ""),
        )
        for item in payload.get("results", [])
        if isinstance(item, dict) and item.get("trackViewUrl")
    )
    if not results:
        raise AIFeatureError("没有找到相关歌曲，请尝试“歌名 歌手”。")
    return results
