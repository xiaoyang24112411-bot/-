"""Brave Search context is bounded and requires a configured key."""

import httpx
import pytest
import respx

from src.config import WebSearchSettings
from src.services.ai_search import WebSearchError, search_web


def settings(key: str = "test-brave-key") -> WebSearchSettings:
    return WebSearchSettings(key, "https://api.search.brave.com/res/v1/llm/context", 10)


@pytest.mark.asyncio
async def test_search_needs_key():
    with pytest.raises(WebSearchError, match="API Key"):
        await search_web("问题", settings(""))


@respx.mock
@pytest.mark.asyncio
async def test_search_returns_only_https_sources():
    route = respx.get("https://api.search.brave.com/res/v1/llm/context").mock(
        return_value=httpx.Response(200, json={"grounding": {"generic": [
            {"title": "<b>标题</b>", "url": "https://example.com/a", "snippets": ["摘要"]},
            {"title": "不安全", "url": "http://example.com/b", "snippets": ["摘要"]},
        ]}})
    )
    sources = await search_web("问题", settings())
    assert len(sources) == 1
    assert sources[0].title == "标题"
    assert route.calls[0].request.headers["X-Subscription-Token"] == "test-brave-key"


@respx.mock
@pytest.mark.asyncio
async def test_search_auth_error():
    respx.get("https://api.search.brave.com/res/v1/llm/context").mock(
        return_value=httpx.Response(403)
    )
    with pytest.raises(WebSearchError, match="无效或套餐不可用"):
        await search_web("问题", settings())
