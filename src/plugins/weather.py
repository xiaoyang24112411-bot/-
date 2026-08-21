"""The /天气 <city> command."""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.params import CommandArg

from src.services.weather import WeatherError, get_weather

weather = on_command("天气", priority=10, block=True)


@weather.handle()
async def handle_weather(
    event: MessageEvent,
    args: Message = CommandArg(),  # noqa: B008 - NoneBot dependency injection
) -> None:
    city = args.extract_plain_text().strip()
    if not city:
        await weather.finish("用法：/天气 城市名\n例如：/天气 上海")

    try:
        result = await get_weather(city)
    except WeatherError as exc:
        await weather.finish(str(exc))

    await weather.finish(result.to_message())
