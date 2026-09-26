"""Regression checks for the added official meme template library."""

import hashlib
import json
import os
import runpy
from pathlib import Path

import pytest

from bot import configure_meme_environment
from src.services.meme_avatar import qq_id_from_avatar_url
from src.services.petpet import normalize_command_text, rewrite_petpet_help_command

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync-memes.py"
SCRIPT_FUNCTIONS = runpy.run_path(str(SCRIPT))


def test_legacy_commands_remain_separate_from_new_prefix() -> None:
    assert normalize_command_text("摸摸") == ("摸摸", True)
    assert normalize_command_text("/摸摸 @群友") == ("/摸摸 @群友", True)
    assert normalize_command_text("#摸摸") == ("#摸摸", False)
    assert normalize_command_text("他说#摸摸") == ("他说#摸摸", False)
    assert rewrite_petpet_help_command("/表情列表") == "/头像相关表情包"
    assert rewrite_petpet_help_command("旧表情列表") == "/头像相关表情包"
    assert rewrite_petpet_help_command("/新表情列表") == "/表情包制作"
    assert rewrite_petpet_help_command("#捏") is None


def test_new_memes_defaults_are_configurable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(os, "environ", os.environ.copy())
    for key in (
        "MEMES_COMMAND_PREFIXES",
        "MEMES_USE_SENDER_WHEN_NO_IMAGE",
        "MEMES_PARAMS_MISMATCH_POLICY",
        "MEME_HOME",
        "SUPERUSERS",
        "LOCALSTORE_CONFIG_DIR",
        "LOCALSTORE_DATA_DIR",
        "LOCALSTORE_CACHE_DIR",
        "ALEMBIC_STARTUP_CHECK",
    ):
        monkeypatch.delenv(key, raising=False)

    configure_meme_environment(tmp_path)
    assert os.environ["MEMES_COMMAND_PREFIXES"] == '["#"]'
    assert os.environ["MEMES_USE_SENDER_WHEN_NO_IMAGE"] == "true"
    assert os.environ["SUPERUSERS"] == '["2448821316"]'
    assert "prompt" in os.environ["MEMES_PARAMS_MISMATCH_POLICY"]
    assert Path(os.environ["MEME_HOME"]).is_absolute()
    assert Path(os.environ["LOCALSTORE_DATA_DIR"]).is_absolute()
    assert os.environ["ALEMBIC_STARTUP_CHECK"] == "true"

    monkeypatch.setenv("MEMES_COMMAND_PREFIXES", '["!"]')
    configure_meme_environment(tmp_path)
    assert os.environ["MEMES_COMMAND_PREFIXES"] == '["!"]'


def test_dotenv_settings_and_permanent_admin_survive_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(os, "environ", os.environ.copy())
    for name in (
        "MEMES_COMMAND_PREFIXES", "MEMES_USE_SENDER_WHEN_NO_IMAGE", "SUPERUSERS",
        "MEME_HOME", "LOCALSTORE_CONFIG_DIR", "LOCALSTORE_DATA_DIR", "LOCALSTORE_CACHE_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")
    (tmp_path / ".env").write_text('MEMES_COMMAND_PREFIXES=["base"]\n', encoding="utf-8")
    (tmp_path / ".env.test").write_text(
        'MEMES_COMMAND_PREFIXES=["!"]\nMEMES_USE_SENDER_WHEN_NO_IMAGE=false\n'
        'SUPERUSERS=["12345"]\nMEME_HOME=custom-assets\n', encoding="utf-8",
    )
    configure_meme_environment(tmp_path)
    assert json.loads(os.environ["MEMES_COMMAND_PREFIXES"]) == ["!"]
    assert os.environ["MEMES_USE_SENDER_WHEN_NO_IMAGE"] == "false"
    assert json.loads(os.environ["SUPERUSERS"]) == ["12345", "2448821316"]
    assert Path(os.environ["MEME_HOME"]) == tmp_path / "custom-assets"
    assert Path(os.environ["LOCALSTORE_DATA_DIR"]).is_relative_to(tmp_path / "custom-assets")
    monkeypatch.setenv("MEMES_COMMAND_PREFIXES", '["process"]')
    configure_meme_environment(tmp_path)
    assert json.loads(os.environ["MEMES_COMMAND_PREFIXES"]) == ["process"]


def test_resource_verification_reports_missing_and_corrupt(tmp_path: Path) -> None:
    expected_resource_path = SCRIPT_FUNCTIONS["expected_resource_path"]
    verify_resources = SCRIPT_FUNCTIONS["verify_resources"]
    content = b"good image"
    resource = expected_resource_path(tmp_path, "images", "sample/0.png")
    resource.parent.mkdir(parents=True)
    resource.write_bytes(content)
    manifest = {
        "fonts": [],
        "images": [{"file": "sample/0.png", "hash": hashlib.sha256(content).hexdigest()}],
    }
    assert verify_resources(tmp_path, manifest) == []
    resource.write_bytes(b"corrupt")
    assert verify_resources(tmp_path, manifest) == ["images/sample/0.png"]

    with pytest.raises(ValueError, match="Unsafe resource"):
        expected_resource_path(tmp_path, "images", "../outside.png")
    with pytest.raises(ValueError, match="Unsafe resource"):
        expected_resource_path(tmp_path, "images", "C:/outside.png")


def test_qq_avatar_url_recognition_is_host_restricted() -> None:
    assert qq_id_from_avatar_url("http://q1.qlogo.cn/g?b=qq&nk=123456&s=640") == "123456"
    assert qq_id_from_avatar_url("https://q2.qlogo.cn/headimg_dl?dst_uin=123456") == "123456"
    assert (
        qq_id_from_avatar_url("https://qlogo4.store.qq.com/qzone/123456/123456/640")
        == "123456"
    )
    assert qq_id_from_avatar_url("https://q1.qlogo.cn.evil.example/g?nk=123456") is None
    assert qq_id_from_avatar_url("file:///avatar.png") is None
