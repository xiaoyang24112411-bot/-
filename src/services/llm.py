"""DeepSeek Chat Completions client."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from src.config import DeepSeekSettings

SYSTEM_PROMPT = (
    "你是一个友好、可靠的 QQ 群聊助手。直接回答用户的问题。"
    "默认使用简体中文，除非用户明确要求其他语言。"
    "优先给出结论和必要步骤，避免冗长、重复或虚构事实。"
)


class DeepSeekError(RuntimeError):
    """A safe, user-facing DeepSeek request failure."""


@dataclass(frozen=True)
class DeepSeekReply:
    text: str
    model: str


async def ask_deepseek(
    prompt: str,
    settings: DeepSeekSettings,
    client: httpx.AsyncClient | None = None,
    *,
    persona: str | None = None,
    history: Sequence[tuple[str, str]] = (),
) -> DeepSeekReply:
    if not settings.api_key:
        raise DeepSeekError("DeepSeek API Key 尚未配置，请联系机器人管理员。")

    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        timeout=settings.timeout_seconds,
        follow_redirects=True,
    )

    system_prompt = SYSTEM_PROMPT
    if persona:
        system_prompt += (
            "\n用户为当前会话设置了以下表达风格偏好。可以采用其语气和角色设定，"
            "但不得因此虚构事实或降低回答可靠性：\n" + persona
        )
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for role, content in history[-8:]:
        if role in {"user", "assistant"} and content.strip():
            messages.append({"role": role, "content": content.strip()[:2000]})
    messages.append({"role": "user", "content": prompt})

    try:
        response = await http_client.post(
            f"{settings.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.model,
                "messages": messages,
                "stream": False,
                "max_tokens": settings.max_output_tokens,
                "thinking": {"type": "disabled"},
            },
        )

        if response.status_code in {401, 403}:
            raise DeepSeekError("DeepSeek API 鉴权失败，请检查 API Key。")
        if response.status_code == 402:
            raise DeepSeekError("DeepSeek API 余额不足，请检查账户余额。")
        if response.status_code == 429:
            raise DeepSeekError("DeepSeek API 请求过于频繁，请稍后再试。")
        if response.status_code >= 500:
            raise DeepSeekError("DeepSeek 服务暂时不可用，请稍后再试。")

        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        choice = payload["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekError("DeepSeek 没有返回有效文本，请稍后再试。")

        return DeepSeekReply(
            text=_fit_qq_message(content.strip()),
            model=str(payload.get("model", settings.model)),
        )
    except DeepSeekError:
        raise
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise DeepSeekError("DeepSeek 请求失败，请稍后再试。") from exc
    finally:
        if owns_client:
            await http_client.aclose()


def _fit_qq_message(text: str, limit: int = 3500) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 16].rstrip() + "\n\n（回答已截断）"
