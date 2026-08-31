import random
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from src.services.economy.common import apply_change, iso_time
from src.services.economy.database import EconomyDatabase
from src.services.economy.errors import EconomyError
from src.services.games.cultivation import (
    breakthrough,
    cultivate,
    get_cultivation_profile,
)
from src.services.games.dice import roll_dice
from src.services.games.gomoku import (
    create_gomoku_game,
    join_gomoku_game,
    parse_coordinate,
    place_gomoku_stone,
)
from src.services.games.life_simulator import simulate_life
from src.services.games.roulette import play_roulette
from src.services.games.yugioh import API_URL, search_yugioh_card


async def seed_points(database, amount: int) -> None:
    async with database.transaction() as connection:
        await apply_change(
            connection,
            group_id=1,
            user_id=10,
            amount=amount,
            event_type="test_seed_batch3",
            reference_id="seed-batch3",
            note="test",
            now=iso_time(),
        )


def test_dice_and_life_simulator_are_bounded():
    dice = roll_dice("3d8", random.Random(1))
    assert dice.count == 3
    assert dice.faces == 8
    assert len(dice.rolls) == 3
    assert all(1 <= value <= 8 for value in dice.rolls)
    with pytest.raises(EconomyError, match="数量"):
        roll_dice("21d6")

    life = simulate_life(random.Random(1))
    assert len(life.talents) == 3
    assert len(life.events) == 9
    assert life.score > 0


@pytest.mark.asyncio
async def test_roulette_settles_points_and_enforces_cooldown(tmp_path):
    database = EconomyDatabase(tmp_path / "roulette.sqlite3")
    await seed_points(database, 100)
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    safe = await play_roulette(
        database,
        group_id=1,
        user_id=10,
        wager=10,
        request_id="roulette-safe",
        cooldown_seconds=60,
        max_wager=100,
        now=now,
        rng=random.Random(5),
    )
    assert safe.result_code == "safe"
    assert safe.change_amount == 2
    assert safe.balance == 102
    with pytest.raises(EconomyError, match="冷却"):
        await play_roulette(
            database,
            group_id=1,
            user_id=10,
            wager=10,
            request_id="roulette-too-soon",
            cooldown_seconds=60,
            max_wager=100,
            now=now + timedelta(seconds=10),
        )

    class HitRandom:
        def randint(self, start: int, end: int) -> int:
            return 1

    hit = await play_roulette(
        database,
        group_id=1,
        user_id=10,
        wager=10,
        request_id="roulette-hit",
        cooldown_seconds=60,
        max_wager=100,
        now=now + timedelta(seconds=61),
        rng=HitRandom(),  # type: ignore[arg-type]
    )
    assert hit.result_code == "hit"
    assert hit.change_amount == -10
    assert hit.balance == 92


@pytest.mark.asyncio
async def test_cultivation_cooldown_and_breakthrough(tmp_path):
    database = EconomyDatabase(tmp_path / "cultivation.sqlite3")
    profile = await get_cultivation_profile(database, 1, 10)
    assert profile.realm_name == "炼气"
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    result = await cultivate(
        database,
        group_id=1,
        user_id=10,
        request_id="cultivate-1",
        cooldown_seconds=60,
        now=now,
        rng=random.Random(1),
    )
    assert 15 <= result.cultivation_gain <= 35
    with pytest.raises(EconomyError, match="灵气尚未恢复"):
        await cultivate(
            database,
            group_id=1,
            user_id=10,
            request_id="cultivate-2",
            cooldown_seconds=60,
            now=now + timedelta(seconds=10),
        )

    async with database.transaction() as connection:
        await connection.execute(
            "UPDATE cultivation_profiles SET cultivation = 100 WHERE group_id = 1 AND user_id = 10"
        )
    upgraded = await breakthrough(
        database,
        group_id=1,
        user_id=10,
        request_id="breakthrough-1",
    )
    assert upgraded.realm_name == "筑基"


@pytest.mark.asyncio
async def test_gomoku_horizontal_win(tmp_path):
    database = EconomyDatabase(tmp_path / "gomoku.sqlite3")
    await create_gomoku_game(database, 1, 10)
    game = await join_gomoku_game(database, 1, 20)
    assert game.current_user_id == 10
    assert parse_coordinate("H8") == (7, 7)

    moves = [
        (10, 0, 0),
        (20, 0, 1),
        (10, 1, 0),
        (20, 1, 1),
        (10, 2, 0),
        (20, 2, 1),
        (10, 3, 0),
        (20, 3, 1),
        (10, 4, 0),
    ]
    result = None
    for user_id, column, row in moves:
        result = await place_gomoku_stone(
            database,
            group_id=1,
            user_id=user_id,
            column=column,
            row=row,
        )
    assert result is not None
    assert result.game.status == "black_won"
    assert result.game.winner_user_id == 10


@pytest.mark.asyncio
async def test_yugioh_lookup_uses_alias_and_cache(tmp_path):
    database = EconomyDatabase(tmp_path / "yugioh.sqlite3")
    payload = {
        "data": [
            {
                "id": 89631139,
                "name": "Blue-Eyes White Dragon",
                "type": "Normal Monster",
                "desc": "A legendary dragon.",
                "race": "Dragon",
                "attribute": "LIGHT",
                "level": 8,
                "atk": 3000,
                "def": 2500,
                "archetype": "Blue-Eyes",
            }
        ]
    }
    with respx.mock(assert_all_called=True) as router:
        route = router.get(API_URL).mock(return_value=httpx.Response(200, json=payload))
        async with httpx.AsyncClient() as client:
            first = await search_yugioh_card(database, "青眼白龙", client=client)
            second = await search_yugioh_card(database, "青眼白龙", client=client)
    assert first.name == "Blue-Eyes White Dragon"
    assert second.card_id == 89631139
    assert route.call_count == 1
