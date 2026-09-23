"""Image ingress, group isolation, and proactive meme gating."""

from io import BytesIO

import httpx
import pytest
import respx
from PIL import Image

from src.config import MemeSettings
from src.services.economy import EconomyError
from src.services.economy.database import EconomyDatabase
from src.services.media.meme_library import (
    delete_meme,
    last_proactive_meme_at,
    mark_proactive_meme_sent,
    meme_count,
    meme_fits_chat,
    proactive_meme_enabled,
    random_meme,
    save_meme,
    select_proactive_meme,
    set_proactive_meme_enabled,
)
from src.services.media.qq_image import fetch_qq_image, inspect_image


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (4, 4), "blue").save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def settings(tmp_path):
    return MemeSettings(tmp_path / "memes", 1024 * 1024, 2, 100, 1800)


@pytest.mark.asyncio
async def test_meme_save_dedupe_isolation_and_delete(tmp_path, settings):
    db = EconomyDatabase(tmp_path / "bot.sqlite3")
    first, created = await save_meme(db, settings, 100, 5, png_bytes())
    duplicate, created_again = await save_meme(db, settings, 100, 7, png_bytes())
    other, created_other = await save_meme(db, settings, 200, 5, png_bytes())
    assert created and created_other and not created_again
    assert duplicate.id == first.id
    assert await meme_count(db, 100) == 1
    assert await meme_count(db, 200) == 1
    assert (await random_meme(db, settings, 100)).path == first.path
    assert other.path != first.path
    assert not await delete_meme(db, settings, 200, first.id)
    assert await delete_meme(db, settings, 100, first.id)
    assert not first.path.exists()
    assert other.path.exists()


@pytest.mark.asyncio
async def test_proactive_meme_is_opt_in_per_group_and_has_interval(tmp_path, settings):
    db = EconomyDatabase(tmp_path / "bot.sqlite3")
    await save_meme(db, settings, 100, 5, png_bytes())
    last_proactive_meme_at.clear()
    assert not await proactive_meme_enabled(db, 100)
    assert await select_proactive_meme(db, settings, 100, now=1000) is None
    await set_proactive_meme_enabled(db, 100, True, 2448821316)
    assert await proactive_meme_enabled(db, 100)
    assert not await proactive_meme_enabled(db, 200)
    assert await select_proactive_meme(db, settings, 100, now=1000) is not None
    mark_proactive_meme_sent(100, now=1000)
    assert await select_proactive_meme(db, settings, 100, now=1001) is None
    assert await select_proactive_meme(db, settings, 100, now=2800) is not None


@respx.mock
@pytest.mark.asyncio
async def test_qq_image_fetch_validated():
    url = "https://gchat.qpic.cn/example"
    respx.get(url).mock(return_value=httpx.Response(200, content=png_bytes()))
    image, extension = await fetch_qq_image(url)
    assert image == png_bytes()
    assert extension == "png"


@pytest.mark.asyncio
async def test_qq_image_rejects_untrusted_and_invalid_content():
    with pytest.raises(EconomyError, match="QQ 群消息"):
        await fetch_qq_image("http://127.0.0.1/private")
    with pytest.raises(EconomyError, match="QQ 群消息"):
        await fetch_qq_image("https://qpic.cn.evil.example/pic")
    with pytest.raises(EconomyError, match="无法识别"):
        inspect_image(b"not-an-image", 1024)


def test_proactive_image_tone_filter():
    assert meme_fits_chat(("今天好开心",), "哼，本鲸也很开心啦！")
    assert not meme_fits_chat(("朋友住院了",), "哼，本鲸在这里陪你。")
    assert not meme_fits_chat(("天气如何",), "北京今天多云。")
