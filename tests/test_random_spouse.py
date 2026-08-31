import random
from datetime import datetime, timedelta, timezone

import pytest

from src.services.economy.database import EconomyDatabase
from src.services.economy.errors import EconomyError
from src.services.entertainment.random_spouse import (
    SpouseCandidate,
    draw_daily_spouse,
    force_daily_spouse,
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
async def test_force_spouse_replaces_draw_once_and_persists(tmp_path):
    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    candidates = [SpouseCandidate(10, "甲"), SpouseCandidate(20, "乙")]
    now = datetime(2026, 8, 30, 9, 0, tzinfo=BEIJING)
    await draw_daily_spouse(
        database,
        group_id=1,
        user_id=100,
        candidates=candidates,
        now=now,
        rng=random.Random(1),
    )

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
    with pytest.raises(EconomyError, match="已经强娶"):
        await force_daily_spouse(
            database,
            group_id=1,
            user_id=100,
            target=candidates[0],
            now=now,
        )


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
