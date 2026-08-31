"""TMDB movie and TV metadata search."""

from dataclasses import dataclass

import httpx

from .errors import InformationError


@dataclass(frozen=True)
class ScreenTitle:
    tmdb_id: int
    media_type: str
    title: str
    year: str
    score: float
    overview: str

    @property
    def detail_url(self) -> str:
        kind = "tv" if self.media_type == "电视剧" else "movie"
        return f"https://www.themoviedb.org/{kind}/{self.tmdb_id}?language=zh-CN"


async def search_screen_titles(
    base_url: str,
    access_token: str,
    query: str,
    *,
    timeout: float = 20,
    client: httpx.AsyncClient | None = None,
) -> tuple[ScreenTitle, ...]:
    keyword = query.strip()
    if not keyword:
        raise InformationError("请输入影视名称，例如：影视搜索 流浪地球")
    if len(keyword) > 80:
        raise InformationError("影视名称太长，请控制在 80 个字符以内。")
    if not access_token:
        raise InformationError("TMDB Access Token 尚未配置，请联系机器人管理员。")
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        response = await http_client.get(
            f"{base_url.rstrip('/')}/search/multi",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"query": keyword, "language": "zh-CN", "include_adult": "false"},
        )
        if response.status_code in {401, 403}:
            raise InformationError("TMDB Access Token 无效或没有权限。")
        response.raise_for_status()
        payload = response.json()
    except InformationError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise InformationError("TMDB 影视查询暂时不可用。") from exc
    finally:
        if owns_client:
            await http_client.aclose()

    results: list[ScreenTitle] = []
    for item in payload.get("results", []):
        if not isinstance(item, dict) or item.get("media_type") not in {"movie", "tv"}:
            continue
        is_tv = item["media_type"] == "tv"
        title = item.get("name") if is_tv else item.get("title")
        date = item.get("first_air_date") if is_tv else item.get("release_date")
        if not title:
            continue
        results.append(
            ScreenTitle(
                tmdb_id=int(item["id"]),
                media_type="电视剧" if is_tv else "电影",
                title=str(title),
                year=str(date or "")[:4] or "年份未知",
                score=float(item.get("vote_average") or 0),
                overview=str(item.get("overview") or "暂无简介").strip(),
            )
        )
        if len(results) >= 5:
            break
    if not results:
        raise InformationError("没有找到相关影视资料，请换一个关键词。")
    return tuple(results)
