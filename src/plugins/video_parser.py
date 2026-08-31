"""Authorized video URL parser/downloader."""

import shutil
from pathlib import Path

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import PROJECT_ROOT, get_media_settings
from src.services.economy import EconomyError
from src.services.economy.commands import command_text
from src.services.media.video_parser import download_video, extract_gallery


def is_video_parser(event: GroupMessageEvent) -> bool:
    return command_text(event, "视频解析") is not None


video_parser = on_message(rule=Rule(is_video_parser), priority=10, block=True)


def is_gallery_parser(event: GroupMessageEvent) -> bool:
    return command_text(event, "图集解析") is not None


gallery_parser = on_message(rule=Rule(is_gallery_parser), priority=10, block=True)


@video_parser.handle()
async def handle_video_parser(bot: Bot, event: GroupMessageEvent) -> None:
    url = (command_text(event, "视频解析") or "").strip()
    if not url:
        await video_parser.finish("用法：视频解析 视频链接（仅限你有权下载的内容）")
    try:
        parsed = await download_video(
            url,
            PROJECT_ROOT / "work" / "media-downloads",
            get_media_settings().max_download_bytes,
        )
        await bot.send(event, f"解析成功：{parsed.title}\n上传者：{parsed.uploader or '未知'}")
        await bot.send(event, MessageSegment.video(Path(parsed.path)))
        shutil.rmtree(parsed.path.parent, ignore_errors=True)
    except EconomyError as exc:
        await video_parser.finish(str(exc))
    except Exception:
        logger.exception("Video parsing failed")
        await video_parser.finish("视频解析失败，请稍后再试。")


@gallery_parser.handle()
async def handle_gallery_parser(bot: Bot, event: GroupMessageEvent) -> None:
    url = (command_text(event, "图集解析") or "").strip()
    if not url:
        await gallery_parser.finish("用法：图集解析 图集链接（仅限你有权访问的内容）")
    try:
        gallery = await extract_gallery(url)
        message = MessageSegment.text(f"解析成功：{gallery.title}\n")
        for image_url in gallery.image_urls:
            message += MessageSegment.image(image_url)
        await bot.send(event, message)
    except EconomyError as exc:
        await gallery_parser.finish(str(exc))
    except Exception:
        logger.exception("Gallery parsing failed")
        await gallery_parser.finish("图集解析失败，请稍后再试。")
