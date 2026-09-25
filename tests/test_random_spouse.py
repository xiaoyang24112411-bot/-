import asyncio
import random
from datetime import datetime, timedelta, timezone

import pytest

from src.services.economy.database import EconomyDatabase
from src.services.economy.errors import EconomyError
from src.services.entertainment.random_spouse import (
    SpouseCandidate,
    draw_daily_spouse,
    force_daily_spouse,
    get_daily_spouse,
    set_spouse_pool_participation,
    unlink_daily_spouse,
)

BEIJING = timezone(timedelta(hours=8))


@pytest.mark.asyncio
async def test_random_spouse_is_fixed_for_the_day_and_refreshes_next_day(tmp_path):
    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    candidates = [
        SpouseCandidate(10, "甲"),
        SpouseCandidate(20, "乙"),
        SpouseCandidate(30, "丙"),
    ]
    today = datetime(2026, 8, 30, 9, 0, tzinfo=BEIJING)

    first = await draw_daily_spouse(
        database,
        group_id=1,
        user_id=100,
        candidates=candidates,
        now=today,
        rng=random.Random(1),
    )
    repeated = await draw_daily_spouse(
        database,
        group_id=1,
        user_id=100,
        candidates=candidates,
        now=today,
        rng=random.Random(999),
    )
    tomorrow = await draw_daily_spouse(
        database,
        group_id=1,
        user_id=100,
        candidates=candidates,
        now=today + timedelta(days=1),
        rng=random.Random(5),
    )

    assert first.is_new is True
    assert repeated.is_new is False
    assert repeated.spouse_user_id == first.spouse_user_id
    assert repeated.draw_date == first.draw_date
    assert tomorrow.is_new is True
    assert tomorrow.draw_date != first.draw_date


@pytest.mark.asyncio
async def test_random_spouse_draw_is_scoped_by_group_and_user(tmp_path):
    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    candidates = [SpouseCandidate(10), SpouseCandidate(20)]
    now = datetime(2026, 8, 30, 9, 0, tzinfo=BEIJING)

    await draw_daily_spouse(
        database,
        group_id=1,
        user_id=100,
        candidates=candidates,
        now=now,
        rng=random.Random(1),
    )
    await draw_daily_spouse(
        database,
        group_id=2,
        user_id=100,
        candidates=candidates,
        now=now,
        rng=random.Random(2),
    )

    async with database.connect() as connection:
        cursor = await connection.execute("SELECT COUNT(*) AS count FROM daily_spouses")
        assert (await cursor.fetchone())["count"] == 2


@pytest.mark.asyncio
async def test_force_spouse_requires_unlink_and_is_limited_once_per_day(tmp_path):
    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    candidates = [SpouseCandidate(10, "甲"), SpouseCandidate(20, "乙")]
    now = datetime(2026, 8, 30, 9, 0, tzinfo=BEIJING)
    await draw_daily_spouse(
        database,
        group_id=1,
        user_id=100,
        candidates=candidates[:1],
        now=now,
        rng=random.Random(1),
    )

    with pytest.raises(EconomyError, match="先由任意一方发送"):
        await force_daily_spouse(
            database, group_id=1, user_id=100, target=candidates[1], now=now
        )
    released = await unlink_daily_spouse(database, group_id=1, user_id=10, now=now)
    assert released.partner_user_id == 100
    assert released.was_mutual_binding

    forced = await force_daily_spouse(
        database,
        group_id=1,
        user_id=100,
        target=candidates[1],
        now=now,
    )
    repeated_draw = await draw_daily_spouse(
        database,
        group_id=1,
        user_id=100,
        candidates=candidates,
        now=now,
        rng=random.Random(999),
    )

    assert forced.spouse_user_id == 20
    assert repeated_draw.spouse_user_id == 20
    await unlink_daily_spouse(database, group_id=1, user_id=20, now=now)
    with pytest.raises(EconomyError, match="已经强娶"):
        await force_daily_spouse(
            database,
            group_id=1,
            user_id=100,
            target=candidates[0],
            now=now,
        )


@pytest.mark.asyncio
async def test_binding_is_mutual_exclusive_and_both_sides_can_unlink(tmp_path):
    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    now = datetime(2026, 8, 30, 9, 0, tzinfo=BEIJING)
    members = [SpouseCandidate(100, "甲"), SpouseCandidate(200, "乙"),
               SpouseCandidate(300, "丙")]
    first = await draw_daily_spouse(
        database, group_id=1, user_id=100, candidates=members, now=now,
        rng=random.Random(0),
    )
    assert first.spouse_user_id in {200, 300}
    partner = first.spouse_user_id
    other = ({200, 300} - {partner}).pop()
    reverse = await draw_daily_spouse(
        database, group_id=1, user_id=partner, candidates=members, now=now,
    )
    assert reverse.spouse_user_id == 100
    assert not reverse.is_new
    with pytest.raises(EconomyError, match="没有可配对"):
        await draw_daily_spouse(
            database, group_id=1, user_id=other, candidates=members, now=now,
        )
    with pytest.raises(EconomyError, match="已有绑定"):
        await force_daily_spouse(
            database, group_id=1, user_id=other, target=SpouseCandidate(partner), now=now,
        )

    released = await unlink_daily_spouse(database, group_id=1, user_id=partner, now=now)
    assert released.partner_user_id == 100
    assert await get_daily_spouse(database, group_id=1, user_id=100, now=now) is None
    assert await get_daily_spouse(database, group_id=1, user_id=partner, now=now) is None
    with pytest.raises(EconomyError, match="已解绑"):
        await draw_daily_spouse(
            database, group_id=1, user_id=100, candidates=members, now=now,
        )
    second = await draw_daily_spouse(
        database, group_id=1, user_id=partner, candidates=members, now=now,
    )
    assert second.spouse_user_id == other


@pytest.mark.asyncio
async def test_opt_out_is_group_scoped_and_releases_pair(tmp_path):
    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    now = datetime(2026, 8, 30, 9, 0, tzinfo=BEIJING)
    members = [SpouseCandidate(100), SpouseCandidate(200), SpouseCandidate(300)]
    await draw_daily_spouse(
        database, group_id=1, user_id=100, candidates=members[:2], now=now,
    )
    changed, released = await set_spouse_pool_participation(
        database, group_id=1, user_id=200, participating=False, now=now,
    )
    assert changed and released and released.partner_user_id == 100
    assert await get_daily_spouse(database, group_id=1, user_id=100, now=now) is None
    with pytest.raises(EconomyError, match="退出"):
        await force_daily_spouse(
            database, group_id=1, user_id=300, target=SpouseCandidate(200), now=now,
        )
    with pytest.raises(EconomyError, match="退出"):
        await draw_daily_spouse(
            database, group_id=1, user_id=200, candidates=members, now=now,
        )
    # An opt-out in group 1 does not affect another group.
    assert (await draw_daily_spouse(
        database, group_id=2, user_id=300, candidates=members[:2], now=now,
    )).spouse_user_id in {100, 200}
    changed, _ = await set_spouse_pool_participation(
        database, group_id=1, user_id=200, participating=True, now=now,
    )
    assert changed
    assert await get_daily_spouse(database, group_id=1, user_id=200, now=now) is None


@pytest.mark.asyncio
async def test_old_draw_is_adopted_or_can_be_unlinked_before_force(tmp_path):
    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    now = datetime(2026, 8, 30, 9, 0, tzinfo=BEIJING)
    await database.initialize()
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO daily_spouses"
            "(group_id, user_id, draw_date, spouse_user_id, created_at) "
            "VALUES (1, 100, '2026-08-30', 200, '2026-08-30T00:00:00Z')"
        )
    adopted = await draw_daily_spouse(
        database, group_id=1, user_id=100,
        candidates=[SpouseCandidate(100), SpouseCandidate(200)], now=now,
    )
    assert adopted.spouse_user_id == 200
    assert not adopted.is_new
    assert (await get_daily_spouse(
        EconomyDatabase(database.path), group_id=1, user_id=200, now=now,
    )).spouse_user_id == 100
    await unlink_daily_spouse(database, group_id=1, user_id=100, now=now)
    assert (await force_daily_spouse(
        database, group_id=1, user_id=100, target=SpouseCandidate(200), now=now,
    )).spouse_user_id == 200


@pytest.mark.asyncio
async def test_blacklisted_members_are_not_random_or_force_targets(tmp_path):
    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    now = datetime(2026, 8, 30, 9, 0, tzinfo=BEIJING)
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO bot_global_blacklist(user_id, blocked_by, blocked_at) "
            "VALUES (200, 2448821316, '2026-08-30T00:00:00Z')"
        )
    result = await draw_daily_spouse(
        database, group_id=1, user_id=100,
        candidates=[SpouseCandidate(200), SpouseCandidate(300)], now=now,
    )
    assert result.spouse_user_id == 300
    with pytest.raises(EconomyError, match="不可参与"):
        await force_daily_spouse(
            database, group_id=2, user_id=100, target=SpouseCandidate(200), now=now,
        )


@pytest.mark.asyncio
async def test_concurrent_draws_cannot_bind_the_same_person(tmp_path):
    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    now = datetime(2026, 8, 30, 9, 0, tzinfo=BEIJING)

    async def draw(user_id):
        return await draw_daily_spouse(
            database, group_id=1, user_id=user_id,
            candidates=[SpouseCandidate(300)], now=now,
        )

    results = await asyncio.gather(draw(100), draw(200), return_exceptions=True)
    assert sum(isinstance(result, EconomyError) for result in results) == 1
    assert sum(getattr(result, "spouse_user_id", None) == 300 for result in results) == 1
    async with database.connect() as connection:
        cursor = await connection.execute("SELECT COUNT(*) FROM daily_spouse_bindings")
        assert (await cursor.fetchone())[0] == 2


@pytest.mark.asyncio
async def test_old_duplicate_draws_get_distinct_new_bindings(tmp_path):
    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    now = datetime(2026, 8, 30, 9, 0, tzinfo=BEIJING)
    async with database.transaction() as connection:
        await connection.executemany(
            "INSERT INTO daily_spouses"
            "(group_id, user_id, draw_date, spouse_user_id, created_at) "
            "VALUES (1, ?, '2026-08-30', 200, '2026-08-30T00:00:00Z')",
            ((100,), (300,)),
        )
    candidates = [SpouseCandidate(100), SpouseCandidate(200),
                  SpouseCandidate(300), SpouseCandidate(400)]
    first = await draw_daily_spouse(
        database, group_id=1, user_id=100, candidates=candidates, now=now,
    )
    second = await draw_daily_spouse(
        database, group_id=1, user_id=300, candidates=candidates, now=now,
    )
    assert first.spouse_user_id == 200
    assert second.spouse_user_id == 400


@pytest.mark.asyncio
async def test_unadopted_old_draw_can_be_unlinked_then_forced(tmp_path):
    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    now = datetime(2026, 8, 30, 9, 0, tzinfo=BEIJING)
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO daily_spouses"
            "(group_id, user_id, draw_date, spouse_user_id, created_at) "
            "VALUES (1, 100, '2026-08-30', 200, '2026-08-30T00:00:00Z')"
        )
    result = await unlink_daily_spouse(database, group_id=1, user_id=100, now=now)
    assert result.partner_user_id == 200
    assert not result.was_mutual_binding
    assert (await force_daily_spouse(
        database, group_id=1, user_id=100, target=SpouseCandidate(200), now=now,
    )).spouse_user_id == 200


@pytest.mark.asyncio
async def test_force_spouse_rejects_self(tmp_path):
    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    with pytest.raises(EconomyError, match="不能强娶自己"):
        await force_daily_spouse(
            database,
            group_id=1,
            user_id=100,
            target=SpouseCandidate(100),
        )
