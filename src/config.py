"""Small application-specific settings layered on top of NoneBot settings."""

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env.prod"
PERMANENT_ADMIN_IDS = frozenset({2448821316})
AUTO_CHAT_CONTROLLER_ID = 2448821316


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
    deep_max_output_tokens: int = 4096


@dataclass(frozen=True)
class WebSearchSettings:
    api_key: str
    base_url: str
    timeout_seconds: float


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


@dataclass(frozen=True)
class AutoChatSettings:
    minimum_messages: int
    context_messages: int
    trigger_percent: int
    context_ttl_seconds: int
    quiet_start_hour: int
    quiet_end_hour: int


@dataclass(frozen=True)
class DeepSeekCostSettings:
    suspend_autochat_during_peak: bool


@dataclass(frozen=True)
class SubscriptionSettings:
    rss_poll_seconds: int
    bili_poll_seconds: int
    bilibili_api_base_url: str
    bilibili_live_api_base_url: str
    bilibili_sessdata: str


@dataclass(frozen=True)
class CommunitySettings:
    choices_enabled: bool = True
    polls_enabled: bool = True
    reminders_enabled: bool = True
    polls_max_active_per_group: int = 5
    reminder_poll_seconds: int = 5
    reminders_max_active_per_user: int = 10
    reminders_max_active_per_group: int = 100


@lru_cache(maxsize=1)
def get_community_settings() -> CommunitySettings:
    """Local group utilities; edits take effect after restarting the bot."""
    def integer(name: str, default: int, maximum: int) -> int:
        try:
            value = int(_get_value(name, str(default)))
        except ValueError as exc:
            raise ValueError(f"{name} 必须是整数") from exc
        if not 1 <= value <= maximum:
            raise ValueError(f"{name} 必须在 1～{maximum} 之间")
        return value

    return CommunitySettings(
        choices_enabled=_as_bool(_get_value("GROUP_CHOICES_ENABLED", "true")),
        polls_enabled=_as_bool(_get_value("GROUP_POLLS_ENABLED", "true")),
        reminders_enabled=_as_bool(_get_value("GROUP_REMINDERS_ENABLED", "true")),
        polls_max_active_per_group=integer("GROUP_POLLS_MAX_ACTIVE", 5, 50),
        reminder_poll_seconds=integer("GROUP_REMINDER_POLL_SECONDS", 5, 60),
        reminders_max_active_per_user=integer("GROUP_REMINDER_MAX_PER_USER", 10, 100),
        reminders_max_active_per_group=integer("GROUP_REMINDER_MAX_PER_GROUP", 100, 1000),
    )


@dataclass(frozen=True)
class GreetingSettings:
    enabled: bool = True
    group_ids: frozenset[int] = frozenset()
    ignored_user_ids: frozenset[int] = frozenset()
    user_cooldown_seconds: int = 0
    group_cooldown_seconds: int = 0
    morning_words: tuple[str, ...] = ("早安", "早上好", "早晨好")
    night_words: tuple[str, ...] = ("晚安", "晚上好")
    morning_replies: tuple[str, ...] = (
        "早安！愿你今天有个好心情 ☀️",
        "早上好呀，记得吃早餐！",
        "新的一天开始啦，祝你一切顺利～",
        "早安，今天也要好好照顾自己呀。",
        "早呀！愿今天有开心的小事发生。",
    )
    night_replies: tuple[str, ...] = (
        "晚安呀，祝你做个好梦 🌙",
        "辛苦一天啦，好好休息吧。",
        "晚安，愿你今晚睡得安稳。",
        "把烦恼暂时放下，明天再慢慢来～",
        "好梦呀，醒来又是新的一天！",
    )


def _greeting_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = _get_value(name).strip()
    if not raw:
        return default
    try:
        values = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是非空 JSON 字符串数组") from exc
    if (
        not isinstance(values, list) or not values
        or any(not isinstance(value, str) or not value.strip() for value in values)
    ):
        raise ValueError(f"{name} 必须是非空 JSON 字符串数组")
    return tuple(dict.fromkeys(value.strip() for value in values))


@lru_cache(maxsize=1)
def get_greeting_settings() -> GreetingSettings:
    """Read once at startup, like the group-management plugin; restart to apply edits."""
    defaults = GreetingSettings()
    cooldowns = {}
    for name, default in (
        ("GREETING_USER_COOLDOWN_SECONDS", 0),
        ("GREETING_GROUP_COOLDOWN_SECONDS", 0),
    ):
        try:
            seconds = int(_get_value(name, str(default)))
        except ValueError as exc:
            raise ValueError(f"{name} 必须是非负整数秒数") from exc
        if seconds < 0:
            raise ValueError(f"{name} 必须是非负整数秒数")
        cooldowns[name] = seconds
    morning_words = _greeting_list("GREETING_MORNING_WORDS", defaults.morning_words)
    night_words = _greeting_list("GREETING_NIGHT_WORDS", defaults.night_words)
    if set(morning_words) & set(night_words):
        raise ValueError("早安和晚安触发词不能重复")
    return GreetingSettings(
        enabled=_as_bool(_get_value("GREETING_ENABLED", "true")),
        group_ids=_as_user_ids(_get_value("GREETING_GROUP_IDS")),
        ignored_user_ids=_as_user_ids(_get_value("GREETING_IGNORED_USER_IDS")),
        user_cooldown_seconds=cooldowns["GREETING_USER_COOLDOWN_SECONDS"],
        group_cooldown_seconds=cooldowns["GREETING_GROUP_COOLDOWN_SECONDS"],
        morning_words=morning_words,
        night_words=night_words,
        morning_replies=_greeting_list("GREETING_MORNING_REPLIES", defaults.morning_replies),
        night_replies=_greeting_list("GREETING_NIGHT_REPLIES", defaults.night_replies),
    )


def get_app_settings() -> AppSettings:
    words = tuple(
        word.strip() for word in _get_value("SENSITIVE_WORDS", "广告").split(",") if word.strip()
    )
    return AppSettings(
        enable_sensitive_recall=_as_bool(_get_value("ENABLE_SENSITIVE_RECALL")),
        sensitive_words=words,
        admin_ids=_as_user_ids(_get_value("BOT_ADMIN_IDS", "")) | PERMANENT_ADMIN_IDS,
    )


def get_deepseek_settings() -> DeepSeekSettings:
    return DeepSeekSettings(
        api_key=_get_value("DEEPSEEK_API_KEY").strip(),
        model=_get_value("DEEPSEEK_MODEL", "deepseek-flash").strip(),
        base_url=_get_value("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/"),
        timeout_seconds=float(_get_value("DEEPSEEK_TIMEOUT_SECONDS", "60")),
        max_output_tokens=int(_get_value("DEEPSEEK_MAX_OUTPUT_TOKENS", "1200")),
        deep_max_output_tokens=max(
            2000, int(_get_value("DEEPSEEK_DEEP_MAX_OUTPUT_TOKENS", "4096"))
        ),
    )


def get_web_search_settings() -> WebSearchSettings:
    return WebSearchSettings(
        api_key=_get_value("BRAVE_SEARCH_API_KEY").strip(),
        base_url="https://api.search.brave.com/res/v1/llm/context",
        timeout_seconds=max(5.0, float(_get_value("WEB_SEARCH_TIMEOUT_SECONDS", "20"))),
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


def get_auto_chat_settings() -> AutoChatSettings:
    context_messages = min(
        30, max(6, int(_get_value("AUTO_CHAT_CONTEXT_MESSAGES", "12")))
    )
    minimum_messages = min(
        context_messages, max(3, int(_get_value("AUTO_CHAT_MIN_MESSAGES", "6")))
    )
    return AutoChatSettings(
        minimum_messages=minimum_messages,
        context_messages=context_messages,
        trigger_percent=min(100, max(1, int(_get_value("AUTO_CHAT_TRIGGER_PERCENT", "80")))),
        context_ttl_seconds=max(300, int(_get_value("AUTO_CHAT_CONTEXT_TTL_SECONDS", "1200"))),
        quiet_start_hour=min(23, max(0, int(_get_value("AUTO_CHAT_QUIET_START_HOUR", "0")))),
        quiet_end_hour=min(23, max(0, int(_get_value("AUTO_CHAT_QUIET_END_HOUR", "7")))),
    )


def get_deepseek_cost_settings() -> DeepSeekCostSettings:
    return DeepSeekCostSettings(
        suspend_autochat_during_peak=_as_bool(
            _get_value("DEEPSEEK_SUSPEND_AUTOCHAT_DURING_PEAK", "true"),
            default=True,
        )
    )


def get_subscription_settings() -> SubscriptionSettings:
    return SubscriptionSettings(
        rss_poll_seconds=max(60, int(_get_value("RSS_POLL_SECONDS", "300"))),
        bili_poll_seconds=max(60, int(_get_value("BILI_POLL_SECONDS", "180"))),
        bilibili_api_base_url=_get_value(
            "BILIBILI_API_BASE_URL", "https://api.bilibili.com"
        ).strip().rstrip("/"),
        bilibili_live_api_base_url=_get_value(
            "BILIBILI_LIVE_API_BASE_URL", "https://api.live.bilibili.com"
        ).strip().rstrip("/"),
        bilibili_sessdata=_get_value("BILIBILI_SESSDATA").strip(),
    )
