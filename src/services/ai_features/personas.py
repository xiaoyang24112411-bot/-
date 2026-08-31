"""Persistent per-user, per-group AI personas."""

from src.services.economy.common import iso_time
from src.services.economy.database import EconomyDatabase

from .errors import AIFeatureError

MAX_PERSONA_LENGTH = 300


async def get_persona(database: EconomyDatabase, group_id: int, user_id: int) -> str | None:
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT persona FROM ai_personas WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        )
        row = await cursor.fetchone()
    return str(row["persona"]) if row else None


async def set_persona(
    database: EconomyDatabase,
    group_id: int,
    user_id: int,
    persona: str,
) -> str:
    value = persona.strip()
    if len(value) < 2:
        raise AIFeatureError("人格描述至少需要 2 个字符。")
    if len(value) > MAX_PERSONA_LENGTH:
        raise AIFeatureError(f"人格描述不能超过 {MAX_PERSONA_LENGTH} 个字符。")
    now = iso_time()
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO ai_personas(group_id, user_id, persona, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(group_id, user_id) DO UPDATE SET "
            "persona = excluded.persona, updated_at = excluded.updated_at",
            (group_id, user_id, value, now, now),
        )
    return value


async def clear_persona(database: EconomyDatabase, group_id: int, user_id: int) -> bool:
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "DELETE FROM ai_personas WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        )
    return cursor.rowcount > 0
