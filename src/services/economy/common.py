"""Internal account and ledger primitives used inside SQLite transactions."""

from datetime import UTC, datetime

import aiosqlite


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_time(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat(timespec="seconds")


async def ensure_account(
    connection: aiosqlite.Connection,
    group_id: int,
    user_id: int,
    now: str,
) -> None:
    await connection.execute(
        "INSERT OR IGNORE INTO economy_accounts"
        "(group_id, user_id, balance, total_earned, total_spent, created_at, updated_at) "
        "VALUES (?, ?, 0, 0, 0, ?, ?)",
        (group_id, user_id, now, now),
    )


async def account_balance(
    connection: aiosqlite.Connection,
    group_id: int,
    user_id: int,
) -> int:
    cursor = await connection.execute(
        "SELECT balance FROM economy_accounts WHERE group_id = ? AND user_id = ?",
        (group_id, user_id),
    )
    row = await cursor.fetchone()
    return int(row["balance"]) if row else 0


async def apply_change(
    connection: aiosqlite.Connection,
    *,
    group_id: int,
    user_id: int,
    amount: int,
    event_type: str,
    reference_id: str,
    now: str,
    counterparty_user_id: int | None = None,
    note: str | None = None,
) -> int:
    if amount == 0:
        return await account_balance(connection, group_id, user_id)

    await ensure_account(connection, group_id, user_id, now)
    current = await account_balance(connection, group_id, user_id)
    new_balance = current + amount
    if new_balance < 0:
        raise ValueError("insufficient balance")

    earned = max(amount, 0)
    spent = max(-amount, 0)
    await connection.execute(
        "UPDATE economy_accounts SET balance = ?, total_earned = total_earned + ?, "
        "total_spent = total_spent + ?, updated_at = ? WHERE group_id = ? AND user_id = ?",
        (new_balance, earned, spent, now, group_id, user_id),
    )
    await connection.execute(
        "INSERT INTO point_transactions"
        "(group_id, user_id, change_amount, balance_after, event_type, reference_id, "
        "counterparty_user_id, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            group_id,
            user_id,
            amount,
            new_balance,
            event_type,
            reference_id,
            counterparty_user_id,
            note,
            now,
        ),
    )
    return new_balance
