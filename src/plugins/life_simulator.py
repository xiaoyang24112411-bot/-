"""One-shot text life restart simulator."""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.economy.commands import command_text
from src.services.games.life_simulator import simulate_life


def is_life_simulator(event: GroupMessageEvent) -> bool:
    return (
        command_text(event, "人生重开") is not None or command_text(event, "人生模拟") is not None
    )


life_simulator = on_message(rule=Rule(is_life_simulator), priority=10, block=True)


@life_simulator.handle()
async def handle_life_simulator(event: GroupMessageEvent) -> None:
    result = simulate_life()
    lines = [
        "人生重开模拟：",
        "天赋：" + "、".join(result.talents),
        (
            f"属性：智力 {result.intelligence}｜体质 {result.constitution}｜"
            f"家境 {result.family}｜幸运 {result.luck}"
        ),
    ]
    lines.extend(f"{age}岁：{text}" for age, text in result.events)
    lines.append(f"人生评分：{result.score}\n结局：{result.ending}")
    await life_simulator.finish(MessageSegment.at(event.user_id) + "\n" + "\n".join(lines))
