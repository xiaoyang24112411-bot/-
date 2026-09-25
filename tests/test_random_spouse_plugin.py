"""Exercise the group commands without a live QQ connection."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment
from nonebot.exception import FinishedException

from src.services.economy.database import EconomyDatabase
from src.services.entertainment.random_spouse import get_daily_spouse


def event(message, *, user_id=100):
    value = Message(message)
    return GroupMessageEvent(
        time=int(time.time()), self_id=99, post_type="message", message_type="group",
        sub_type="normal", message_id=1, group_id=1, user_id=user_id,
        message=value, original_message=value.copy(), raw_message=str(value), font=0,
        sender={"user_id": user_id, "nickname": "测试群友"}, to_me=False,
    )


@pytest.fixture
def spouse_plugin(monkeypatch, tmp_path):
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.plugins import random_spouse

    database = EconomyDatabase(tmp_path / "spouse.sqlite3")
    monkeypatch.setattr(random_spouse, "get_economy_database", lambda: database)
    for matcher in (
        random_spouse.daily_spouse, random_spouse.force_spouse,
        random_spouse.my_spouse, random_spouse.unlink_spouse,
        random_spouse.leave_pool, random_spouse.join_pool,
    ):
        monkeypatch.setattr(matcher, "finish", AsyncMock(side_effect=FinishedException))
    bot = SimpleNamespace(
        self_id="99",
        get_group_member_list=AsyncMock(return_value=[
            {"user_id": member_id, "nickname": str(member_id)}
            for member_id in (100, 200, 300)
        ]),
        send=AsyncMock(),
    )
    return random_spouse, database, bot


@pytest.mark.asyncio
async def test_command_aliases_mutual_query_unlink_and_force(spouse_plugin):
    plugin, database, bot = spouse_plugin
    assert plugin.is_daily_spouse(event("/抽老婆"))
    assert plugin.is_my_spouse(event("查询老婆"))
    assert plugin.is_unlink_spouse(event("/解绑群友老婆"))
    await plugin.handle_daily_spouse(bot, event("今日老婆"))
    current = await get_daily_spouse(database, group_id=1, user_id=100)
    assert current and current.spouse_user_id in (200, 300)
    await plugin.handle_my_spouse(bot, event("我的老婆", user_id=current.spouse_user_id))
    assert bot.send.await_count == 2

    target = ({200, 300} - {current.spouse_user_id}).pop()
    with pytest.raises(FinishedException):
        await plugin.handle_force_spouse(
            bot, event(MessageSegment.text("强娶 ") + MessageSegment.at(target))
        )
    assert "解绑老婆" in str(plugin.force_spouse.finish.call_args.args[0])
    with pytest.raises(FinishedException):
        await plugin.handle_unlink_spouse(event("解绑老婆", user_id=current.spouse_user_id))
    await plugin.handle_force_spouse(
        bot, event(MessageSegment.text("强娶 ") + MessageSegment.at(target))
    )
    assert (await get_daily_spouse(database, group_id=1, user_id=target)).spouse_user_id == 100


@pytest.mark.asyncio
async def test_opt_out_command_releases_pair(spouse_plugin):
    plugin, database, bot = spouse_plugin
    await plugin.handle_daily_spouse(bot, event("随机老婆"))
    current = await get_daily_spouse(database, group_id=1, user_id=100)
    with pytest.raises(FinishedException):
        await plugin.handle_leave_pool(event("退出老婆池", user_id=current.spouse_user_id))
    assert await get_daily_spouse(database, group_id=1, user_id=100) is None
    assert "解除今日绑定" in plugin.leave_pool.finish.call_args.args[0]
    with pytest.raises(FinishedException):
        await plugin.handle_join_pool(event("加入老婆池", user_id=current.spouse_user_id))
