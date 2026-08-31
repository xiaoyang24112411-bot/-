"""Persistent one-active-game-per-group Gomoku service."""

import json
import re
import uuid
from dataclasses import dataclass

from src.services.economy.common import iso_time
from src.services.economy.database import EconomyDatabase
from src.services.economy.errors import EconomyError

BOARD_SIZE = 15
ACTIVE_STATUSES = {"waiting", "playing"}
COORDINATE_PATTERN = re.compile(r"^([A-Oa-o])(1[0-5]|[1-9])$")


@dataclass(frozen=True)
class GomokuGame:
    game_id: str
    group_id: int
    black_user_id: int
    white_user_id: int | None
    status: str
    current_user_id: int | None
    board: tuple[int, ...]
    winner_user_id: int | None


@dataclass(frozen=True)
class GomokuMoveResult:
    game: GomokuGame
    column: int
    row: int


def parse_coordinate(text: str) -> tuple[int, int]:
    matched = COORDINATE_PATTERN.fullmatch(text.strip())
    if matched is None:
        raise EconomyError("落子格式错误，请使用 A1～O15，例如：落子 H8")
    column = ord(matched.group(1).upper()) - ord("A")
    row = int(matched.group(2)) - 1
    return column, row


def _from_row(row) -> GomokuGame:
    board = tuple(int(value) for value in json.loads(row["board_json"]))
    if len(board) != BOARD_SIZE * BOARD_SIZE:
        raise ValueError("invalid stored Gomoku board")
    return GomokuGame(
        game_id=str(row["game_id"]),
        group_id=int(row["group_id"]),
        black_user_id=int(row["black_user_id"]),
        white_user_id=int(row["white_user_id"]) if row["white_user_id"] else None,
        status=str(row["status"]),
        current_user_id=int(row["current_user_id"]) if row["current_user_id"] else None,
        board=board,
        winner_user_id=int(row["winner_user_id"]) if row["winner_user_id"] else None,
    )


async def get_gomoku_game(database: EconomyDatabase, group_id: int) -> GomokuGame:
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT * FROM gomoku_games WHERE group_id = ?", (group_id,)
        )
        row = await cursor.fetchone()
    if row is None:
        raise EconomyError("本群当前没有五子棋对局，发送“五子棋”创建。")
    return _from_row(row)


async def create_gomoku_game(
    database: EconomyDatabase,
    group_id: int,
    creator_user_id: int,
) -> GomokuGame:
    timestamp = iso_time()
    game_id = uuid.uuid4().hex
    board_json = json.dumps([0] * (BOARD_SIZE * BOARD_SIZE))
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT status FROM gomoku_games WHERE group_id = ?", (group_id,)
        )
        existing = await cursor.fetchone()
        if existing is not None and existing["status"] in ACTIVE_STATUSES:
            raise EconomyError("本群已有进行中的五子棋对局。")
        await connection.execute("DELETE FROM gomoku_games WHERE group_id = ?", (group_id,))
        await connection.execute(
            "INSERT INTO gomoku_games"
            "(group_id, game_id, black_user_id, status, board_json, created_at, updated_at) "
            "VALUES (?, ?, ?, 'waiting', ?, ?, ?)",
            (group_id, game_id, creator_user_id, board_json, timestamp, timestamp),
        )
        cursor = await connection.execute(
            "SELECT * FROM gomoku_games WHERE group_id = ?", (group_id,)
        )
        return _from_row(await cursor.fetchone())


async def join_gomoku_game(
    database: EconomyDatabase,
    group_id: int,
    user_id: int,
) -> GomokuGame:
    timestamp = iso_time()
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT * FROM gomoku_games WHERE group_id = ?", (group_id,)
        )
        row = await cursor.fetchone()
        if row is None or row["status"] != "waiting":
            raise EconomyError("本群没有等待加入的五子棋对局。")
        if int(row["black_user_id"]) == user_id:
            raise EconomyError("不能同时担任黑棋和白棋，请等待另一位群友。")
        await connection.execute(
            "UPDATE gomoku_games SET white_user_id = ?, status = 'playing', "
            "current_user_id = black_user_id, updated_at = ? WHERE group_id = ?",
            (user_id, timestamp, group_id),
        )
        cursor = await connection.execute(
            "SELECT * FROM gomoku_games WHERE group_id = ?", (group_id,)
        )
        return _from_row(await cursor.fetchone())


def _has_five(board: list[int], column: int, row: int, stone: int) -> bool:
    for delta_column, delta_row in ((1, 0), (0, 1), (1, 1), (1, -1)):
        total = 1
        for direction in (-1, 1):
            next_column = column + delta_column * direction
            next_row = row + delta_row * direction
            while (
                0 <= next_column < BOARD_SIZE
                and 0 <= next_row < BOARD_SIZE
                and board[next_row * BOARD_SIZE + next_column] == stone
            ):
                total += 1
                next_column += delta_column * direction
                next_row += delta_row * direction
        if total >= 5:
            return True
    return False


async def place_gomoku_stone(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    column: int,
    row: int,
) -> GomokuMoveResult:
    if not (0 <= column < BOARD_SIZE and 0 <= row < BOARD_SIZE):
        raise EconomyError("落子位置超出棋盘范围。")
    timestamp = iso_time()
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT * FROM gomoku_games WHERE group_id = ?", (group_id,)
        )
        stored = await cursor.fetchone()
        if stored is None or stored["status"] != "playing":
            raise EconomyError("本群当前没有正在进行的五子棋对局。")
        game = _from_row(stored)
        if game.current_user_id != user_id:
            raise EconomyError("还没轮到你落子。")

        board = list(game.board)
        position = row * BOARD_SIZE + column
        if board[position] != 0:
            raise EconomyError("这个位置已经有棋子了。")
        stone = 1 if user_id == game.black_user_id else 2
        board[position] = stone

        if _has_five(board, column, row, stone):
            status = "black_won" if stone == 1 else "white_won"
            current_user_id = None
            winner_user_id = user_id
        elif all(board):
            status = "draw"
            current_user_id = None
            winner_user_id = None
        else:
            status = "playing"
            current_user_id = (
                game.white_user_id if user_id == game.black_user_id else game.black_user_id
            )
            winner_user_id = None

        await connection.execute(
            "UPDATE gomoku_games SET status = ?, current_user_id = ?, board_json = ?, "
            "winner_user_id = ?, updated_at = ? WHERE group_id = ?",
            (
                status,
                current_user_id,
                json.dumps(board),
                winner_user_id,
                timestamp,
                group_id,
            ),
        )
        cursor = await connection.execute(
            "SELECT * FROM gomoku_games WHERE group_id = ?", (group_id,)
        )
        updated = _from_row(await cursor.fetchone())
    return GomokuMoveResult(updated, column, row)


async def abort_gomoku_game(
    database: EconomyDatabase,
    group_id: int,
    user_id: int,
) -> GomokuGame:
    timestamp = iso_time()
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT * FROM gomoku_games WHERE group_id = ?", (group_id,)
        )
        row = await cursor.fetchone()
        if row is None or row["status"] not in ACTIVE_STATUSES:
            raise EconomyError("本群没有可以结束的五子棋对局。")
        game = _from_row(row)
        if user_id not in {game.black_user_id, game.white_user_id}:
            raise EconomyError("只有对局中的玩家可以结束棋局。")
        await connection.execute(
            "UPDATE gomoku_games SET status = 'aborted', current_user_id = NULL, "
            "updated_at = ? WHERE group_id = ?",
            (timestamp, group_id),
        )
        cursor = await connection.execute(
            "SELECT * FROM gomoku_games WHERE group_id = ?", (group_id,)
        )
        return _from_row(await cursor.fetchone())


def render_board(game: GomokuGame) -> str:
    symbols = {0: "·", 1: "●", 2: "○"}
    lines = ["   " + " ".join(chr(ord("A") + index) for index in range(BOARD_SIZE))]
    for row in range(BOARD_SIZE):
        cells = game.board[row * BOARD_SIZE : (row + 1) * BOARD_SIZE]
        lines.append(f"{row + 1:>2} " + " ".join(symbols[value] for value in cells))
    return "\n".join(lines)
