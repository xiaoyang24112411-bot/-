"""Discover usable avatar templates and draw one without memorizing keywords."""

import random

from nonebot import get_bots, on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.typing import T_State
from nonebot_plugin_alconna import Image
from nonebot_plugin_memes.manager import meme_manager
from nonebot_plugin_memes.matchers import command as meme_command
from nonebot_plugin_memes.matchers.utils import UserId
from nonebot_plugin_uninfo import Uninfo

from src.services.meme_catalog import avatar_target, avatar_templates, catalog_page


def human_group_message(event: GroupMessageEvent) -> bool:
    return (event.user_id != event.self_id and str(event.user_id) not in get_bots()
            and not getattr(event.sender, "is_bot", False))


# The existing global_blacklist event preprocessor also guards these handlers.
avatar_box = on_command("头像盲盒", aliases={"随机头像表情"},
                        rule=human_group_message, priority=10, block=True)
avatar_catalog = on_command("头像模板", aliases={"头像表情目录"},
                            rule=human_group_message, priority=10, block=True)


def available_templates(user_id: str):
    return avatar_templates(
        meme_manager.get_memes(), lambda key: meme_manager.check(user_id, key)
    )


@avatar_catalog.handle()
async def show_avatar_catalog(
    user_id: UserId, argument: Message = CommandArg(),  # noqa: B008
) -> None:
    if any(segment.type != "text" for segment in argument):
        await avatar_catalog.finish("用法：/头像模板 [页码]，例如 /头像模板 2。")
    prefix = next(iter(meme_command.prefixes), "")
    await avatar_catalog.finish(MessageSegment.text(catalog_page(
        available_templates(user_id), argument.extract_plain_text(), prefix
    )))


@avatar_box.handle()
async def draw_avatar_template(
    bot: Bot, event: GroupMessageEvent, state: T_State, session: Uninfo, user_id: UserId,
    argument: Message = CommandArg(),  # noqa: B008
) -> None:
    try:
        target = avatar_target(argument, event.user_id)
    except ValueError as exc:
        await avatar_box.finish(str(exc))
        return
    candidates = available_templates(user_id)
    if not candidates:
        await avatar_box.finish("本群目前没有已启用的单头像模板。")
        return
    meme = random.choice(candidates)
    name = target
    if target == str(event.user_id):
        name = event.sender.card or event.sender.nickname or target
    await meme_command.process(
        bot, event, state, avatar_box, session, meme,
        [Image(name=name, url=f"https://q1.qlogo.cn/g?b=qq&nk={target}&s=640")], [],
        show_info=True,
    )
