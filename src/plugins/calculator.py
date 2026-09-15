"""Safe local calculator command."""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg

from src.services.calculator import CalculatorError, calculate

calculator = on_command("calc", aliases={"计算"}, priority=10, block=True)


@calculator.handle()
async def handle_calculator(args: Message = CommandArg()) -> None:  # noqa: B008
    try:
        result = calculate(args.extract_plain_text())
    except CalculatorError as exc:
        await calculator.finish(str(exc))
    await calculator.finish(f"计算结果：{result}")
