"""Opt-in group message storage and Chinese word-cloud rendering."""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import jieba
from wordcloud import WordCloud

from src.services.economy.common import iso_time
from src.services.economy.database import EconomyDatabase

from .errors import AIFeatureError

STOPWORDS = {
    "这个",
    "那个",
    "什么",
    "怎么",
    "就是",
    "不是",
    "可以",
    "没有",
    "一个",
    "我们",
    "你们",
    "他们",
    "自己",
    "感觉",
    "还是",
    "然后",
    "因为",
    "所以",
    "真的",
    "哈哈",
    "哈哈哈",
}
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


@dataclass(frozen=True)
class WordCloudSetting:
    enabled: bool
    retention_days: int


async def get_wordcloud_setting(
    database: EconomyDatabase,
    group_id: int,
    default_retention_days: int = 30,
) -> WordCloudSetting:
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT enabled, retention_days FROM wordcloud_group_settings WHERE group_id = ?",
            (group_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return WordCloudSetting(False, default_retention_days)
    return WordCloudSetting(bool(row["enabled"]), int(row["retention_days"]))


async def set_wordcloud_enabled(
    database: EconomyDatabase,
    group_id: int,
    enabled: bool,
    updated_by: int,
    retention_days: int,
) -> WordCloudSetting:
    days = min(90, max(1, retention_days))
    now = iso_time()
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO wordcloud_group_settings"
            "(group_id, enabled, retention_days, updated_by, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(group_id) DO UPDATE SET enabled = excluded.enabled, "
            "retention_days = excluded.retention_days, updated_by = excluded.updated_by, "
            "updated_at = excluded.updated_at",
            (group_id, int(enabled), days, updated_by, now),
        )
    return WordCloudSetting(enabled, days)


def normalize_message(text: str) -> str:
    value = URL_PATTERN.sub(" ", text).strip()
    value = re.sub(r"\s+", " ", value)
    return value[:500]


async def record_wordcloud_message(
    database: EconomyDatabase,
    group_id: int,
    user_id: int,
    text: str,
    *,
    now: datetime | None = None,
) -> bool:
    message = normalize_message(text)
    if len(message) < 2:
        return False
    current = (now or datetime.now(UTC)).astimezone(UTC)
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT enabled, retention_days FROM wordcloud_group_settings WHERE group_id = ?",
            (group_id,),
        )
        setting = await cursor.fetchone()
        if setting is None or not bool(setting["enabled"]):
            return False
        cutoff = current - timedelta(days=int(setting["retention_days"]))
        await connection.execute(
            "INSERT INTO wordcloud_messages(group_id, user_id, message_text, created_at) "
            "VALUES (?, ?, ?, ?)",
            (group_id, user_id, message, iso_time(current)),
        )
        await connection.execute(
            "DELETE FROM wordcloud_messages WHERE group_id = ? AND created_at < ?",
            (group_id, iso_time(cutoff)),
        )
    return True


async def clear_wordcloud_messages(database: EconomyDatabase, group_id: int) -> int:
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "DELETE FROM wordcloud_messages WHERE group_id = ?", (group_id,)
        )
    return max(0, cursor.rowcount)


async def get_wordcloud_messages(
    database: EconomyDatabase,
    group_id: int,
    days: int,
    *,
    now: datetime | None = None,
) -> tuple[str, ...]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    cutoff = iso_time(current - timedelta(days=min(90, max(1, days))))
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT message_text FROM wordcloud_messages "
            "WHERE group_id = ? AND created_at >= ? ORDER BY created_at DESC LIMIT 5000",
            (group_id, cutoff),
        )
        rows = await cursor.fetchall()
    return tuple(str(row["message_text"]) for row in rows)


def resolve_wordcloud_font(configured: Path | None = None) -> Path:
    candidates = (
        configured,
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
    )
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise AIFeatureError("未找到中文字体，请配置 WORDCLOUD_FONT_PATH。")


def generate_wordcloud(messages: tuple[str, ...], font_path: Path) -> bytes:
    frequencies: Counter[str] = Counter()
    for message in messages:
        for word in jieba.lcut(message):
            token = word.strip().lower()
            if (
                len(token) < 2
                or token in STOPWORDS
                or token.isdigit()
                or not any(
                    character.isalnum() or "\u4e00" <= character <= "\u9fff" for character in token
                )
            ):
                continue
            frequencies[token] += 1
    if len(frequencies) < 3:
        raise AIFeatureError("有效聊天词语太少，请先积累更多群聊消息。")
    cloud = WordCloud(
        font_path=str(font_path),
        width=1000,
        height=700,
        background_color="white",
        max_words=180,
        colormap="viridis",
        random_state=42,
    ).generate_from_frequencies(frequencies)
    output = BytesIO()
    cloud.to_image().save(output, format="PNG")
    return output.getvalue()
