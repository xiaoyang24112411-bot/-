import asyncio
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.services.economy.accounts import get_account
from src.services.economy.checkin import check_in
from src.services.economy.commands import parse_positive_integers
from src.services.economy.common import apply_change, iso_time
from src.services.economy.database import EconomyDatabase
from src.services.economy.errors import EconomyError
from src.services.economy.red_packets import claim_red_packet, create_red_packet
from src.services.economy.robbery import play_robbery
from src.services.economy.shop import (
    create_product,
    fulfill_order,
    redeem_product,
    refund_order,
)
from src.services.economy.transfer import transfer_points


def make_database(tmp_path) -> EconomyDatabase:
    return EconomyDatabase(tmp_path / "economy.sqlite3")


async def seed_points(
    database: EconomyDatabase,
    group_id: int,
    user_id: int,
    amount: int,
    reference: str,
) -> int:
    async with database.transaction() as connection:
        return await apply_change(
            connection,
            group_id=group_id,
            user_id=user_id,
            amount=amount,
            event_type="test_seed",
            reference_id=reference,
            note="test",
            now=iso_time(),
        )


@pytest.mark.asyncio
async def test_database_schema_and_daily_checkin(tmp_path):
    database = make_database(tmp_path)
    current = datetime(2026, 8, 30, 9, 0, tzinfo=timezone.utc)

    result = await check_in(
        database,
        100,
        200,
        10,
        20,
        now=current,
        rng=random.Random(1),
    )

    assert 10 <= result.reward <= 20
    assert result.balance == result.reward
    with pytest.raises(EconomyError, match="已经签到"):
        await check_in(database, 100, 200, 10, 20, now=current)

    other_group = await get_account(database, 101, 200)
    assert other_group.balance == 0
    async with database.connect() as connection:
        cursor = await connection.execute("SELECT MAX(version) AS version FROM schema_migrations")
        assert (await cursor.fetchone())["version"] == 9


@pytest.mark.asyncio
async def test_atomic_transfer_and_idempotency(tmp_path):
    database = make_database(tmp_path)
    await seed_points(database, 1, 10, 100, "seed-transfer")

    result = await transfer_points(
        database,
        group_id=1,
        sender_user_id=10,
        receiver_user_id=20,
        amount=35,
        request_id="transfer-message-1",
    )

    assert result.sender_balance == 65
    assert result.receiver_balance == 35
    with pytest.raises(EconomyError, match="已经处理"):
        await transfer_points(
            database,
            group_id=1,
            sender_user_id=10,
            receiver_user_id=20,
            amount=35,
            request_id="transfer-message-1",
        )
    with pytest.raises(EconomyError, match="积分不足"):
        await transfer_points(
            database,
            group_id=1,
            sender_user_id=10,
            receiver_user_id=20,
            amount=1000,
            request_id="transfer-message-2",
        )


@pytest.mark.asyncio
async def test_red_packet_claims_sum_to_total(tmp_path):
    database = make_database(tmp_path)
    await seed_points(database, 1, 10, 100, "seed-packet")
    packet = await create_red_packet(
        database,
        group_id=1,
        sender_user_id=10,
        total_amount=30,
        total_count=3,
        request_id="packet-create-1",
        ttl_seconds=3600,
    )

    claims = []
    for index, user_id in enumerate((20, 21, 22), start=1):
        result = await claim_red_packet(
            database,
            group_id=1,
            user_id=user_id,
            request_id=f"packet-claim-{index}",
            packet_token=packet.short_id,
            rng=random.Random(index),
        )
        claims.append(result.amount)
    assert sum(claims) == 30
    assert all(amount > 0 for amount in claims)
    with pytest.raises(EconomyError, match="领完|失效"):
        await claim_red_packet(
            database,
            group_id=1,
            user_id=23,
            request_id="packet-claim-4",
            packet_token=packet.short_id,
        )


@pytest.mark.asyncio
async def test_concurrent_red_packet_claims_do_not_overspend(tmp_path):
    database = make_database(tmp_path)
    await seed_points(database, 1, 10, 100, "seed-concurrent-packet")
    packet = await create_red_packet(
        database,
        group_id=1,
        sender_user_id=10,
        total_amount=25,
        total_count=3,
        request_id="concurrent-create",
        ttl_seconds=3600,
    )

    results = await asyncio.gather(
        *(
            claim_red_packet(
                database,
                group_id=1,
                user_id=user_id,
                request_id=f"concurrent-claim-{user_id}",
                packet_token=packet.short_id,
                rng=random.Random(user_id),
            )
            for user_id in range(20, 25)
        ),
        return_exceptions=True,
    )
    successes = [result for result in results if not isinstance(result, BaseException)]
    failures = [result for result in results if isinstance(result, BaseException)]

    assert len(successes) == 3
    assert sum(result.amount for result in successes) == 25
    assert len(failures) == 2
    assert all(isinstance(error, EconomyError) for error in failures)


@pytest.mark.asyncio
async def test_expired_red_packet_refunds_remaining_points(tmp_path):
    database = make_database(tmp_path)
    await seed_points(database, 1, 10, 50, "seed-expired-packet")
    packet = await create_red_packet(
        database,
        group_id=1,
        sender_user_id=10,
        total_amount=20,
        total_count=2,
        request_id="expired-create",
        ttl_seconds=3600,
    )
    async with database.transaction() as connection:
        await connection.execute(
            "UPDATE red_packets SET expires_at = ? WHERE id = ?",
            (iso_time(datetime.now(timezone.utc) - timedelta(minutes=1)), packet.packet_id),
        )

    with pytest.raises(EconomyError, match="已经过期"):
        await claim_red_packet(
            database,
            group_id=1,
            user_id=20,
            request_id="expired-claim",
            packet_token=packet.short_id,
        )
    account = await get_account(database, 1, 10)
    assert account.balance == 50


class FixedRandom:
    def __init__(self, roll: float, amount: int) -> None:
        self.roll = roll
        self.amount = amount

    def random(self) -> float:
        return self.roll

    def randint(self, start: int, end: int) -> int:
        return min(max(self.amount, start), end)


@pytest.mark.asyncio
async def test_robbery_cooldown_and_nonnegative_balance(tmp_path):
    database = make_database(tmp_path)
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    result = await play_robbery(
        database,
        group_id=1,
        user_id=10,
        request_id="robbery-1",
        cooldown_seconds=600,
        now=now,
        rng=FixedRandom(0.1, 15),  # type: ignore[arg-type]
    )
    assert result.change_amount == 15
    with pytest.raises(EconomyError, match="冷却"):
        await play_robbery(
            database,
            group_id=1,
            user_id=10,
            request_id="robbery-2",
            cooldown_seconds=600,
            now=now + timedelta(minutes=1),
        )

    loss = await play_robbery(
        database,
        group_id=1,
        user_id=10,
        request_id="robbery-3",
        cooldown_seconds=600,
        now=now + timedelta(minutes=11),
        rng=FixedRandom(0.7, 20),  # type: ignore[arg-type]
    )
    assert loss.balance == 0
    assert loss.change_amount == -15


@pytest.mark.asyncio
async def test_shop_redeem_and_refund_restores_stock(tmp_path):
    database = make_database(tmp_path)
    await seed_points(database, 1, 10, 100, "seed-shop")
    product = await create_product(
        database,
        group_id=1,
        name="测试商品",
        description="用于测试",
        price=20,
        stock=3,
        created_by=99,
    )
    order = await redeem_product(
        database,
        group_id=1,
        user_id=10,
        product_id=product.product_id,
        quantity=2,
        request_id="shop-order-1",
    )
    assert order.total_price == 40
    assert order.balance == 60

    refunded = await refund_order(
        database,
        group_id=1,
        order_token=order.short_id,
    )
    assert refunded.balance == 100
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT stock FROM shop_products WHERE id = ?", (product.product_id,)
        )
        assert (await cursor.fetchone())["stock"] == 3


@pytest.mark.parametrize("argument,count", [
    ("-100", 1), ("10.5", 1), ("100 200", 1), ("转100", 1),
    ("-100 5", 2), ("100 -5", 2), ("10.5 2", 2), ("100 5多", 2),
    ("0", 1), (str(2**63), 1), ("9" * 5000, 1),
])
def test_money_arguments_are_not_silently_reinterpreted(argument, count):
    with pytest.raises(EconomyError):
        parse_positive_integers(argument, count)


def test_money_arguments_accept_whitespace_and_leading_zeroes():
    assert parse_positive_integers(" 100 ", 1) == (100,)
    assert parse_positive_integers("0100\t5", 2) == (100, 5)


@pytest.mark.asyncio
async def test_order_prefixes_cannot_modify_an_arbitrary_order(tmp_path, monkeypatch):
    database = make_database(tmp_path)
    await seed_points(database, 1, 10, 100, "order-validation")
    product = await create_product(
        database, group_id=1, name="前缀测试", description="", price=10,
        stock=5, created_by=99,
    )
    ids = iter(("abcdef12" + "0" * 24, "abcdef12" + "1" * 24))
    monkeypatch.setattr("src.services.economy.shop.uuid4", lambda: SimpleNamespace(hex=next(ids)))
    orders = []
    for index in range(2):
        orders.append(await redeem_product(
            database, group_id=1, user_id=10, product_id=product.product_id,
            quantity=1, request_id=f"prefix-order-{index}",
        ))

    for token, error in (("%%%%", "格式"), ("abcd____", "格式"), ("abcdef12", "多个")):
        with pytest.raises(EconomyError, match=error):
            await refund_order(database, group_id=1, order_token=token)
        with pytest.raises(EconomyError, match=error):
            await fulfill_order(database, group_id=1, order_token=token, fulfilled_by=99)
    assert (await get_account(database, 1, 10)).balance == 80
    async with database.connect() as connection:
        cursor = await connection.execute("SELECT status FROM shop_orders")
        assert [row["status"] for row in await cursor.fetchall()] == ["pending", "pending"]
    # A full ID still selects exactly one order, including uppercase input.
    await fulfill_order(
        database, group_id=1, order_token=orders[0].order_id.upper(), fulfilled_by=99
    )
    with pytest.raises(EconomyError, match="没有找到"):
        await refund_order(database, group_id=2, order_token=orders[1].order_id)
    result = await refund_order(database, group_id=1, order_token=orders[1].order_id)
    assert result.balance == 90
    with pytest.raises(EconomyError, match="待核销"):
        await refund_order(database, group_id=1, order_token=orders[1].order_id)


@pytest.mark.asyncio
async def test_red_packet_prefixes_reject_ambiguity(tmp_path, monkeypatch):
    database = make_database(tmp_path)
    await seed_points(database, 1, 10, 100, "packet-validation")
    ids = iter(("abcdef12" + "0" * 24, "abcdef12" + "1" * 24))
    monkeypatch.setattr(
        "src.services.economy.red_packets.uuid4", lambda: SimpleNamespace(hex=next(ids))
    )
    packets = []
    for index in range(2):
        packets.append(await create_red_packet(
            database, group_id=1, sender_user_id=10, total_amount=10, total_count=1,
            request_id=f"prefix-packet-{index}", ttl_seconds=3600,
        ))
    for token, error in (("%%%%", "格式"), ("abcdef12", "多个")):
        with pytest.raises(EconomyError, match=error):
            await claim_red_packet(
                database, group_id=1, user_id=20, packet_token=token, request_id="bad-claim"
            )
    assert (await get_account(database, 1, 20)).balance == 0
    result = await claim_red_packet(
        database, group_id=1, user_id=20, packet_token=packets[0].packet_id,
        request_id="good-claim",
    )
    assert result.balance == 10
