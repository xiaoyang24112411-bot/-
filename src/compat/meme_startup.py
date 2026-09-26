"""Meme defaults with the same process > dotenv > defaults precedence as NoneBot."""

import json
import os
from pathlib import Path

from dotenv import dotenv_values

from src.config import PERMANENT_ADMIN_IDS


def configure_meme_environment(project_root: Path | None = None) -> None:
    root = (project_root or Path.cwd()).resolve()
    process = {key.upper(): value for key, value in os.environ.items()}
    base = {key.upper(): value for key, value in dotenv_values(root / ".env").items()}
    environment = process.get("ENVIRONMENT") or base.get("ENVIRONMENT") or "prod"
    env_file = root / f".env.{environment}"
    file_values = {key.upper(): value for key, value in dotenv_values(env_file).items()}
    values = {**base, **file_values, **process}

    def effective(key: str, default: str) -> str:
        value = values.get(key)
        return default if value is None else value

    meme_root = Path(effective("MEME_HOME", "data/meme-generator")).expanduser()
    if not meme_root.is_absolute():
        meme_root = root / meme_root
    localstore_root = meme_root / "localstore"
    defaults = {
        "MEMES_COMMAND_PREFIXES": '["#"]',
        "MEMES_USE_SENDER_WHEN_NO_IMAGE": "true",
        "MEMES_PARAMS_MISMATCH_POLICY": '{"too_few_text":"prompt","too_few_image":"prompt"}',
        "LOCALSTORE_CONFIG_DIR": str(localstore_root / "config"),
        "LOCALSTORE_DATA_DIR": str(localstore_root / "data"),
        "LOCALSTORE_CACHE_DIR": str(localstore_root / "cache"),
        "ALEMBIC_STARTUP_CHECK": "true",
    }
    # The Rust generator reads OS variables directly. Publish the resolved value
    # from dotenv too; setdefault alone would hide file settings behind defaults.
    os.environ["MEME_HOME"] = str(meme_root.resolve())
    for name, default in defaults.items():
        os.environ[name] = effective(name, default)

    try:
        configured_admins = json.loads(effective("SUPERUSERS", "[]"))
        if not isinstance(configured_admins, list) or any(
            not isinstance(item, (str, int)) or isinstance(item, bool)
            for item in configured_admins
        ):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ValueError('SUPERUSERS 必须是 JSON 数组，例如 ["2448821316"]') from exc
    admins = {str(item) for item in configured_admins} | {
        str(item) for item in PERMANENT_ADMIN_IDS
    }
    os.environ["SUPERUSERS"] = json.dumps(sorted(admins))
