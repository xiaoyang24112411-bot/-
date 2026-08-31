"""Yu-Gi-Oh card lookup command backed by YGOPRODeck."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.economy import EconomyError, get_economy_database
from src.services.economy.commands import command_text
from src.services.games.yugioh import search_yugioh_card


def is_yugioh_lookup(event: GroupMessageEvent) -> bool:
    return command_text(event, "游戏王查卡") is not None


yugioh_lookup = on_message(rule=Rule(is_yugioh_lookup), priority=10, block=True)


@yugioh_lookup.handle()
async def handle_yugioh_lookup(event: GroupMessageEvent) -> None:
    query = (command_text(event, "游戏王查卡") or "").strip()
    if not query:
        await yugioh_lookup.finish(
            "用法：游戏王查卡 英文卡名/常见中文卡名/卡片密码\n例如：游戏王查卡 青眼白龙"
        )
    try:
        card = await search_yugioh_card(get_economy_database(), query)
    except EconomyError as exc:
        await yugioh_lookup.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Yu-Gi-Oh card lookup failed")
        await yugioh_lookup.finish("游戏王查卡失败，请稍后再试。")

    details = [f"卡名：{card.name}", f"密码：{card.card_id}", f"类型：{card.card_type}"]
    if card.attribute:
        details.append(f"属性：{card.attribute}｜种族：{card.race}")
    else:
        details.append(f"分类：{card.race}")
    if card.level is not None:
        details.append(f"等级/阶级：{card.level}")
    if card.attack is not None:
        defense = card.defense if card.defense is not None else "-"
        details.append(f"ATK：{card.attack}｜DEF：{defense}")
    if card.archetype:
        details.append(f"系列：{card.archetype}")
    description = card.description
    if len(description) > 600:
        description = description[:600] + "……"
    details.append("效果：" + description)
    await yugioh_lookup.finish(MessageSegment.at(event.user_id) + "\n" + "\n".join(details))
