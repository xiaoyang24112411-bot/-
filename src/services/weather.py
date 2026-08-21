"""Open-Meteo geocoding and current-weather client."""

from dataclasses import dataclass
from typing import Any

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_DESCRIPTIONS = {
    0: "晴",
    1: "大致晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    56: "轻微冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "轻微冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "米雪",
    80: "小阵雨",
    81: "中阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴强冰雹",
}


class WeatherError(RuntimeError):
    """A user-facing weather lookup failure."""


@dataclass(frozen=True)
class Weather:
    location: str
    country: str
    temperature: float
    apparent_temperature: float
    humidity: int
    precipitation: float
    weather_code: int
    wind_speed: float

    def to_message(self) -> str:
        description = WEATHER_DESCRIPTIONS.get(self.weather_code, "未知天气")
        location = f"{self.location}，{self.country}" if self.country else self.location
        return (
            f"{location} 当前天气：{description}\n"
            f"温度：{self.temperature:g}°C（体感 {self.apparent_temperature:g}°C）\n"
            f"湿度：{self.humidity}%\n"
            f"降水：{self.precipitation:g} mm\n"
            f"风速：{self.wind_speed:g} km/h"
        )


async def get_weather(city: str, client: httpx.AsyncClient | None = None) -> Weather:
    """Resolve a city name, then fetch its current weather."""
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)

    try:
        geocoding_response = await http_client.get(
            GEOCODING_URL,
            params={"name": city, "count": 1, "language": "zh", "format": "json"},
        )
        geocoding_response.raise_for_status()
        locations = geocoding_response.json().get("results") or []
        if not locations:
            raise WeatherError(f"没有找到城市“{city}”，请换一个更完整的名称。")

        location: dict[str, Any] = locations[0]
        forecast_response = await http_client.get(
            FORECAST_URL,
            params={
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "current": (
                    "temperature_2m,apparent_temperature,relative_humidity_2m,"
                    "precipitation,weather_code,wind_speed_10m"
                ),
                "timezone": "auto",
            },
        )
        forecast_response.raise_for_status()
        current = forecast_response.json().get("current")
        if not current:
            raise WeatherError("天气服务暂时没有返回实时数据，请稍后再试。")

        return Weather(
            location=str(location.get("name", city)),
            country=str(location.get("country", "")),
            temperature=float(current["temperature_2m"]),
            apparent_temperature=float(current["apparent_temperature"]),
            humidity=int(current["relative_humidity_2m"]),
            precipitation=float(current["precipitation"]),
            weather_code=int(current["weather_code"]),
            wind_speed=float(current["wind_speed_10m"]),
        )
    except WeatherError:
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise WeatherError("天气服务请求失败，请稍后再试。") from exc
    finally:
        if owns_client:
            await http_client.aclose()

