"""Strictly read-only tools available to DeepSeek chat."""

import json
from datetime import datetime, timezone

from src.config import get_information_settings
from src.services.information import InformationError
from src.services.information.api_60s import HOT_PLATFORMS, fetch_hot_search
from src.services.weather import WeatherError, get_weather

READ_ONLY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "查询指定城市的实时天气。仅用于天气问题。",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名，如上海"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hot_search",
            "description": "查询微博、抖音、知乎、头条、B站或小红书的实时热搜。",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "enum": list(dict.fromkeys(HOT_PLATFORMS)),
                        "description": "热搜平台，默认微博",
                    }
                },
                "required": ["platform"],
            },
        },
    },
]


async def execute_readonly_tool(name: str, arguments: str) -> str:
    """Validate every model-supplied argument before calling a permitted API."""
    try:
        parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
        if name == "get_current_weather":
            city = parsed.get("city")
            if not isinstance(city, str) or not 1 <= len(city.strip()) <= 40:
                raise ValueError("invalid city")
            weather = await get_weather(city.strip())
            result = {
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "data": weather.to_message(),
            }
        elif name == "get_hot_search":
            platform = parsed.get("platform", "微博")
            if not isinstance(platform, str) or platform not in HOT_PLATFORMS:
                raise ValueError("invalid platform")
            settings = get_information_settings()
            items = await fetch_hot_search(
                settings.api_60s_base_url,
                platform,
                limit=5,
                timeout=settings.timeout_seconds,
            )
            result = {
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "platform": platform,
                "items": [
                    {"title": item.title[:100], "url": item.link[:250]}
                    for item in items
                ],
            }
        else:
            raise ValueError("unknown tool")
        return json.dumps(result, ensure_ascii=False)
    except (ValueError, TypeError, WeatherError, InformationError):
        return json.dumps({"error": "查询失败或参数无效，请不要编造结果。"}, ensure_ascii=False)
