"""Persistent group Gomoku commands."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.services.economy import EconomyError, get_economy_database
from src.services.economy.commands import command_text
from src.services.games.gomoku import (
    abort_gomoku_game,
    create_gomoku_game,
    get_gomoku_game,
    join_gomoku_game,
    parse_coordinate,
    place_gomoku_stone,
    render_board,
)


def _rule(command: str) -> Rule:
    return Rule(lambda event: command_text(event, command) is not None)


create_game = on_message(rule=_rule("五子棋"), priority=10, block=True)
join_game = on_message(rule=_rule("加入五子棋"), priority=10, block=True)
place_stone = on_message(rule=_rule("落子"), priority=10, block=True)
show_board = on_message(rule=_rule("五子棋棋盘"), priority=10, block=True)
end_game = on_message(rule=_rule("结束五子棋"), priority=10, block=True)


@create_game.handle()
async def handle_create_game(event: GroupMessageEvent) -> None:
    argument = (command_text(event, "五子棋") or "").strip()
    if argument not in {"", "创建"}:
        await create_game.finish("五子棋指令：五子棋｜加入五子棋｜落子 H8｜五子棋棋盘｜结束五子棋")
    try:
        await create_gomoku_game(get_economy_database(), event.group_id, event.user_id)
    except EconomyError as exc:
        await create_game.finish(str(exc))
    except Exception:
        logger.exception("Gomoku game creation failed")
        await create_game.finish("五子棋创建失败，请稍后再试。")
    await create_game.finish(
        MessageSegment.at(event.user_id) + " 已创建五子棋对局并执黑。另一位群友请发送“加入五子棋”。"
    )


@join_game.handle()
async def handle_join_game(event: GroupMessageEvent) -> None:
    try:
        game = await join_gomoku_game(get_economy_database(), event.group_id, event.user_id)
    except EconomyError as exc:
        await join_game.finish(str(exc))
    except Exception:
        logger.exception("Gomoku join failed")
        await join_game.finish("加入五子棋失败，请稍后再试。")
    await join_game.finish(
        "五子棋开始！\n"
        + MessageSegment.at(game.black_user_id)
        + " 执黑先手，使用“落子 H8”。\n"
        + render_board(game)
    )


@place_stone.handle()
async def handle_place_stone(event: GroupMessageEvent) -> None:
    try:
        column, row = parse_coordinate(command_text(event, "落子") or "")
        result = await place_gomoku_stone(
            get_economy_database(),
            group_id=event.group_id,
            user_id=event.user_id,
            column=column,
            row=row,
        )
    except EconomyError as exc:
        await place_stone.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Gomoku move failed")
        await place_stone.finish("五子棋落子失败，请稍后再试。")

    coordinate = f"{chr(ord('A') + result.column)}{result.row + 1}"
    lines = [f"落子：{coordinate}", render_board(result.game)]
    if result.game.winner_user_id:
        await place_stone.finish(
            "\n".join(lines) + "\n胜者：" + MessageSegment.at(result.game.winner_user_id)
        )
    if result.game.status == "draw":
        await place_stone.finish("\n".join(lines) + "\n棋盘已满，本局平局。")
    await place_stone.finish(
        "\n".join(lines) + "\n轮到：" + MessageSegment.at(result.game.current_user_id)
    )


@show_board.handle()
async def handle_show_board(event: GroupMessageEvent) -> None:
    try:
        game = await get_gomoku_game(get_economy_database(), event.group_id)
    except EconomyError as exc:
        await show_board.finish(str(exc))
    except Exception:
        logger.exception("Gomoku board lookup failed")
        await show_board.finish("棋盘查询失败，请稍后再试。")
    status = game.status
    await show_board.finish(f"五子棋状态：{status}\n{render_board(game)}")


@end_game.handle()
async def handle_end_game(event: GroupMessageEvent) -> None:
    try:
        await abort_gomoku_game(get_economy_database(), event.group_id, event.user_id)
    except EconomyError as exc:
        await end_game.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Gomoku abort failed")
        await end_game.finish("结束五子棋失败，请稍后再试。")
    await end_game.finish("本群五子棋对局已结束。")
