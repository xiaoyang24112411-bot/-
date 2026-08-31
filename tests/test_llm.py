import json

import httpx
import pytest
import respx

from src.config import DeepSeekSettings
from src.services.llm import DeepSeekError, ask_deepseek


def settings(api_key: str = "test-key") -> DeepSeekSettings:
    return DeepSeekSettings(
        api_key=api_key,
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        timeout_seconds=10.0,
        max_output_tokens=1200,
    )


@respx.mock
@pytest.mark.asyncio
async def test_ask_deepseek():
    route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
                "choices": [{"message": {"role": "assistant", "content": "你好！"}}],
            },
        )
    )

    reply = await ask_deepseek("你好", settings())

    assert reply.text == "你好！"
    assert reply.model == "deepseek-v4-flash"
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer test-key"
    assert b'"thinking":{"type":"disabled"}' in request.content


@respx.mock
@pytest.mark.asyncio
async def test_ask_deepseek_includes_persona_and_history():
    route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
                "choices": [{"message": {"role": "assistant", "content": "继续回答"}}],
            },
        )
    )
    await ask_deepseek(
        "继续",
        settings(),
        persona="用简洁的侦探口吻回答",
        history=(("user", "上一问"), ("assistant", "上一答")),
    )
    payload = json.loads(route.calls[0].request.content)
    assert "侦探口吻" in payload["messages"][0]["content"]
    assert [message["role"] for message in payload["messages"]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]


@pytest.mark.asyncio
async def test_missing_deepseek_api_key():
    with pytest.raises(DeepSeekError, match="API Key 尚未配置"):
        await ask_deepseek("你好", settings(api_key=""))


@respx.mock
@pytest.mark.asyncio
async def test_deepseek_authentication_error():
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "invalid key"}})
    )

    with pytest.raises(DeepSeekError, match="鉴权失败"):
        await ask_deepseek("你好", settings())
