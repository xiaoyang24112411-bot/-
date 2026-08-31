"""Point red packet creation, claiming, and expiry refunds."""

import random
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

import aiosqlite

from .common import account_balance, apply_change, ensure_account, iso_time, utc_now
from .database import EconomyDatabase
from .errors import EconomyError


@dataclass(frozen=True)
class RedPacket:
    packet_id: str
    total_amount: int
    total_count: int
    sender_balance: int
    expires_at: str

    @property
    def short_id(self) -> str:
        return self.packet_id[:8]


@dataclass(frozen=True)
class ClaimResult:
    packet_id: str
    amount: int
    balance: int
    remaining_count: int


async def _refund_packet(
    connection: aiosqlite.Connection,
    row: aiosqlite.Row,
    now: str,
) -> None:
    remaining = int(row["remaining_amount"])
    if remaining > 0:
        await apply_change(
            connection,
            group_id=row["group_id"],
            user_id=row["sender_user_id"],
            amount=remaining,
            event_type="red_packet_refund",
            reference_id=row["id"],
            note="红包过期退款",
            now=now,
        )
    await connection.execute(
        "UPDATE red_packets SET remaining_amount = 0, remaining_count = 0, "
        "status = 'refunded', refunded_at = ? WHERE id = ?",
        (now, row["id"]),
    )


async def create_red_packet(
    database: EconomyDatabase,
    *,
    group_id: int,
    sender_user_id: int,
    total_amount: int,
    total_count: int,
    request_id: str,
    ttl_seconds: int,
) -> RedPacket:
    if total_amount <= 0 or total_count <= 0:
        raise EconomyError("红包积分和份数必须是正整数。")
    if total_amount < total_count:
        raise EconomyError("红包总积分不能少于红包份数。")

    current = utc_now()
    now = iso_time(current)
    expires_at = iso_time(current + timedelta(seconds=max(60, ttl_seconds)))
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT id FROM red_packets WHERE request_id = ?",
            (request_id,),
        )
        if await cursor.fetchone() is not None:
            raise EconomyError("这个红包已经发送过了。")

        await ensure_account(connection, group_id, sender_user_id, now)
        if await account_balance(connection, group_id, sender_user_id) < total_amount:
            raise EconomyError("积分不足，无法发送红包。")

        packet_id = uuid4().hex
        await connection.execute(
            "INSERT INTO red_packets"
            "(id, group_id, sender_user_id, total_amount, total_count, remaining_amount, "
            "remaining_count, status, request_id, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)",
            (
                packet_id,
                group_id,
                sender_user_id,
                total_amount,
                total_count,
                total_amount,
                total_count,
                request_id,
                expires_at,
                now,
            ),
        )
        balance = await apply_change(
            connection,
            group_id=group_id,
            user_id=sender_user_id,
            amount=-total_amount,
            event_type="red_packet_create",
            reference_id=packet_id,
            note=f"发送 {total_count} 份积分红包",
            now=now,
        )
    return RedPacket(packet_id, total_amount, total_count, balance, expires_at)


async def claim_red_packet(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    request_id: str,
    packet_token: str | None = None,
    rng: random.Random | None = None,
) -> ClaimResult:
    now = iso_time()
    generator = rng or random.SystemRandom()
    expired = False
    result: ClaimResult | None = None
    async with database.transaction() as connection:
        duplicate_cursor = await connection.execute(
            "SELECT packet_id FROM red_packet_claims WHERE request_id = ?",
            (request_id,),
        )
        if await duplicate_cursor.fetchone() is not None:
            raise EconomyError("这次抢红包请求已经处理过了。")

        if packet_token:
            cursor = await connection.execute(
                "SELECT * FROM red_packets WHERE group_id = ? AND id LIKE ? "
                "ORDER BY created_at DESC LIMIT 1",
                (group_id, f"{packet_token.lower()}%"),
            )
        else:
            cursor = await connection.execute(
                "SELECT * FROM red_packets WHERE group_id = ? AND status = 'open' "
                "ORDER BY created_at DESC LIMIT 1",
                (group_id,),
            )
        packet = await cursor.fetchone()
        if packet is None:
            raise EconomyError("当前没有可领取的积分红包。")

        if packet["status"] != "open":
            raise EconomyError("这个红包已经领完或失效了。")
        if packet["expires_at"] <= now:
            await _refund_packet(connection, packet, now)
            expired = True
        else:
            claim_cursor = await connection.execute(
                "SELECT 1 FROM red_packet_claims WHERE packet_id = ? AND user_id = ?",
                (packet["id"], user_id),
            )
            if await claim_cursor.fetchone() is not None:
                raise EconomyError("你已经抢过这个红包了。")

            remaining_amount = int(packet["remaining_amount"])
            remaining_count = int(packet["remaining_count"])
            if remaining_amount <= 0 or remaining_count <= 0:
                raise EconomyError("这个红包已经被抢完了。")

            if remaining_count == 1:
                amount = remaining_amount
            else:
                guaranteed_max = remaining_amount - (remaining_count - 1)
                double_mean = max(1, remaining_amount * 2 // remaining_count)
                amount = generator.randint(1, min(guaranteed_max, double_mean))

            new_amount = remaining_amount - amount
            new_count = remaining_count - 1
            status = "exhausted" if new_count == 0 else "open"
            await connection.execute(
                "UPDATE red_packets SET remaining_amount = ?, remaining_count = ?, status = ? "
                "WHERE id = ?",
                (new_amount, new_count, status, packet["id"]),
            )
            await connection.execute(
                "INSERT INTO red_packet_claims"
                "(packet_id, user_id, amount, request_id, claimed_at) VALUES (?, ?, ?, ?, ?)",
                (packet["id"], user_id, amount, request_id, now),
            )
            balance = await apply_change(
                connection,
                group_id=group_id,
                user_id=user_id,
                amount=amount,
                event_type="red_packet_claim",
                reference_id=packet["id"],
                counterparty_user_id=packet["sender_user_id"],
                note="领取积分红包",
                now=now,
            )
            result = ClaimResult(packet["id"], amount, balance, new_count)
    if expired:
        raise EconomyError("这个红包已经过期，剩余积分已退回。")
    assert result is not None
    return result
