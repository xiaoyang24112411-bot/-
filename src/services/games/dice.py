"""Validated multi-sided dice rolling."""

import random
import re
from dataclasses import dataclass

from src.services.economy.errors import EconomyError

DICE_PATTERN = re.compile(r"^(\d+)[dD](\d+)$")
RANGE_PATTERN = re.compile(r"^(-?\d+)\s*[-~～]\s*(-?\d+)$")


@dataclass(frozen=True)
class DiceResult:
    count: int
    faces: int
    rolls: tuple[int, ...]

    @property
    def total(self) -> int:
        return sum(self.rolls)


def roll_dice(argument: str, rng: random.Random | None = None) -> DiceResult:
    text = argument.strip() or "1d6"
    matched = DICE_PATTERN.fullmatch(text)
    if matched is None:
        raise EconomyError("用法：掷骰子 [数量d面数]，例如：掷骰子 2d6")

    count, faces = (int(value) for value in matched.groups())
    if not 1 <= count <= 20:
        raise EconomyError("骰子数量必须在 1～20 之间。")
    if not 2 <= faces <= 1000:
        raise EconomyError("骰子面数必须在 2～1000 之间。")

    generator = rng or random.SystemRandom()
    rolls = tuple(generator.randint(1, faces) for _ in range(count))
    return DiceResult(count=count, faces=faces, rolls=rolls)


def roll_range(argument: str, rng: random.Random | None = None) -> int:
    text = argument.strip() or "1-100"
    matched = RANGE_PATTERN.fullmatch(text)
    if matched is None:
        raise EconomyError("用法：/roll 最小值-最大值，例如：/roll 1-100")
    lower, upper = (int(value) for value in matched.groups())
    if lower > upper:
        raise EconomyError("最小值不能大于最大值。")
    if upper - lower > 1_000_000_000:
        raise EconomyError("随机范围过大。")
    generator = rng or random.SystemRandom()
    return generator.randint(lower, upper)
