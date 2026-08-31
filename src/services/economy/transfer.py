"""Atomic point transfers."""

from dataclasses import dataclass
from uuid import uuid4

from .common import account_balance, apply_change, ensure_account, iso_time
from .database import EconomyDatabase
from .errors import EconomyError


@dataclass(frozen=True)
class TransferResult:
    transfer_id: str
    amount: int
    sender_balance: int
    receiver_balance: int


async def transfer_points(
    database: EconomyDatabase,
    *,
    group_id: int,
    sender_user_id: int,
    receiver_user_id: int,
    amount: int,
    request_id: str,
) -> TransferResult:
    if sender_user_id == receiver_user_id:
        raise EconomyError("不能给自己转账。")
    if amount <= 0:
        raise EconomyError("转账积分必须是正整数。")

    now = iso_time()
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT id, amount FROM point_transfers WHERE request_id = ?",
            (request_id,),
        )
        duplicate = await cursor.fetchone()
        if duplicate is not None:
            raise EconomyError("这笔转账已经处理过了。")

        await ensure_account(connection, group_id, sender_user_id, now)
        await ensure_account(connection, group_id, receiver_user_id, now)
        if await account_balance(connection, group_id, sender_user_id) < amount:
            raise EconomyError("积分不足，无法完成转账。")

        transfer_id = uuid4().hex
        await connection.execute(
            "INSERT INTO point_transfers"
            "(id, group_id, sender_user_id, receiver_user_id, amount, request_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                transfer_id,
                group_id,
                sender_user_id,
                receiver_user_id,
                amount,
                request_id,
                now,
            ),
        )
        sender_balance = await apply_change(
            connection,
            group_id=group_id,
            user_id=sender_user_id,
            amount=-amount,
            event_type="transfer_out",
            reference_id=transfer_id,
            counterparty_user_id=receiver_user_id,
            note="积分转账支出",
            now=now,
        )
        receiver_balance = await apply_change(
            connection,
            group_id=group_id,
            user_id=receiver_user_id,
            amount=amount,
            event_type="transfer_in",
            reference_id=transfer_id,
            counterparty_user_id=sender_user_id,
            note="积分转账收入",
            now=now,
        )
    return TransferResult(transfer_id, amount, sender_balance, receiver_balance)
