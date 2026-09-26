import asyncio
import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from nonebot.exception import FinishedException

from src.services.meme_avatar import MemeImageDownloadError, fetch_meme_image


def avatar(**overrides):
    return SimpleNamespace(**{
        "url": "http://q1.qlogo.cn/g?nk=123456", "raw": None, "path": None, **overrides,
    })


@pytest.mark.asyncio
async def test_download_uses_native_fallback_but_keeps_embedded_image():
    native = AsyncMock(return_value=b"native")
    downloader = AsyncMock(side_effect=httpx.ConnectError("offline"))
    assert await fetch_meme_image(
        None, None, {}, avatar(), native_fetch=native, avatar_fetch=downloader
    ) == b"native"
    downloader.assert_awaited_once_with("123456", timeout=5)
    downloader.reset_mock()
    assert await fetch_meme_image(
        None, None, {}, avatar(raw=b"embedded"),
        native_fetch=native, avatar_fetch=downloader,
    ) == b"native"
    downloader.assert_not_awaited()


@pytest.mark.asyncio
async def test_download_errors_and_total_deadline_are_actionable():
    native = AsyncMock(side_effect=httpx.ConnectError("offline"))
    downloader = AsyncMock(side_effect=RuntimeError("all avatar endpoints offline"))
    with pytest.raises(MemeImageDownloadError):
        await fetch_meme_image(
            None, None, {}, avatar(), native_fetch=native, avatar_fetch=downloader
        )

    async def hang(*args, **kwargs):
        await asyncio.sleep(5)

    with pytest.raises(MemeImageDownloadError):
        await fetch_meme_image(
            None, None, {}, avatar(), native_fetch=hang, avatar_fetch=hang, timeout=0.01,
        )
    cancelled = AsyncMock(side_effect=asyncio.CancelledError)
    with pytest.raises(asyncio.CancelledError):
        await fetch_meme_image(
            None, None, {}, avatar(), native_fetch=native, avatar_fetch=cancelled,
        )


@pytest.fixture
def runtime_wrapper(monkeypatch):
    # Load only our narrow adapter with an isolated upstream module; no startup,
    # network access, ORM migration or thousands of matchers are required here.
    native = SimpleNamespace(
        image_fetch=AsyncMock(), record_meme_generation=AsyncMock(), process=AsyncMock(),
    )
    matchers = ModuleType("nonebot_plugin_memes.matchers")
    matchers.command = native
    monkeypatch.setitem(sys.modules, "nonebot_plugin_memes.matchers", matchers)
    path = Path(__file__).resolve().parents[1] / "src/plugins/new_memes_compat.py"
    return runpy.run_path(str(path)), native


@pytest.mark.asyncio
async def test_stats_failure_does_not_discard_successful_image(runtime_wrapper):
    wrapper, native = runtime_wrapper
    wrapper["original_record"].side_effect = RuntimeError("database unavailable")
    assert await native.record_meme_generation("session", "petpet") is None
    wrapper["original_record"].side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await native.record_meme_generation("session", "petpet")


@pytest.mark.asyncio
@pytest.mark.parametrize("error, expected", [
    (MemeImageDownloadError("offline"), "头像或图片下载失败"),
    (RuntimeError("renderer failed"), "表情生成失败"),
])
async def test_render_failures_reply_once(runtime_wrapper, error, expected):
    wrapper, native = runtime_wrapper
    wrapper["original_process"].side_effect = error
    matcher = SimpleNamespace(finish=AsyncMock(side_effect=FinishedException))
    with pytest.raises(FinishedException):
        await native.process(None, None, {}, matcher, None, SimpleNamespace(key="test"), [], [])
    matcher.finish.assert_awaited_once()
    assert expected in matcher.finish.call_args.args[0]


@pytest.mark.asyncio
async def test_successful_matcher_finish_is_not_reported_as_render_failure(runtime_wrapper):
    wrapper, native = runtime_wrapper
    wrapper["original_process"].side_effect = FinishedException
    matcher = SimpleNamespace(finish=AsyncMock())
    with pytest.raises(FinishedException):
        await native.process(None, None, {}, matcher, None, SimpleNamespace(key="test"), [], [])
    matcher.finish.assert_not_awaited()
