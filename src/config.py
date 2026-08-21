"""Small application-specific settings layered on top of NoneBot settings."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env.prod"


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_value(name: str, default: str = "") -> str:
    """Read process environment first, then the project's local prod env file."""
    process_value = os.getenv(name)
    if process_value is not None:
        return process_value

    file_value = dotenv_values(ENV_FILE).get(name)
    return str(file_value) if file_value is not None else default


@dataclass(frozen=True)
class AppSettings:
    enable_sensitive_recall: bool
    sensitive_words: tuple[str, ...]


@dataclass(frozen=True)
class DeepSeekSettings:
    api_key: str
    model: str
    base_url: str
    timeout_seconds: float
    max_output_tokens: int


def get_app_settings() -> AppSettings:
    words = tuple(
        word.strip() for word in _get_value("SENSITIVE_WORDS", "广告").split(",") if word.strip()
    )
    return AppSettings(
        enable_sensitive_recall=_as_bool(_get_value("ENABLE_SENSITIVE_RECALL")),
        sensitive_words=words,
    )


def get_deepseek_settings() -> DeepSeekSettings:
    return DeepSeekSettings(
        api_key=_get_value("DEEPSEEK_API_KEY").strip(),
        model=_get_value("DEEPSEEK_MODEL", "deepseek-v4-flash").strip(),
        base_url=_get_value("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/"),
        timeout_seconds=float(_get_value("DEEPSEEK_TIMEOUT_SECONDS", "60")),
        max_output_tokens=int(_get_value("DEEPSEEK_MAX_OUTPUT_TOKENS", "1200")),
    )
