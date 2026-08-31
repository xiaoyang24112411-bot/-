"""Song lookup returning official Apple/iTunes track pages."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.ai_features import AIFeatureError
from src.services.ai_features.music import search_songs
from src.services.economy.commands import command_text

music_request = on_message(
    rule=Rule(lambda event: command_text(event, "点歌") is not None),
    priority=10,
    block=True,
)


@music_request.handle()
async def handle_music_request(event: GroupMessageEvent) -> None:
    try:
        results = await search_songs(command_text(event, "点歌") or "")
    except AIFeatureError as exc:
        await music_request.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Music search failed")
        await music_request.finish("点歌查询失败，请稍后再试。")

    lines = ["Apple/iTunes 曲目搜索："]
    for index, song in enumerate(results[:3], start=1):
        minutes, seconds = divmod(song.duration_seconds, 60)
        lines.extend(
            (
                f"{index}. {song.title} - {song.artist}",
                f"专辑：{song.album}｜时长：{minutes}:{seconds:02d}",
                song.track_url,
            )
        )
    lines.append("链接指向官方曲目页，能否完整播放取决于所在地区和账号权限。")
    await music_request.finish("\n".join(lines))
