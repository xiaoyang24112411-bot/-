import random
from datetime import datetime, timedelta, timezone

import pytest

from src.services.economy.database import EconomyDatabase
from src.services.entertainment.answer_book import ANSWERS, open_answer_book
from src.services.entertainment.daily_fortune import draw_daily_fortune
from src.services.entertainment.licking_dog_diary import DIARIES, random_diary
from src.services.entertainment.tarot import CARDS, draw_tarot

BEIJING = timezone(timedelta(hours=8))


@pytest.mark.asyncio
async def test_daily_fortune_is_fixed_and_refreshes_next_day(tmp_path):
    database = EconomyDatabase(tmp_path / "fortune.sqlite3")
    today = datetime(2026, 8, 30, 10, 0, tzinfo=BEIJING)
    first = await draw_daily_fortune(
        database,
        group_id=1,
        user_id=2,
        now=today,
        rng=random.Random(1),
    )
    repeated = await draw_daily_fortune(
        database,
        group_id=1,
        user_id=2,
        now=today,
        rng=random.Random(999),
    )
    tomorrow = await draw_daily_fortune(
        database,
        group_id=1,
        user_id=2,
        now=today + timedelta(days=1),
        rng=random.Random(5),
    )

    assert first.is_new is True
    assert repeated.is_new is False
    assert repeated == first.__class__(**{**first.__dict__, "is_new": False})
    assert tomorrow.fortune_date != first.fortune_date
    assert 1 <= first.score <= 100


def test_tarot_uses_builtin_major_arcana():
    result = draw_tarot(random.Random(1))
    assert result.card_name in {card.name for card in CARDS}
    assert result.orientation in {"正位", "逆位"}
    assert result.interpretation


def test_answer_book_and_diary_use_builtin_content():
    assert open_answer_book(random.Random(1)) in ANSWERS
    assert random_diary(random.Random(1)) in DIARIES
