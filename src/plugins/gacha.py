"""Unofficial text-only game draw commands."""

from collections import Counter

from nonebot import on_fullmatch

from src.services.games.gacha import GachaItem, draw_arknights, draw_fgo, draw_genshin

genshin = on_fullmatch(
    ("原神10抽", "原神十抽", "原神十连", "/原神10抽", "/原神十抽", "/原神十连"),
    priority=10,
    block=True,
)
arknights = on_fullmatch(
    ("方舟十抽", "方舟十连", "/方舟十抽", "/方舟十连"), priority=10, block=True
)
fgo = on_fullmatch(("fgo一井", "FGO一井", "/fgo一井", "/FGO一井"), priority=10, block=True)


def _format(title: str, items: tuple[GachaItem, ...]) -> str:
    counts = Counter(item.rarity for item in items)
    rare = [item for item in items if item.rarity >= 4]
    rare_text = "、".join(f"{item.rarity}★{item.name}" for item in rare) or "无"
    summary = "｜".join(f"{rarity}★×{counts[rarity]}" for rarity in sorted(counts, reverse=True))
    return f"{title}（非官方娱乐模拟）\n{summary}\n稀有结果：{rare_text}"


@genshin.handle()
async def handle_genshin() -> None:
    await genshin.finish(_format("原神十连", draw_genshin()))


@arknights.handle()
async def handle_arknights() -> None:
    await arknights.finish(_format("方舟十连", draw_arknights()))


@fgo.handle()
async def handle_fgo() -> None:
    # Keep output compact: simulate 30 eleven-pulls instead of dumping 330 lines.
    await fgo.finish(_format("FGO 一井（330 抽）", draw_fgo(330)))
