import httpx
import pytest
import respx

from src.services.weather import FORECAST_URL, GEOCODING_URL, WeatherError, get_weather


@respx.mock
@pytest.mark.asyncio
async def test_get_weather():
    respx.get(GEOCODING_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"name": "上海", "country": "中国", "latitude": 31.23, "longitude": 121.47}
                ]
            },
        )
    )
    respx.get(FORECAST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "current": {
                    "temperature_2m": 28.2,
                    "apparent_temperature": 31.0,
                    "relative_humidity_2m": 70,
                    "precipitation": 0.0,
                    "weather_code": 1,
                    "wind_speed_10m": 12.5,
                }
            },
        )
    )

    weather = await get_weather("上海")

    assert weather.location == "上海"
    assert "大致晴朗" in weather.to_message()
    assert "28.2°C" in weather.to_message()


@respx.mock
@pytest.mark.asyncio
async def test_city_not_found():
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json={"results": []}))

    with pytest.raises(WeatherError, match="没有找到城市"):
        await get_weather("不存在的城市")

