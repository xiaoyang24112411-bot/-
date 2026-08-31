"""Local category-based random image and video commands."""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_media_settings
from src.services.economy import EconomyError
from src.services.economy.commands import command_text
from src.services.media.local_library import list_categories, random_media


def _rule(command: str) -> Rule:
    return Rule(lambda event: command_text(event, command) is not None)


random_image = on_message(rule=_rule("随机图片"), priority=10, block=True)
image_categories = on_message(rule=_rule("图片分类"), priority=10, block=True)
random_video = on_message(rule=_rule("随机视频"), priority=10, block=True)
video_categories = on_message(rule=_rule("视频分类"), priority=10, block=True)


@random_image.handle()
async def handle_random_image(event: GroupMessageEvent) -> None:
    try:
        path = random_media(
            get_media_settings().media_root,
            "images",
            command_text(event, "随机图片") or "",
        )
    except EconomyError as exc:
        await random_image.finish(str(exc))
    await random_image.finish(MessageSegment.image(path.read_bytes()))


@image_categories.handle()
async def handle_image_categories() -> None:
    categories = list_categories(get_media_settings().media_root, "images")
    await image_categories.finish(
        "图片分类：" + ("、".join(categories) if categories else "暂无，请添加本地素材")
    )


@random_video.handle()
async def handle_random_video(event: GroupMessageEvent) -> None:
    try:
        path = random_media(
            get_media_settings().media_root,
            "videos",
            command_text(event, "随机视频") or "",
        )
    except EconomyError as exc:
        await random_video.finish(str(exc))
    await random_video.finish(MessageSegment.video(path))


@video_categories.handle()
async def handle_video_categories() -> None:
    categories = list_categories(get_media_settings().media_root, "videos")
    await video_categories.finish(
        "视频分类：" + ("、".join(categories) if categories else "暂无，请添加本地素材")
    )
