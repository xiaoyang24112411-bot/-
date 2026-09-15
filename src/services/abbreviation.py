"""Client for the public 能不能好好说话 abbreviation service."""

from dataclasses import dataclass

import httpx


class AbbreviationError(RuntimeError):
    """Raised when an abbreviation cannot be resolved."""


@dataclass(frozen=True)
class AbbreviationResult:
    name: str
    translations: tuple[str, ...]


async def explain_abbreviation(
    text: str,
    *,
    endpoint: str = "https://lab.magiconch.com/api/nbnhhsh/guess",
    timeout: float = 15,
) -> tuple[AbbreviationResult, ...]:
    query = text.strip()
    if not query:
        raise AbbreviationError("用法：/缩写 yyds")
    if len(query) > 40:
        raise AbbreviationError("查询内容请控制在 40 个字符以内。")
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.post(endpoint, json={"text": query})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise AbbreviationError("缩写查询服务暂时不可用，请稍后再试。") from exc
    if not isinstance(payload, list):
        raise AbbreviationError("缩写查询服务返回了无法识别的数据。")
    results: list[AbbreviationResult] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        values = item.get("trans") or item.get("inputting") or []
        translations = tuple(str(value).strip() for value in values if str(value).strip())
        if translations:
            results.append(AbbreviationResult(str(item.get("name") or query), translations[:8]))
    if not results:
        raise AbbreviationError(f"暂时没有查到“{query}”的常见解释。")
    return tuple(results)
