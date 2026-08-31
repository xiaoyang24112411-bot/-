"""Validated multi-sided dice rolling."""

import random
import re
from dataclasses import dataclass

from src.services.economy.errors import EconomyError

DICE_PATTERN = re.compile(r"^(\d+)[dD](\d+)$")


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
