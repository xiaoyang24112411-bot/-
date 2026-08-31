"""Account balance queries."""

from dataclasses import dataclass

from .common import ensure_account, iso_time
from .database import EconomyDatabase


@dataclass(frozen=True)
class Account:
    group_id: int
    user_id: int
    balance: int
    total_earned: int
    total_spent: int


async def get_account(database: EconomyDatabase, group_id: int, user_id: int) -> Account:
    now = iso_time()
    async with database.transaction() as connection:
        await ensure_account(connection, group_id, user_id, now)
        cursor = await connection.execute(
            "SELECT balance, total_earned, total_spent FROM economy_accounts "
            "WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        )
        row = await cursor.fetchone()
    assert row is not None
    return Account(group_id, user_id, row["balance"], row["total_earned"], row["total_spent"])
