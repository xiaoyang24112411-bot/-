"""Bounded local random choices; no model, network or persistent chat history."""

import random


class ChoiceError(ValueError):
    pass


def parse_choices(argument: str) -> tuple[str, ...]:
    if len(argument) > 1500:
        raise ChoiceError("选项内容太长，请控制在 1500 个字符以内。")
    parts = tuple(value.strip() for value in argument.replace("｜", "|").split("|"))
    if len(parts) > 20 or any(not value or len(value) > 60 for value in parts):
        raise ChoiceError("请提供 2～20 个非空选项，每项最多 60 字，用 | 分隔。")
    # Duplicated options must not silently increase their chance of being chosen.
    choices = tuple(dict.fromkeys(parts))
    if len(choices) < 2:
        raise ChoiceError("至少需要两个不同选项，例如：帮我选 火锅 | 烧烤 | 面条")
    return choices


def choose_one(argument: str, rng: random.Random | None = None) -> str:
    return (rng or random.SystemRandom()).choice(parse_choices(argument))


def shuffle_choices(argument: str, rng: random.Random | None = None) -> tuple[str, ...]:
    choices = list(parse_choices(argument))
    (rng or random.SystemRandom()).shuffle(choices)
    return tuple(choices)
