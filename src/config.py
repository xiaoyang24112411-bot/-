"""Small application-specific settings layered on top of NoneBot settings."""

import os
import re
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


def _as_user_ids(value: str) -> frozenset[int]:
    """Parse a comma, whitespace, or Chinese-comma separated QQ user ID list."""
    user_ids: set[int] = set()
    for item in re.split(r"[,，\s]+", value.strip()):
        if not item:
            continue
        if not item.isdigit() or int(item) <= 0:
            raise ValueError(f"无效的机器人管理员 QQ 号：{item}")
        user_ids.add(int(item))
    return frozenset(user_ids)


@dataclass(frozen=True)
class AppSettings:
    enable_sensitive_recall: bool
    sensitive_words: tuple[str, ...]
    admin_ids: frozenset[int]


@dataclass(frozen=True)
class DeepSeekSettings:
    api_key: str
    model: str
    base_url: str
    timeout_seconds: float
    max_output_tokens: int


@dataclass(frozen=True)
class EconomySettings:
    database_path: Path
    checkin_reward_min: int
    checkin_reward_max: int
    robbery_cooldown_seconds: int
    red_packet_ttl_seconds: int
    roulette_cooldown_seconds: int
    roulette_max_wager: int
    cultivation_cooldown_seconds: int


@dataclass(frozen=True)
class MediaSettings:
    media_root: Path
    max_download_bytes: int
    saucenao_api_key: str


@dataclass(frozen=True)
class InformationSettings:
    api_60s_base_url: str
    api_60s_fallback_urls: tuple[str, ...]
    tmdb_access_token: str
    tmdb_base_url: str
    mangadex_base_url: str
    timeout_seconds: float
    hot_search_limit: int


@dataclass(frozen=True)
class AIFeatureSettings:
    wordcloud_font_path: Path | None
    wordcloud_retention_days: int
    tts_max_characters: int
    tts_timeout_seconds: float


def get_app_settings() -> AppSettings:
    words = tuple(
        word.strip() for word in _get_value("SENSITIVE_WORDS", "广告").split(",") if word.strip()
    )
    return AppSettings(
        enable_sensitive_recall=_as_bool(_get_value("ENABLE_SENSITIVE_RECALL")),
        sensitive_words=words,
        admin_ids=_as_user_ids(_get_value("BOT_ADMIN_IDS", "2448821316")),
    )


def get_deepseek_settings() -> DeepSeekSettings:
    return DeepSeekSettings(
        api_key=_get_value("DEEPSEEK_API_KEY").strip(),
        model=_get_value("DEEPSEEK_MODEL", "deepseek-v4-flash").strip(),
        base_url=_get_value("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/"),
        timeout_seconds=float(_get_value("DEEPSEEK_TIMEOUT_SECONDS", "60")),
        max_output_tokens=int(_get_value("DEEPSEEK_MAX_OUTPUT_TOKENS", "1200")),
    )


def get_economy_settings() -> EconomySettings:
    database_path = Path(_get_value("ECONOMY_DB_PATH", "data/economy/qqbot.sqlite3"))
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path

    reward_min = int(_get_value("CHECKIN_REWARD_MIN", "10"))
    reward_max = int(_get_value("CHECKIN_REWARD_MAX", "30"))
    if reward_min <= 0 or reward_max < reward_min:
        raise ValueError("签到积分范围配置无效")

    return EconomySettings(
        database_path=database_path,
        checkin_reward_min=reward_min,
        checkin_reward_max=reward_max,
        robbery_cooldown_seconds=max(0, int(_get_value("ROBBERY_COOLDOWN_SECONDS", "600"))),
        red_packet_ttl_seconds=max(60, int(_get_value("RED_PACKET_TTL_SECONDS", "86400"))),
        roulette_cooldown_seconds=max(0, int(_get_value("ROULETTE_COOLDOWN_SECONDS", "60"))),
        roulette_max_wager=max(5, int(_get_value("ROULETTE_MAX_WAGER", "1000"))),
        cultivation_cooldown_seconds=max(0, int(_get_value("CULTIVATION_COOLDOWN_SECONDS", "60"))),
    )


def get_media_settings() -> MediaSettings:
    media_root = Path(_get_value("MEDIA_ROOT", "data/media"))
    if not media_root.is_absolute():
        media_root = PROJECT_ROOT / media_root
    max_megabytes = max(5, int(_get_value("MEDIA_MAX_DOWNLOAD_MB", "50")))
    return MediaSettings(
        media_root=media_root,
        max_download_bytes=max_megabytes * 1024 * 1024,
        saucenao_api_key=_get_value("SAUCENAO_API_KEY").strip(),
    )


def get_information_settings() -> InformationSettings:
    fallback_urls = tuple(
        value.strip().rstrip("/")
        for value in _get_value(
            "INFO_60S_API_FALLBACK_URLS",
            "https://60s.crystelf.top/v2,https://60s.7se.cn/v2",
        ).split(",")
        if value.strip()
    )
    return InformationSettings(
        api_60s_base_url=_get_value("INFO_60S_API_BASE_URL", "https://60s.viki.moe/v2")
        .strip()
        .rstrip("/"),
        api_60s_fallback_urls=fallback_urls,
        tmdb_access_token=_get_value("TMDB_ACCESS_TOKEN").strip(),
        tmdb_base_url=_get_value("TMDB_API_BASE_URL", "https://api.themoviedb.org/3")
        .strip()
        .rstrip("/"),
        mangadex_base_url=_get_value("MANGADEX_API_BASE_URL", "https://api.mangadex.org")
        .strip()
        .rstrip("/"),
        timeout_seconds=max(5.0, float(_get_value("INFO_API_TIMEOUT_SECONDS", "20"))),
        hot_search_limit=min(20, max(3, int(_get_value("HOT_SEARCH_LIMIT", "10")))),
    )


def get_ai_feature_settings() -> AIFeatureSettings:
    font_value = _get_value("WORDCLOUD_FONT_PATH").strip()
    font_path = Path(font_value) if font_value else None
    if font_path is not None and not font_path.is_absolute():
        font_path = PROJECT_ROOT / font_path
    return AIFeatureSettings(
        wordcloud_font_path=font_path,
        wordcloud_retention_days=min(90, max(1, int(_get_value("WORDCLOUD_RETENTION_DAYS", "30")))),
        tts_max_characters=min(1000, max(50, int(_get_value("TTS_MAX_CHARACTERS", "300")))),
        tts_timeout_seconds=max(10.0, float(_get_value("TTS_TIMEOUT_SECONDS", "45"))),
    )
