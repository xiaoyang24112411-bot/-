"""Small, unofficial text-only gacha simulations for entertainment."""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class GachaItem:
    rarity: int
    name: str


GENSHIN = {
    3: ("冷刃", "黎明神剑", "弹弓", "讨龙英杰谭", "黑缨枪"),
    4: ("班尼特", "行秋", "香菱", "菲谢尔", "祭礼剑", "西风长枪"),
    5: ("迪卢克", "琴", "莫娜", "刻晴", "七七", "提纳里"),
}
ARKNIGHTS = {
    3: ("芬", "香草", "玫兰莎", "克洛丝", "斑点"),
    4: ("砾", "桃金娘", "古米", "白雪", "慕斯"),
    5: ("德克萨斯", "白面鸮", "拉普兰德", "幽灵鲨", "蓝毒"),
    6: ("能天使", "银灰", "艾雅法拉", "塞雷娅", "推进之王"),
}
FGO = {
    3: ("罗宾汉", "美狄亚", "库·丘林", "牛若丸", "荆轲"),
    4: ("卫宫", "尼托克丽丝", "赫拉克勒斯", "兰斯洛特", "玛尔达"),
    5: ("阿尔托莉雅", "诸葛孔明", "贞德", "俄里翁", "弗拉德三世"),
}


def _choose(
    pool: dict[int, tuple[str, ...]], rates: tuple[tuple[float, int], ...], rng
) -> GachaItem:
    roll = rng.random()
    total = 0.0
    rarity = rates[-1][1]
    for probability, candidate in rates:
        total += probability
        if roll < total:
            rarity = candidate
            break
    return GachaItem(rarity, rng.choice(pool[rarity]))


def draw_genshin(count: int = 10, rng: random.Random | None = None) -> tuple[GachaItem, ...]:
    generator = rng or random.SystemRandom()
    results = [
        _choose(GENSHIN, ((0.006, 5), (0.051, 4), (0.943, 3)), generator)
        for _ in range(count)
    ]
    if count >= 10 and all(item.rarity < 4 for item in results):
        results[-1] = GachaItem(4, generator.choice(GENSHIN[4]))
    return tuple(results)


def draw_arknights(count: int = 10, rng: random.Random | None = None) -> tuple[GachaItem, ...]:
    generator = rng or random.SystemRandom()
    results = [
        _choose(ARKNIGHTS, ((0.02, 6), (0.08, 5), (0.50, 4), (0.40, 3)), generator)
        for _ in range(count)
    ]
    if count >= 10 and all(item.rarity < 5 for item in results):
        results[-1] = GachaItem(5, generator.choice(ARKNIGHTS[5]))
    return tuple(results)


def draw_fgo(count: int = 11, rng: random.Random | None = None) -> tuple[GachaItem, ...]:
    generator = rng or random.SystemRandom()
    results = [_choose(FGO, ((0.01, 5), (0.03, 4), (0.96, 3)), generator) for _ in range(count)]
    if count >= 11 and all(item.rarity < 4 for item in results):
        results[-1] = GachaItem(4, generator.choice(FGO[4]))
    return tuple(results)
