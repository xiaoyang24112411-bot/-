"""Per-group, explicitly curated QQ image library."""

import hashlib
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from src.config import MemeSettings
from src.services.economy import EconomyDatabase, EconomyError
from src.services.media.qq_image import inspect_image

SERIOUS_TOPICS = (
    "自杀",
    "自残",
    "急救",
    "报警",
    "去世",
    "死亡",
    "事故",
    "受伤",
    "医院",
    "住院",
    "生病",
    "发烧",
    "抑郁",
    "崩溃",
    "难过",
    "伤心",
    "分手",
    "失恋",
    "焦虑",
    "痛苦",
    "绝望",
    "欺负",
    "骚扰",
    "哭了",
)
PLAYFUL_CUES = ("哈哈", "嘿嘿", "好玩", "有趣", "可爱", "开心", "摸摸", "贴贴", "哼")


@dataclass(frozen=True)
class SavedMeme:
    id: int
    group_id: int
    path: Path


def _meme_path(root: Path, group_id: int, sha256: str, extension: str) -> Path:
    if group_id <= 0 or len(sha256) != 64 or extension not in {"jpg", "png", "gif", "webp"}:
        raise EconomyError("表情包记录无效。")
    return root / str(group_id) / f"{sha256}.{extension}"


async def save_meme(
    db: EconomyDatabase, settings: MemeSettings, group_id: int, user_id: int, data: bytes
) -> tuple[SavedMeme, bool]:
    extension = inspect_image(data, settings.max_image_bytes)
    digest = hashlib.sha256(data).hexdigest()
    path = _meme_path(settings.root, group_id, digest, extension)
    async with db.transaction() as connection:
        existing = await connection.execute(
            "SELECT id FROM group_memes WHERE group_id = ? AND sha256 = ?",
            (group_id, digest),
        )
        row = await existing.fetchone()
        if row is not None:
            if not path.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            return SavedMeme(int(row[0]), group_id, path), False
        count_cursor = await connection.execute(
            "SELECT COUNT(*) FROM group_memes WHERE group_id = ?", (group_id,)
        )
        count_row = await count_cursor.fetchone()
        if count_row and int(count_row[0]) >= settings.max_per_group:
            raise EconomyError(f"本群最多收藏 {settings.max_per_group} 张表情包，请先删除旧图。")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{digest}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as file:
                file.write(data)
            os.replace(temporary, path)
            cursor = await connection.execute(
                "INSERT INTO group_memes(group_id, sha256, file_extension, added_by, created_at) "
                "VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                (group_id, digest, extension, user_id),
            )
            return SavedMeme(int(cursor.lastrowid), group_id, path), True
        finally:
            temporary.unlink(missing_ok=True)


async def random_meme(
    db: EconomyDatabase, settings: MemeSettings, group_id: int
) -> SavedMeme | None:
    async with db.connect() as connection:
        cursor = await connection.execute(
            "SELECT id, sha256, file_extension FROM group_memes "
            "WHERE group_id = ? ORDER BY RANDOM() LIMIT 1",
            (group_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    path = _meme_path(settings.root, group_id, str(row[1]), str(row[2]))
    return SavedMeme(int(row[0]), group_id, path) if path.is_file() else None


async def meme_count(db: EconomyDatabase, group_id: int) -> int:
    async with db.connect() as connection:
        cursor = await connection.execute(
            "SELECT COUNT(*) FROM group_memes WHERE group_id = ?", (group_id,)
        )
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def delete_meme(
    db: EconomyDatabase, settings: MemeSettings, group_id: int, meme_id: int
) -> bool:
    async with db.transaction() as connection:
        cursor = await connection.execute(
            "SELECT sha256, file_extension FROM group_memes WHERE group_id = ? AND id = ?",
            (group_id, meme_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return False
        await connection.execute(
            "DELETE FROM group_memes WHERE group_id = ? AND id = ?", (group_id, meme_id)
        )
    _meme_path(settings.root, group_id, str(row[0]), str(row[1])).unlink(missing_ok=True)
    return True


async def proactive_meme_enabled(db: EconomyDatabase, group_id: int) -> bool:
    async with db.connect() as connection:
        cursor = await connection.execute(
            "SELECT proactive_enabled FROM meme_group_settings WHERE group_id = ?", (group_id,)
        )
        row = await cursor.fetchone()
    return bool(row[0]) if row else False


async def set_proactive_meme_enabled(
    db: EconomyDatabase, group_id: int, enabled: bool, user_id: int
) -> None:
    async with db.transaction() as connection:
        await connection.execute(
            "INSERT INTO meme_group_settings(group_id, proactive_enabled, updated_by, updated_at) "
            "VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "ON CONFLICT(group_id) DO UPDATE SET proactive_enabled=excluded.proactive_enabled, "
            "updated_by=excluded.updated_by, updated_at=excluded.updated_at",
            (group_id, int(enabled), user_id),
        )


last_proactive_meme_at: dict[int, float] = {}


def meme_fits_chat(recent_texts: tuple[str, ...], reply: str) -> bool:
    """Keep surprise images out of serious or matter-of-fact discussions."""
    context = " ".join(recent_texts[-3:]) + " " + reply
    return not any(word in context for word in SERIOUS_TOPICS) and any(
        word in reply for word in PLAYFUL_CUES
    )


async def select_proactive_meme(
    db: EconomyDatabase,
    settings: MemeSettings,
    group_id: int,
    *,
    now: float | None = None,
    rng: random.Random | None = None,
) -> SavedMeme | None:
    current = time.monotonic() if now is None else now
    if settings.proactive_percent <= 0:
        return None
    if (
        current - last_proactive_meme_at.get(group_id, float("-inf"))
        < settings.proactive_interval_seconds
    ):
        return None
    if not await proactive_meme_enabled(db, group_id):
        return None
    if (rng or random.SystemRandom()).randrange(100) >= settings.proactive_percent:
        return None
    return await random_meme(db, settings, group_id)


def mark_proactive_meme_sent(group_id: int, *, now: float | None = None) -> None:
    last_proactive_meme_at[group_id] = time.monotonic() if now is None else now
