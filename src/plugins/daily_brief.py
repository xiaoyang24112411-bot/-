"""Daily 60-second news brief in image or text mode."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_information_settings
from src.services.economy.commands import command_text
from src.services.information import InformationError
from src.services.information.api_60s import download_brief_image, fetch_daily_brief


def _argument(event: GroupMessageEvent) -> str | None:
    for command in ("每天60秒", "每日60秒", "60秒读懂世界"):
        argument = command_text(event, command)
        if argument is not None:
            return argument
    return None


daily_brief = on_message(
    rule=Rule(lambda event: _argument(event) is not None), priority=10, block=True
)


def _text_brief(date: str, weekday: str, news: tuple[str, ...], tip: str) -> str:
    lines = [f"每天60秒读懂世界｜{date} {weekday}".rstrip()]
    lines.extend(f"{index}. {item}" for index, item in enumerate(news, start=1))
    if tip:
        lines.append("每日微语：" + tip)
    return "\n".join(lines)


@daily_brief.handle()
async def handle_daily_brief(event: GroupMessageEvent) -> None:
    argument = (_argument(event) or "").strip()
    if argument not in {"", "图片", "文字"}:
        await daily_brief.finish("用法：每天60秒 [图片/文字]")
    settings = get_information_settings()
    try:
        brief = await fetch_daily_brief(
            settings.api_60s_base_url,
            timeout=settings.timeout_seconds,
        )
    except InformationError as exc:
        await daily_brief.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Daily brief lookup failed")
        await daily_brief.finish("每日简报查询失败，请稍后再试。")

    if argument != "文字" and brief.image_url:
        try:
            image = await download_brief_image(
                brief.image_url,
                timeout=settings.timeout_seconds,
            )
        except InformationError as exc:
            logger.warning("Daily brief image unavailable, falling back to text: %s", exc)
        except Exception:
            logger.exception("Daily brief image download failed, falling back to text")
        else:
            await daily_brief.finish(
                MessageSegment.image(image)
                + f"\n{brief.date} {brief.weekday}｜内容来自公开资讯汇总"
            )

    await daily_brief.finish(_text_brief(brief.date, brief.weekday, brief.news, brief.tip))
