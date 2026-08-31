"""Compact one-shot text life simulator."""

import random
from dataclasses import dataclass

TALENTS = (
    "天生乐观",
    "过目不忘",
    "运动健将",
    "社交达人",
    "艺术细胞",
    "商业嗅觉",
    "坚定意志",
    "好运体质",
    "技术宅",
    "冒险家",
    "治愈者",
    "时间管理大师",
)

EVENTS = {
    0: ("你出生在一个普通但温暖的家庭。", "你带着响亮的哭声来到这个世界。"),
    6: ("你第一次走进学校，对一切都很好奇。", "你交到了童年最要好的朋友。"),
    12: ("你发现了真正喜欢的一门课。", "一次比赛让你体会到努力的意义。"),
    18: ("你站在人生路口，做出第一个重要选择。", "你离开熟悉的地方追寻新生活。"),
    25: ("你开始独立生活，也学会承担责任。", "一个偶然机会改变了职业方向。"),
    35: ("长期积累终于带来稳定的收获。", "你重新审视生活，并调整了前进方向。"),
    50: ("你更在意健康、家人与内心的平静。", "你把经验分享给了更年轻的人。"),
    65: ("你开始享受从容的生活节奏。", "你完成了一件惦记多年的心愿。"),
    80: ("回望一生，你发现平凡日子也闪闪发光。", "故事接近尾声，但影响仍在延续。"),
}


@dataclass(frozen=True)
class LifeResult:
    talents: tuple[str, ...]
    intelligence: int
    constitution: int
    family: int
    luck: int
    events: tuple[tuple[int, str], ...]
    score: int
    ending: str


def simulate_life(rng: random.Random | None = None) -> LifeResult:
    generator = rng or random.SystemRandom()
    talents = tuple(generator.sample(TALENTS, 3))
    attributes = [generator.randint(3, 10) for _ in range(4)]
    events = tuple((age, generator.choice(options)) for age, options in EVENTS.items())
    score = sum(attributes) * 2 + generator.randint(5, 25)
    if score >= 85:
        ending = "闪耀人生：你活成了自己真正喜欢的样子。"
    elif score >= 65:
        ending = "充实人生：有遗憾，也有许多值得珍藏的时刻。"
    else:
        ending = "平凡人生：故事没有传奇，但温柔而真实。"
    return LifeResult(
        talents=talents,
        intelligence=attributes[0],
        constitution=attributes[1],
        family=attributes[2],
        luck=attributes[3],
        events=events,
        score=score,
        ending=ending,
    )
