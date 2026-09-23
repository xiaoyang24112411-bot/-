from src import config
from src.config import (
    get_app_settings,
    get_auto_chat_settings,
    get_deepseek_cost_settings,
    get_deepseek_settings,
    get_economy_settings,
    get_information_settings,
    get_media_settings,
)


def test_app_settings(monkeypatch):
    monkeypatch.setenv("ENABLE_SENSITIVE_RECALL", "true")
    monkeypatch.setenv("SENSITIVE_WORDS", "广告, 加群, ")
    monkeypatch.setenv("BOT_ADMIN_IDS", "2448821316，123456 789012")

    settings = get_app_settings()

    assert settings.enable_sensitive_recall is True
    assert settings.sensitive_words == ("广告", "加群")
    assert settings.admin_ids == frozenset({2448821316, 123456, 789012})


def test_app_settings_reject_invalid_admin_id(monkeypatch):
    monkeypatch.setenv("BOT_ADMIN_IDS", "2448821316,not-a-qq")

    try:
        get_app_settings()
    except ValueError as exc:
        assert "not-a-qq" in str(exc)
    else:
        raise AssertionError("invalid administrator QQ number was accepted")


def test_deepseek_settings(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-flash")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/")

    settings = get_deepseek_settings()

    assert settings.api_key == "secret"
    assert settings.model == "deepseek-flash"
    assert settings.base_url == "https://api.deepseek.com"


def test_deepseek_settings_fall_back_to_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "DEEPSEEK_API_KEY=file-secret\n"
        "DEEPSEEK_MODEL=deepseek-flash\n"
        "DEEPSEEK_BASE_URL=https://api.deepseek.com/\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "ENV_FILE", env_file)

    settings = get_deepseek_settings()

    assert settings.api_key == "file-secret"
    assert settings.model == "deepseek-flash"
    assert settings.base_url == "https://api.deepseek.com"


def test_economy_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("ECONOMY_DB_PATH", str(tmp_path / "points.sqlite3"))
    monkeypatch.setenv("CHECKIN_REWARD_MIN", "8")
    monkeypatch.setenv("CHECKIN_REWARD_MAX", "18")
    monkeypatch.setenv("ROBBERY_COOLDOWN_SECONDS", "300")
    monkeypatch.setenv("RED_PACKET_TTL_SECONDS", "7200")
    monkeypatch.setenv("ROULETTE_COOLDOWN_SECONDS", "30")
    monkeypatch.setenv("ROULETTE_MAX_WAGER", "500")
    monkeypatch.setenv("CULTIVATION_COOLDOWN_SECONDS", "45")

    settings = get_economy_settings()

    assert settings.database_path == tmp_path / "points.sqlite3"
    assert settings.checkin_reward_min == 8
    assert settings.checkin_reward_max == 18
    assert settings.robbery_cooldown_seconds == 300
    assert settings.red_packet_ttl_seconds == 7200
    assert settings.roulette_cooldown_seconds == 30
    assert settings.roulette_max_wager == 500
    assert settings.cultivation_cooldown_seconds == 45


def test_media_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setenv("MEDIA_MAX_DOWNLOAD_MB", "25")
    monkeypatch.setenv("SAUCENAO_API_KEY", "sauce-secret")

    settings = get_media_settings()

    assert settings.media_root == tmp_path / "media"
    assert settings.max_download_bytes == 25 * 1024 * 1024
    assert settings.saucenao_api_key == "sauce-secret"


def test_information_settings(monkeypatch):
    monkeypatch.setenv("INFO_60S_API_BASE_URL", "https://info.example/v2/")
    monkeypatch.setenv("TMDB_ACCESS_TOKEN", "tmdb-token")
    monkeypatch.setenv("HOT_SEARCH_LIMIT", "99")

    settings = get_information_settings()

    assert settings.api_60s_base_url == "https://info.example/v2"
    assert settings.tmdb_access_token == "tmdb-token"
    assert settings.hot_search_limit == 20


def test_auto_chat_settings_are_bounded(monkeypatch):
    monkeypatch.setenv("AUTO_CHAT_TRIGGER_PERCENT", "0")
    monkeypatch.setenv("AUTO_CHAT_MIN_MESSAGES", "20")
    monkeypatch.setenv("AUTO_CHAT_CONTEXT_MESSAGES", "6")

    settings = get_auto_chat_settings()

    assert settings.trigger_percent == 1
    assert settings.minimum_messages == settings.context_messages == 6


def test_auto_chat_default_trigger_percent(monkeypatch, tmp_path):
    monkeypatch.delenv("AUTO_CHAT_TRIGGER_PERCENT", raising=False)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    assert get_auto_chat_settings().trigger_percent == 100


def test_peak_cost_protection_defaults_on(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_SUSPEND_AUTOCHAT_DURING_PEAK", raising=False)
    assert get_deepseek_cost_settings().suspend_autochat_during_peak

    monkeypatch.setenv("DEEPSEEK_SUSPEND_AUTOCHAT_DURING_PEAK", "false")
    assert not get_deepseek_cost_settings().suspend_autochat_during_peak


def test_persona_extra_from_environment(monkeypatch):
    monkeypatch.setenv("WHALE_PERSONA_EXTRA", "  用更轻快的语气  ")
    assert config.get_persona_settings().extra_guidance == "用更轻快的语气"

    monkeypatch.setenv("WHALE_PERSONA_EXTRA", "鲸" * 501)
    try:
        config.get_persona_settings()
    except ValueError as exc:
        assert "500" in str(exc)
    else:
        raise AssertionError("oversized persona addition was accepted")
