import signal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.exception import FinishedException

from src.services.command_help import (
    SEARCH_RESULT_LIMIT,
    category_index,
    render_help,
    search_commands,
)


@pytest.fixture
def help_plugin():
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.plugins import runtime_admin

    return runtime_admin


def test_full_help_and_category_navigation(help_plugin):
    menu = help_plugin.HELP_TEXT
    assert render_help(menu) == menu
    assert render_help(menu, "全部") == menu
    assert "/头像盲盒" in render_help(menu, "表情")
    assert "/转账" in render_help(menu, "积分")
    assert "/头像盲盒" not in render_help(menu, "积分")
    assert "DeepSeek" in render_help(menu, " ai ")
    assert "群管理或终极管理员" in render_help(menu, "群管")
    assert "机器人终极管理员" in render_help(menu, "主人")
    assert "/指令搜索" in category_index(menu)
    assert "积分与商店" in render_help(menu, "分类")


def test_keyword_search_finds_real_commands_and_handles_unknown_category(help_plugin):
    menu = help_plugin.HELP_TEXT
    result = search_commands(menu, "老婆")
    assert "/解绑老婆" in result
    assert "退出老婆池" in result
    assert "#关键词" not in result
    assert "/头像模板" in search_commands(menu, "头像")
    assert "/bili_sub" in search_commands(menu, "BILI_SUB")
    assert "/天气 城市" in render_help(menu, "天气")
    assert "没有“天气”这个帮助分类" in render_help(menu, "天气")
    assert "没有找到" in search_commands(menu, "根本不存在的功能")
    assert "用法" in search_commands(menu, "  ")


def test_search_stays_bounded_when_a_keyword_matches_many_commands():
    menu = "【测试分类】\n" + "\n".join(f"/功能{number} 测试" for number in range(40))
    result = search_commands(menu, "功能")
    assert "共 40 条" in result
    assert result.count("【测试分类】") == SEARCH_RESULT_LIMIT
    assert "更具体的关键词" in result
    assert "64 个字符" in search_commands(menu, "测" * 65)


@pytest.mark.asyncio
async def test_help_handlers_use_arguments_and_escape_user_text(help_plugin, monkeypatch):
    monkeypatch.setattr(
        help_plugin.help_command, "finish", AsyncMock(side_effect=FinishedException)
    )
    monkeypatch.setattr(
        help_plugin.search_help_command, "finish", AsyncMock(side_effect=FinishedException)
    )
    with pytest.raises(FinishedException):
        await help_plugin.handle_help(Message("表情"))
    assert "/头像盲盒" in help_plugin.help_command.finish.call_args.args[0].data["text"]
    with pytest.raises(FinishedException):
        await help_plugin.handle_search_help(Message(MessageSegment.text("[CQ:image,file=evil]")))
    reply = help_plugin.search_help_command.finish.call_args.args[0]
    assert reply.type == "text"
    assert "[CQ:image,file=evil]" in reply.data["text"]


@pytest.mark.asyncio
async def test_local_restart_keeps_bot_running_and_admin_restriction(help_plugin, monkeypatch):
    matcher = SimpleNamespace(finish=AsyncMock(side_effect=FinishedException))
    create_task = Mock()
    monkeypatch.setattr(help_plugin, "Path", lambda _: SimpleNamespace(is_file=lambda: False))
    monkeypatch.setattr(help_plugin.asyncio, "create_task", create_task)
    monkeypatch.setattr(help_plugin, "is_bot_admin", lambda _: False)
    with pytest.raises(FinishedException):
        await help_plugin._restart(matcher, SimpleNamespace(user_id=100))
    assert "仅机器人终极管理员" in matcher.finish.call_args.args[0]
    monkeypatch.setattr(help_plugin, "is_bot_admin", lambda _: True)
    with pytest.raises(FinishedException):
        await help_plugin._restart(matcher, SimpleNamespace(user_id=2448821316))
    assert "机器人目前仍在运行" in matcher.finish.call_args.args[0]
    create_task.assert_not_called()


@pytest.mark.asyncio
async def test_container_restart_still_schedules_process_exit(help_plugin, monkeypatch):
    matcher = SimpleNamespace(finish=AsyncMock(side_effect=FinishedException))
    create_task = Mock(side_effect=lambda coroutine: coroutine.close())
    monkeypatch.setattr(help_plugin, "Path", lambda _: SimpleNamespace(is_file=lambda: True))
    monkeypatch.setattr(help_plugin.asyncio, "create_task", create_task)
    monkeypatch.setattr(help_plugin, "is_bot_admin", lambda _: True)
    with pytest.raises(FinishedException):
        await help_plugin._restart(matcher, SimpleNamespace(user_id=2448821316))
    assert "Docker" in matcher.finish.call_args.args[0]
    create_task.assert_called_once()


@pytest.mark.asyncio
async def test_delayed_exit_sends_graceful_termination_after_reply_delay(help_plugin, monkeypatch):
    call_order = []
    abrupt_exit = Mock()

    async def delay(seconds):
        call_order.append(("sleep", seconds))

    monkeypatch.setattr(help_plugin.asyncio, "sleep", delay)
    monkeypatch.setattr(help_plugin.os, "getpid", lambda: 12345)
    monkeypatch.setattr(help_plugin.os, "_exit", abrupt_exit)
    monkeypatch.setattr(
        help_plugin.os, "kill", lambda pid, sig: call_order.append(("signal", pid, sig))
    )
    await help_plugin._exit_later()
    assert call_order == [("sleep", 1), ("signal", 12345, signal.SIGTERM)]
    abrupt_exit.assert_not_called()
