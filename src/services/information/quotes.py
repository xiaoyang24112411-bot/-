"""Local, short, original-style copywriting collection."""

import random
from dataclasses import dataclass

from .errors import InformationError

QUOTES = {
    "治愈": (
        "慢一点也没关系，抵达从来不只属于赶路的人。",
        "把今天照顾好，明天会自己长出答案。",
        "风会越过低谷，也会把新的花期带到你身边。",
        "允许生活偶尔留白，安静也是一种生长。",
    ),
    "热血": (
        "真正的出发，不是等风来，而是先迈出那一步。",
        "地图没有画完的地方，正适合写下你的名字。",
        "困难只负责挡路，方向仍然由你决定。",
        "热爱不是一时沸腾，而是冷却之后仍愿意前进。",
    ),
    "成长": (
        "成长不是变得无坚不摧，而是学会带着裂痕继续发光。",
        "每一次认真选择，都在悄悄塑造未来的自己。",
        "答案不一定藏在远方，也可能在你坚持过的日常里。",
        "接受自己的速度，也别忘了继续向前。",
    ),
    "古风": (
        "山水有归期，清风知我意。",
        "且将新火试新茶，心安之处便是天涯。",
        "长路自有灯火，岁月不负从容。",
        "一程烟雨一程晴，行到云开月自明。",
    ),
}


@dataclass(frozen=True)
class Quote:
    category: str
    text: str


def random_quote(category: str = "", *, rng: random.Random | None = None) -> Quote:
    normalized = category.strip()
    chooser = rng or random.SystemRandom()
    if normalized and normalized not in QUOTES:
        raise InformationError("可用文案分类：" + "、".join(QUOTES))
    selected_category = normalized or chooser.choice(tuple(QUOTES))
    return Quote(selected_category, chooser.choice(QUOTES[selected_category]))
