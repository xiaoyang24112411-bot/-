"""A small arithmetic evaluator that never executes Python code."""

import ast
import math
import operator


class CalculatorError(ValueError):
    """Raised for invalid or unsafe calculator input."""


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _evaluate(node: ast.AST, depth: int = 0) -> int | float:
    if depth > 20:
        raise CalculatorError("算式嵌套过深。")
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, depth + 1)
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate(node.operand, depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate(node.left, depth + 1)
        right = _evaluate(node.right, depth + 1)
        if isinstance(node.op, ast.Pow) and (abs(right) > 10 or abs(left) > 1_000_000):
            raise CalculatorError("幂运算数值过大。")
        try:
            value = _BINARY_OPERATORS[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise CalculatorError("不能除以零。") from exc
        if not math.isfinite(float(value)) or abs(value) > 10**100:
            raise CalculatorError("计算结果过大。")
        return value
    raise CalculatorError("只支持数字、括号和 + - * / // % ** 运算。")


def calculate(expression: str) -> str:
    text = expression.strip()
    if not text:
        raise CalculatorError("用法：/calc 算式，例如：/calc 1+2*3")
    if len(text) > 200:
        raise CalculatorError("算式过长，请控制在 200 个字符以内。")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError("算式格式不正确。") from exc
    value = _evaluate(tree)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return format(value, ".12g")
