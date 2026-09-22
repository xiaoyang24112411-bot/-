from contextlib import AsyncExitStack
from unittest.mock import AsyncMock

import httpx
import nonebot
import pytest
import respx
from nonebot.adapters.onebot.v11 import Adapter, Bot, GroupMessageEvent, Message
from nonebot.dependencies import Dependent
from nonebot.exception import IgnoredException
from nonebot.message import EVENT_PCS_PARAMS

from src.services.economy.errors import EconomyError
from src.services.media.ascii_art import download_image
from src.services.media.message_image import image_url_from_event


def group_event(text="摸摸", reply=None):
    return GroupMessageEvent(
        time=1, self_id=2, post_type="message", message_type="group", sub_type="normal",
        user_id=3, group_id=4, message_id=5, message=Message(text), raw_message=text,
        font=0, sender={"user_id": 3, "role": "admin"}, reply=reply,
    )


def replied_message():
    return {
        "time": 1, "message_type": "group", "message_id": 81, "real_id": 81,
        "sender": {"user_id": 8},
        "message": [{"type": "image", "data": {"url": "https://example.com/avatar.png"}}],
    }


@pytest.mark.asyncio
async def test_image_reply_already_consumed_by_onebot():
    event = group_event("图转字符", reply=replied_message())
    bot = AsyncMock()
    assert await image_url_from_event(bot, event) == "https://example.com/avatar.png"
    bot.get_msg.assert_not_called()


def init_nonebot():
    try:
        return nonebot.get_driver()
    except ValueError:
        nonebot.init()
        return nonebot.get_driver()


def test_withdraw_uses_onebot_reply_instead_of_bot_history():
    init_nonebot()
    from src.plugins.group_admin_commands import _reply_message_id

    assert _reply_message_id(group_event("/withdraw", reply=replied_message())) == 81


@pytest.mark.asyncio
async def test_petpet_lock_released_when_other_preprocessor_ignores_event():
    driver = init_nonebot()
    from src.compat.pillow import apply_pillow_compatibility

    apply_pillow_compatibility()
    assert nonebot.load_plugin("nonebot_plugin_petpet") is not None
    from src.plugins import petpet_compat

    bot = Bot(Adapter(driver), "2")
    processor = Dependent.parse(
        call=petpet_compat.normalize_petpet_message, allow_types=EVENT_PCS_PARAMS
    )
    event = group_event()
    with pytest.raises(IgnoredException):
        async with AsyncExitStack() as stack:
            await processor(bot=bot, event=event, state={}, stack=stack, dependency_cache={})
            assert petpet_compat.petpet_render_lock.locked()
            # NoneBot skips its event postprocessors on exactly this path.
            raise IgnoredException("maintenance mode")
    assert not petpet_compat.petpet_render_lock.locked()
    assert not petpet_compat.active_petpet_events

    # The next meme can acquire the renderer rather than staying busy forever.
    async with AsyncExitStack() as stack:
        await processor(
            bot=bot, event=group_event(), state={}, stack=stack, dependency_cache={}
        )
        assert petpet_compat.petpet_render_lock.locked()
    assert not petpet_compat.petpet_render_lock.locked()


@pytest.mark.asyncio
async def test_image_download_stops_before_consuming_oversized_stream():
    class LargeStream(httpx.AsyncByteStream):
        def __init__(self):
            self.chunks_read = 0

        async def __aiter__(self):
            for _ in range(20):
                self.chunks_read += 1
                yield b"x" * (64 * 1024)

    stream = LargeStream()
    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/large.png").mock(
            return_value=httpx.Response(200, stream=stream)
        )
        with pytest.raises(EconomyError, match="大小"):
            await download_image("https://example.com/large.png", max_bytes=64 * 1024)
    assert stream.chunks_read == 2


@pytest.mark.asyncio
async def test_image_download_accepts_small_image():
    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/small.png").mock(
            return_value=httpx.Response(200, content=b"small-image")
        )
        assert await download_image("https://example.com/small.png", max_bytes=32) == b"small-image"
