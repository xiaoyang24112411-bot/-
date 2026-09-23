"""Explicit group meme collection, replay, and visual understanding."""

from nonebot import get_bots, logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import AUTO_CHAT_CONTROLLER_ID, get_deepseek_settings, get_meme_settings
from src.services.ai_features.personas import get_effective_persona
from src.services.economy import EconomyError, get_economy_database
from src.services.economy.commands import command_text
from src.services.llm import DeepSeekError, ask_deepseek
from src.services.media.meme_library import (
    delete_meme,
    meme_count,
    proactive_meme_enabled,
    random_meme,
    save_meme,
    set_proactive_meme_enabled,
)
from src.services.media.message_image import image_url_from_event
from src.services.media.qq_image import fetch_qq_image
from src.services.permissions import is_group_manager


def _rule(command: str) -> Rule:
    return Rule(
        lambda event: (
            isinstance(event, GroupMessageEvent)
            and event.user_id != event.self_id
            and str(event.user_id) not in get_bots()
            and command_text(event, command) is not None
        )
    )


save_command = on_message(rule=_rule("收藏表情包"), priority=8, block=True)
random_command = on_message(rule=_rule("随机表情包"), priority=8, block=True)
delete_command = on_message(rule=_rule("删除表情包"), priority=8, block=True)
status_command = on_message(rule=_rule("表情包状态"), priority=8, block=True)
enable_command = on_message(rule=_rule("开启表情包自主发送"), priority=8, block=True)
disable_command = on_message(rule=_rule("关闭表情包自主发送"), priority=8, block=True)
vision_command = on_message(rule=_rule("看图"), priority=8, block=True)


@save_command.handle()
async def handle_save(bot: Bot, event: GroupMessageEvent) -> None:
    if not is_group_manager(event):
        await save_command.finish("收藏表情包仅限本群管理或终极管理员操作。")
    try:
        url = await image_url_from_event(bot, event)
        image, _ = await fetch_qq_image(url, get_meme_settings().max_image_bytes)
        saved, created = await save_meme(
            get_economy_database(), get_meme_settings(), event.group_id, event.user_id, image
        )
    except EconomyError as exc:
        await save_command.finish(str(exc))
    except Exception:
        logger.exception("Meme save failed: group={}", event.group_id)
        await save_command.finish("收藏失败，请稍后重试。")
    await save_command.finish(f"{'已收藏' if created else '这张图已经收藏过'}，编号 {saved.id}。")


@random_command.handle()
async def handle_random(event: GroupMessageEvent) -> None:
    try:
        saved = await random_meme(get_economy_database(), get_meme_settings(), event.group_id)
        message = (
            MessageSegment.image(saved.path.read_bytes()) + f"\n表情包编号 {saved.id}"
            if saved is not None
            else "本群还没有可用的收藏表情包。"
        )
    except Exception:
        logger.exception("Meme replay failed: group={}", event.group_id)
        await random_command.finish("发送收藏表情包失败，请稍后重试。")
    await random_command.finish(message)


@delete_command.handle()
async def handle_delete(event: GroupMessageEvent) -> None:
    if not is_group_manager(event):
        await delete_command.finish("删除表情包仅限本群管理或终极管理员操作。")
    argument = command_text(event, "删除表情包") or ""
    if not argument.isdecimal() or int(argument) <= 0:
        await delete_command.finish("用法：删除表情包 编号")
    deleted = await delete_meme(
        get_economy_database(), get_meme_settings(), event.group_id, int(argument)
    )
    await delete_command.finish("已删除。" if deleted else "本群没有这个表情包编号。")


@status_command.handle()
async def handle_status(event: GroupMessageEvent) -> None:
    database = get_economy_database()
    count = await meme_count(database, event.group_id)
    enabled = await proactive_meme_enabled(database, event.group_id)
    await status_command.finish(
        f"本群已收藏 {count} 张；自主发送{'开启' if enabled else '关闭'}。"
        "\n自主发送还需要本群的自主回答开关开启。"
    )


async def _change_auto_send(event: GroupMessageEvent, enabled: bool, matcher) -> None:
    if event.user_id != AUTO_CHAT_CONTROLLER_ID:
        await matcher.finish(f"只有终极管理员 {AUTO_CHAT_CONTROLLER_ID} 可以控制自主发送。")
    await set_proactive_meme_enabled(get_economy_database(), event.group_id, enabled, event.user_id)
    await matcher.finish(f"本群表情包自主发送已{'开启' if enabled else '关闭'}。")


@enable_command.handle()
async def handle_enable(event: GroupMessageEvent) -> None:
    await _change_auto_send(event, True, enable_command)


@disable_command.handle()
async def handle_disable(event: GroupMessageEvent) -> None:
    await _change_auto_send(event, False, disable_command)


@vision_command.handle()
async def handle_vision(bot: Bot, event: GroupMessageEvent) -> None:
    prompt = command_text(event, "看图") or ""
    if len(prompt) > 500:
        await vision_command.finish("问题太长，请控制在 500 字以内。")
    if not prompt:
        prompt = "请看图并简短解释内容、图中文字和这张表情包表达的情绪；看不清就说明。"
    try:
        url = await image_url_from_event(bot, event)
        image = await fetch_qq_image(url, get_meme_settings().max_image_bytes)
        persona = await get_effective_persona(get_economy_database(), event.group_id, event.user_id)
        reply = await ask_deepseek(prompt, get_deepseek_settings(), persona=persona, image=image)
    except (EconomyError, DeepSeekError) as exc:
        await vision_command.finish(str(exc))
    except Exception:
        logger.exception("Meme vision failed: group={}", event.group_id)
        await vision_command.finish("看图失败，请稍后重试。")
    await vision_command.finish(reply.text)
