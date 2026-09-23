"""Persistent, account-wide QQ user block list."""

from src.services.economy.database import EconomyDatabase


async def is_blocked(database: EconomyDatabase, user_id: int) -> bool:
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT 1 FROM bot_global_blacklist WHERE user_id = ?", (user_id,)
        )
        return await cursor.fetchone() is not None


async def block_user(database: EconomyDatabase, user_id: int, blocked_by: int) -> bool:
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "INSERT OR IGNORE INTO bot_global_blacklist(user_id, blocked_by, blocked_at) "
            "VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
            (user_id, blocked_by),
        )
        return cursor.rowcount == 1


async def unblock_user(database: EconomyDatabase, user_id: int) -> bool:
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "DELETE FROM bot_global_blacklist WHERE user_id = ?", (user_id,)
        )
        return cursor.rowcount == 1


async def list_blocked(
    database: EconomyDatabase, page: int, page_size: int = 20
) -> tuple[int, list[int]]:
    async with database.connect() as connection:
        cursor = await connection.execute("SELECT COUNT(*) FROM bot_global_blacklist")
        total = (await cursor.fetchone())[0]
        cursor = await connection.execute(
            "SELECT user_id FROM bot_global_blacklist ORDER BY blocked_at DESC, user_id DESC "
            "LIMIT ? OFFSET ?",
            (page_size, (page - 1) * page_size),
        )
        return total, [row[0] for row in await cursor.fetchall()]
