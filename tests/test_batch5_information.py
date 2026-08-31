import random

import httpx
import pytest
import respx

from src.services.information import InformationError
from src.services.information.api_60s import (
    download_brief_image,
    fetch_daily_brief,
    fetch_fuel_price,
    fetch_hot_search,
)
from src.services.information.mangadex import search_manga
from src.services.information.quotes import random_quote
from src.services.information.tmdb import search_screen_titles


@pytest.mark.asyncio
async def test_60s_information_services_parse_responses():
    base_url = "https://information.test/v2"
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{base_url}/fuel-price").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "region": "北京",
                        "items": [{"name": "92#汽油", "price_desc": "7.50 元/升"}],
                        "trend": {"description": "预计下调"},
                        "updated": "2026/08/30 12:00",
                        "link": "https://example.test/fuel",
                    },
                },
            )
        )
        router.get(f"{base_url}/60s").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "date": "2026-08-30",
                        "day_of_week": "星期日",
                        "news": ["第一条新闻", "第二条新闻"],
                        "tip": "今日微语",
                        "image": "https://cdn.test/brief.png",
                        "link": "https://example.test/brief",
                    },
                },
            )
        )
        router.get(f"{base_url}/weibo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": [
                        {"title": "热搜一", "hot_value": 10000, "link": "https://weibo.test/1"},
                        {"title": "热搜二", "score": "火热", "link": ""},
                    ],
                },
            )
        )
        router.get("https://cdn.test/brief.png").mock(
            return_value=httpx.Response(200, content=b"png-bytes")
        )
        async with httpx.AsyncClient() as client:
            fuel = await fetch_fuel_price(base_url, "北京", client=client)
            brief = await fetch_daily_brief(base_url, client=client)
            hot = await fetch_hot_search(base_url, "微博", client=client)
            image = await download_brief_image(brief.image_url, client=client)

    assert fuel.items[0].price_description == "7.50 元/升"
    assert brief.news == ("第一条新闻", "第二条新闻")
    assert hot[0].title == "热搜一"
    assert hot[1].hot_value == "火热"
    assert image == b"png-bytes"


@pytest.mark.asyncio
async def test_tmdb_requires_token_and_parses_movie():
    with pytest.raises(InformationError, match="Token"):
        await search_screen_titles("https://tmdb.test/3", "", "流浪地球")

    payload = {
        "results": [
            {
                "id": 535167,
                "media_type": "movie",
                "title": "流浪地球",
                "release_date": "2019-02-05",
                "vote_average": 7.1,
                "overview": "太阳即将毁灭，人类建造推进器寻找新家园。",
            },
            {"id": 1, "media_type": "person", "name": "不应返回"},
        ]
    }
    with respx.mock(assert_all_called=True) as router:
        router.get("https://tmdb.test/3/search/multi").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with httpx.AsyncClient() as client:
            results = await search_screen_titles(
                "https://tmdb.test/3", "token", "流浪地球", client=client
            )
    assert results[0].title == "流浪地球"
    assert results[0].year == "2019"
    assert "/movie/535167" in results[0].detail_url


@pytest.mark.asyncio
async def test_mangadex_search_and_local_quotes():
    payload = {
        "data": [
            {
                "id": "manga-id",
                "attributes": {
                    "title": {"zh": "测试漫画", "en": "Test Manga"},
                    "description": {"zh": "测试简介"},
                    "year": 2024,
                    "status": "ongoing",
                },
            }
        ]
    }
    with respx.mock(assert_all_called=True) as router:
        router.get("https://manga.test/manga").mock(return_value=httpx.Response(200, json=payload))
        async with httpx.AsyncClient() as client:
            results = await search_manga("https://manga.test", "测试", client=client)
    assert results[0].title == "测试漫画"
    assert results[0].detail_url.endswith("/manga-id")

    quote = random_quote("治愈", rng=random.Random(1))
    assert quote.category == "治愈"
    with pytest.raises(InformationError, match="可用文案分类"):
        random_quote("不存在")
