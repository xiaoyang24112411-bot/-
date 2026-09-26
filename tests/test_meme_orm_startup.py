"""Exercise real plugin migrations in isolated processes and temporary databases."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from src.compat.meme_orm import backup_sqlite

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROBE = """
import asyncio
from pathlib import Path
import nonebot
from nonebot.adapters.onebot.v11 import Adapter
from src.compat.meme_startup import configure_meme_environment
from src.compat.meme_orm import initialize_meme_orm, install_meme_orm_startup
configure_meme_environment(Path.cwd())
nonebot.init(driver='~fastapi+~httpx', log_level='ERROR', memes_check_resources_on_startup=False)
driver = nonebot.get_driver()
driver.register_adapter(Adapter)
assert nonebot.load_plugin('nonebot_plugin_memes') is not None
install_meme_orm_startup(driver)
install_meme_orm_startup(driver)
assert driver._lifespan._startup_funcs.count(initialize_meme_orm) == 1
asyncio.run(initialize_meme_orm())
print('ORM_STARTUP_OK')
"""


def run_probe(root: Path) -> subprocess.CompletedProcess:
    environment = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith(("MEME", "LOCALSTORE_", "SQLALCHEMY_", "ALEMBIC_"))
    }
    environment.update(PYTHONPATH=str(PROJECT_ROOT), PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, "-c", PROBE], cwd=root, env=environment,
        capture_output=True, text=True, encoding="utf-8", timeout=45,
    )


def test_real_startup_preserves_records_and_refuses_unversioned_schema_drift(tmp_path: Path):
    result = run_probe(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    database = tmp_path / "data/meme-generator/localstore/data/nonebot_plugin_orm/db.sqlite3"
    table = "nonebot_plugin_memes_memegenerationrecord_v2"
    with sqlite3.connect(database) as connection:
        connection.execute(
            f"INSERT INTO {table} (id, session_persist_id, time, meme_key) VALUES (1, 1, ?, ?)",
            ("2026-09-26 00:00:00", "petpet"),
        )
    result = run_probe(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute(f"SELECT meme_key FROM {table}").fetchone() == ("petpet",)
        # Previous releases used schema sync without stamping migration heads.
        connection.execute("DELETE FROM alembic_version")
    result = run_probe(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert list((database.parent / "backups").glob("*.sqlite3"))
    with sqlite3.connect(database) as connection:
        assert connection.execute(f"SELECT meme_key FROM {table}").fetchone() == ("petpet",)
        connection.execute("DELETE FROM alembic_version")
        connection.execute(f"ALTER TABLE {table} ADD COLUMN custom_keep TEXT")
    result = run_probe(tmp_path)
    assert result.returncode != 0
    with sqlite3.connect(database) as connection:
        assert connection.execute(f"SELECT meme_key, custom_keep FROM {table}").fetchone() == (
            "petpet", None,
        )


def test_sqlite_backup_includes_committed_wal_records(tmp_path: Path):
    database = tmp_path / "sample.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE sample (value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('keep')")
        connection.commit()
        backup = backup_sqlite(database)
        with sqlite3.connect(backup) as copied:
            assert copied.execute("SELECT value FROM sample").fetchone() == ("keep",)
