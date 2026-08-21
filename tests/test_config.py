from src import config
from src.config import get_app_settings, get_deepseek_settings


def test_app_settings(monkeypatch):
    monkeypatch.setenv("ENABLE_SENSITIVE_RECALL", "true")
    monkeypatch.setenv("SENSITIVE_WORDS", "广告, 加群, ")

    settings = get_app_settings()

    assert settings.enable_sensitive_recall is True
    assert settings.sensitive_words == ("广告", "加群")


def test_deepseek_settings(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/")

    settings = get_deepseek_settings()

    assert settings.api_key == "secret"
    assert settings.model == "deepseek-v4-flash"
    assert settings.base_url == "https://api.deepseek.com"


def test_deepseek_settings_fall_back_to_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "DEEPSEEK_API_KEY=file-secret\n"
        "DEEPSEEK_MODEL=deepseek-v4-flash\n"
        "DEEPSEEK_BASE_URL=https://api.deepseek.com/\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "ENV_FILE", env_file)

    settings = get_deepseek_settings()

    assert settings.api_key == "file-secret"
    assert settings.model == "deepseek-v4-flash"
    assert settings.base_url == "https://api.deepseek.com"
