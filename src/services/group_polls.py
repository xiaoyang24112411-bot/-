"""Persistent, group-scoped single-choice polls with atomic revoting."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import aiosqlite

from src.services.economy.database import EconomyDatabase

MAX_INPUT_LENGTH = 800


class PollError(ValueError):
    """A safe, user-facing poll validation error."""


@dataclass(frozen=True)
class GroupPoll:
    id: int
    title: str
    options: tuple[str, ...]
    creator_user_id: int
    status: str
    counts: tuple[int, ...]


def parse_poll_creation(argument: str) -> tuple[str, tuple[str, ...]]:
    if len(argument) > MAX_INPUT_LENGTH:
        raise PollError("投票内容过长，标题和选项合计最多 800 字。")
    parts = tuple(part.strip() for part in argument.split("|"))
    title, options = parts[0], parts[1:]
    validate_poll_content(title, options)
    return title, options


def validate_poll_content(title: str, options: tuple[str, ...]) -> None:
    if not title.strip() or len(title) > 100:
        raise PollError("投票标题不能为空，且最多 100 字。")
    if not 2 <= len(options) <= 10:
        raise PollError("每个投票需要 2～10 个选项，用 | 分隔。")
    if any(not option.strip() or len(option) > 60 for option in options):
        raise PollError("投票选项不能为空，每项最多 60 字。")
    if len({option.strip().casefold() for option in options}) != len(options):
        raise PollError("投票选项不能重复。")
    if len(title) + sum(map(len, options)) + len(options) > MAX_INPUT_LENGTH:
        raise PollError("投票内容过长，标题和选项合计最多 800 字。")


def parse_poll_id(value: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]{0,18}", value) or int(value) > 2**63 - 1:
        raise PollError("投票编号和选项编号必须是正整数。")
    return int(value)


async def _read_poll(
    connection: aiosqlite.Connection, bot_id: int, group_id: int, poll_id: int
) -> GroupPoll:
    cursor = await connection.execute(
        "SELECT * FROM group_polls WHERE bot_id = ? AND group_id = ? AND id = ?",
        (bot_id, group_id, poll_id),
    )
    row = await cursor.fetchone()
    if row is None:
        raise PollError("当前群找不到这个投票，请检查编号。")
    options = tuple(json.loads(row["options_json"]))
    counts = [0] * len(options)
    cursor = await connection.execute(
        "SELECT option_number, COUNT(*) AS total FROM group_poll_votes "
        "WHERE bot_id = ? AND group_id = ? AND poll_id = ? GROUP BY option_number",
        (bot_id, group_id, poll_id),
    )
    for vote in await cursor.fetchall():
        counts[vote["option_number"] - 1] = vote["total"]
    return GroupPoll(
        row["id"], row["title"], options, row["creator_user_id"],
        row["status"], tuple(counts),
    )


async def create_poll(
    database: EconomyDatabase, *, bot_id: int, group_id: int, user_id: int,
    title: str, options: tuple[str, ...], request_id: str, max_active: int = 5,
) -> GroupPoll:
    title = title.strip()
    options = tuple(option.strip() for option in options)
    validate_poll_content(title, options)
    if not 1 <= max_active <= 50:
        raise PollError("投票数量配置无效，请联系管理员。")
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT id FROM group_polls WHERE bot_id = ? AND group_id = ? AND request_id = ?",
            (bot_id, group_id, request_id),
        )
        existing = await cursor.fetchone()
        if existing:
            return await _read_poll(connection, bot_id, group_id, existing["id"])
        cursor = await connection.execute(
            "SELECT COUNT(*) FROM group_polls WHERE bot_id = ? AND group_id = ? "
            "AND status = 'open'", (bot_id, group_id),
        )
        if (await cursor.fetchone())[0] >= max_active:
            raise PollError(f"本群最多同时进行 {max_active} 个投票，请先结束已有投票。")
        cursor = await connection.execute(
            "INSERT INTO group_polls (bot_id, group_id, creator_user_id, title, "
            "options_json, request_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (bot_id, group_id, user_id, title, json.dumps(options, ensure_ascii=False),
             request_id, datetime.now(timezone.utc).isoformat()),
        )
        return await _read_poll(connection, bot_id, group_id, cursor.lastrowid)


async def get_poll(
    database: EconomyDatabase, *, bot_id: int, group_id: int, poll_id: int,
) -> GroupPoll:
    async with database.connect() as connection:
        # A read transaction keeps status and tallies from different SELECTs consistent.
        await connection.execute("BEGIN")
        return await _read_poll(connection, bot_id, group_id, poll_id)


async def list_polls(
    database: EconomyDatabase, *, bot_id: int, group_id: int,
) -> list[GroupPoll]:
    async with database.connect() as connection:
        await connection.execute("BEGIN")
        cursor = await connection.execute(
            "SELECT id FROM group_polls WHERE bot_id = ? AND group_id = ? "
            "AND status = 'open' ORDER BY id DESC LIMIT 50", (bot_id, group_id),
        )
        rows = await cursor.fetchall()
        return [await _read_poll(connection, bot_id, group_id, row["id"]) for row in rows]


async def cast_vote(
    database: EconomyDatabase, *, bot_id: int, group_id: int, poll_id: int,
    user_id: int, option_number: int,
) -> GroupPoll:
    async with database.transaction() as connection:
        poll = await _read_poll(connection, bot_id, group_id, poll_id)
        if poll.status != "open":
            raise PollError("这个投票已经结束，不能再投票。")
        if not 1 <= option_number <= len(poll.options):
            raise PollError(f"选项编号应在 1～{len(poll.options)} 之间。")
        await connection.execute(
            "INSERT INTO group_poll_votes "
            "(bot_id, group_id, poll_id, user_id, option_number, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(bot_id, group_id, poll_id, user_id) DO UPDATE SET "
            "option_number = excluded.option_number, updated_at = excluded.updated_at",
            (bot_id, group_id, poll_id, user_id, option_number,
             datetime.now(timezone.utc).isoformat()),
        )
        return await _read_poll(connection, bot_id, group_id, poll_id)


async def close_poll(
    database: EconomyDatabase, *, bot_id: int, group_id: int, poll_id: int,
    user_id: int, is_manager: bool = False,
) -> GroupPoll:
    async with database.transaction() as connection:
        poll = await _read_poll(connection, bot_id, group_id, poll_id)
        if user_id != poll.creator_user_id and not is_manager:
            raise PollError("只有投票创建者、群管理或机器人管理员可以结束投票。")
        if poll.status != "closed":
            await connection.execute(
                "UPDATE group_polls SET status = 'closed', closed_at = ? "
                "WHERE bot_id = ? AND group_id = ? AND id = ?",
                (datetime.now(timezone.utc).isoformat(), bot_id, group_id, poll_id),
            )
        return await _read_poll(connection, bot_id, group_id, poll_id)


def format_poll(poll: GroupPoll) -> str:
    state = "进行中" if poll.status == "open" else "已结束"
    lines = [f"投票 #{poll.id}｜{state}", poll.title]
    lines.extend(
        f"{index}. {option}：{count} 票"
        for index, (option, count) in enumerate(
            zip(poll.options, poll.counts, strict=True), 1
        )
    )
    lines.append(f"共 {sum(poll.counts)} 人投票，每人一票，可重新投票修改选择。")
    if poll.status == "open":
        lines.append(f"发送：投票 {poll.id} 选项编号")
    return "\n".join(lines)
