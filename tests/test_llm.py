import json

import httpx
import pytest
import respx

from src.config import DeepSeekSettings
from src.services.ai_search import SearchSource
from src.services.llm import DeepSeekError, ask_deepseek


def settings(api_key: str = "test-key") -> DeepSeekSettings:
    return DeepSeekSettings(
        api_key=api_key,
        model="deepseek-flash",
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
                "model": "deepseek-flash",
                "choices": [{"message": {"role": "assistant", "content": "你好！"}}],
            },
        )
    )

    reply = await ask_deepseek("你好", settings())

    assert reply.text == "你好！"
    assert reply.model == "deepseek-flash"
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
                "model": "deepseek-flash",
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


@respx.mock
@pytest.mark.asyncio
async def test_deep_thinking_and_search_sources():
    route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "答案见[1]。"}}]},
        )
    )
    source = SearchSource("参考页", "https://example.com/one", "一段摘要")
    reply = await ask_deepseek("最新情况？", settings(), deep=True, sources=(source,))
    body = json.loads(route.calls[0].request.content)
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "high"
    assert body["max_tokens"] == 4096
    assert "一段摘要" in body["messages"][-1]["content"]
    assert "https://example.com/one" in reply.text


@respx.mock
@pytest.mark.asyncio
async def test_read_only_tool_call(monkeypatch):
    async def fake_tool(name: str, arguments: str) -> str:
        assert name == "get_current_weather"
        assert json.loads(arguments) == {"city": "北京"}
        return '{"data":"北京 晴"}'

    monkeypatch.setattr("src.services.llm.execute_readonly_tool", fake_tool)
    route = respx.post("https://api.deepseek.com/chat/completions")
    route.side_effect = [
        httpx.Response(
            200,
            json={
                "choices": [{"message": {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "思考过程",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_current_weather", "arguments": '{"city":"北京"}'},
                    }],
                }}],
            },
        ),
        httpx.Response(200, json={"choices": [{"message": {"content": "北京晴。"}}]}),
    ]
    reply = await ask_deepseek("北京天气？", settings(), deep=True)
    followup = json.loads(route.calls[1].request.content)
    assert followup["messages"][-2]["reasoning_content"] == "思考过程"
    assert followup["messages"][-1]["role"] == "tool"
    assert reply.text == "北京晴。"


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    [],
    {"choices": []},
    {"choices": [{"message": []}]},
    {"choices": [{"message": {"content": "", "tool_calls": "bad"}}]},
    {"choices": [{"message": {"content": "  "}}]},
])
async def test_malformed_responses_raise_safe_error(payload):
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    with pytest.raises(DeepSeekError):
        await ask_deepseek("测试", settings())
