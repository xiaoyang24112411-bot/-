"""Persisted daily fortune generation."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.services.economy.common import iso_time
from src.services.economy.database import EconomyDatabase

BEIJING = timezone(timedelta(hours=8), "Asia/Shanghai")

FORTUNES = (
    ("大吉", 90, 100, ("好运正在靠近，适合主动争取。", "今天容易遇到令人开心的惊喜。")),
    ("吉", 75, 89, ("稳步推进就会有不错的收获。", "保持耐心，好消息会慢慢出现。")),
    ("小吉", 60, 74, ("平凡的一天里藏着小确幸。", "适合完成手边的小目标。")),
    ("平", 45, 59, ("按部就班最稳妥，不必过度焦虑。", "平常心会让今天更加顺利。")),
    ("小凶", 25, 44, ("重要决定可以多检查一次。", "少些冲动，能避开大部分麻烦。")),
    ("凶", 1, 24, ("今天宜低调休息，避免意气用事。", "放慢脚步，明天会有新的转机。")),
)
COLORS = ("晴空蓝", "樱花粉", "薄荷绿", "暖阳橙", "葡萄紫", "月光白", "曜石黑")
DIRECTIONS = ("东", "南", "西", "北", "东南", "西南", "东北", "西北")
ITEMS = ("耳机", "水杯", "钥匙扣", "纸巾", "充电线", "硬币", "笔记本", "糖果")


@dataclass(frozen=True)
class DailyFortuneResult:
    fortune_level: str
    score: int
    summary: str
    lucky_color: str
    lucky_number: int
    lucky_direction: str
    lucky_item: str
    fortune_date: str
    is_new: bool


def _from_row(row, *, is_new: bool) -> DailyFortuneResult:
    return DailyFortuneResult(
        fortune_level=str(row["fortune_level"]),
        score=int(row["score"]),
        summary=str(row["summary"]),
        lucky_color=str(row["lucky_color"]),
        lucky_number=int(row["lucky_number"]),
        lucky_direction=str(row["lucky_direction"]),
        lucky_item=str(row["lucky_item"]),
        fortune_date=str(row["fortune_date"]),
        is_new=is_new,
    )


async def draw_daily_fortune(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> DailyFortuneResult:
    current = now or datetime.now(BEIJING)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BEIJING)
    current = current.astimezone(BEIJING)
    date_text = current.date().isoformat()
    timestamp = iso_time(current)

    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT * FROM daily_fortunes WHERE group_id = ? AND user_id = ? AND fortune_date = ?",
            (group_id, user_id, date_text),
        )
        row = await cursor.fetchone()
        if row is not None:
            return _from_row(row, is_new=False)

        generator = rng or random.SystemRandom()
        level, score_min, score_max, summaries = generator.choice(FORTUNES)
        values = (
            group_id,
            user_id,
            date_text,
            level,
            generator.randint(score_min, score_max),
            generator.choice(summaries),
            generator.choice(COLORS),
            generator.randint(0, 99),
            generator.choice(DIRECTIONS),
            generator.choice(ITEMS),
            timestamp,
        )
        await connection.execute(
            "INSERT INTO daily_fortunes"
            "(group_id, user_id, fortune_date, fortune_level, score, summary, "
            "lucky_color, lucky_number, lucky_direction, lucky_item, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
        cursor = await connection.execute(
            "SELECT * FROM daily_fortunes WHERE group_id = ? AND user_id = ? AND fortune_date = ?",
            (group_id, user_id, date_text),
        )
        row = await cursor.fetchone()

    return _from_row(row, is_new=True)
