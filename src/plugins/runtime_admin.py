"""Help, runtime status, and tightly restricted process controls."""

import asyncio
import os
import sys
import time
from pathlib import Path

import nonebot
from nonebot import on_command, on_fullmatch
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.exception import IgnoredException
from nonebot.message import event_preprocessor
from nonebot.params import CommandArg

from src.config import get_deepseek_settings
from src.services.permissions import is_bot_admin

STARTED_AT = time.monotonic()
maintenance_mode = False

HELP_TEXT = """====== Bot 完整指令 ======
【基础】
/help　查看帮助
/ping　测试连通与延迟

【群管｜群管理或终极管理员】
/ban @群友 分钟　禁言
/unban @群友　解除禁言
/kick @群友 [理由]　移出群聊
/set_title @群友 头衔　设置头衔
/ban_all　开启全员禁言
/unban_all　关闭全员禁言
/withdraw　撤回机器人上一条群消息

【AI 对话】
/ai 问题　DeepSeek 对话
/深度问 问题　深度推理（较慢、消耗更多额度）
/联网问 问题　联网搜索并列出来源（需 Brave API Key）
/深度联网问 问题　联网搜索 + 深度推理
/记忆清除　清空自己的上下文
设置人格 内容｜查看人格｜重置人格

【工具】
/天气 城市
/缩写 词
/calc 算式
/今日词云｜/本周词云

【积分与娱乐】
/签到｜/积分｜/排行榜
/转账 @群友 积分｜/发红包 总分 份数｜/抢红包
/打劫｜/商店｜/兑换 商品编号 [数量]
/roll 1-100｜掷骰子 2d6
/今日运势｜/人品
/魔法占卜｜/答案之书 问题｜/舔狗日记
/今日老婆｜/强娶 @群友
/原神10抽｜/方舟十连｜/fgo一井
/表情列表
/表情 模板名 [文字/@群友]

【群聊游戏】
五子棋｜加入五子棋｜落子 H8｜结束五子棋
人生重开｜牛牛修仙｜修炼｜突破
俄罗斯轮盘 积分｜游戏王查卡 卡名

【媒体与信息】
随机图片 [分类]｜随机视频 [分类]
图转字符 + 图片｜网页截图 URL｜取CQ码
视频解析 URL｜图集解析 URL｜图片来源 + 图片
今日油价 城市｜每天60秒｜热搜 平台
影视搜索 片名｜漫画搜索 作品名｜高质量文案

【语音与群聊统计】
点歌 歌名｜随机唱鸭｜语音 [角色] 文字
开启词云记录｜关闭词云记录｜词云状态

【订阅与撤回｜群管理或终极管理员】
/bili_sub UID｜/bili_unsub UID｜/bili_list
/rss add URL｜/rss del 编号或URL｜/rss list
/开启撤回记录｜/关闭撤回记录｜/查看撤回

【机器人终极管理员】
/status｜/echo 文本｜/API预设
/reload｜/restart｜/stop（维护模式）｜/start"""

help_command = on_command("help", aliases={"帮助"}, priority=5, block=True)
full_help_command = on_fullmatch(("完整指令", "/完整指令"), priority=5, block=True)
status_command = on_command("status", priority=5, block=True)
echo_command = on_command("echo", priority=5, block=True)
reload_command = on_command("reload", priority=5, block=True)
restart_command = on_command("restart", priority=5, block=True)
stop_command = on_command("stop", priority=5, block=True)
start_command = on_command("start", priority=5, block=True)
api_preset = on_command("API预设", priority=5, block=True)


def _memory_megabytes() -> str:
    status = Path("/proc/self/status")
    if status.is_file():
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return f"{int(line.split()[1]) / 1024:.1f} MB"
    return "当前平台不可用"


def _uptime() -> str:
    seconds = int(time.monotonic() - STARTED_AT)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}小时 {minutes}分 {seconds}秒"


async def _require_admin(matcher, event: MessageEvent) -> None:
    if not is_bot_admin(event):
        await matcher.finish("仅机器人终极管理员可执行此指令。")


async def _exit_later() -> None:
    await asyncio.sleep(1)
    os._exit(0)


@event_preprocessor
async def block_during_maintenance(event: MessageEvent) -> None:
    if maintenance_mode and not is_bot_admin(event):
        raise IgnoredException


@help_command.handle()
async def handle_help() -> None:
    await help_command.finish(HELP_TEXT)


@full_help_command.handle()
async def handle_full_help() -> None:
    await full_help_command.finish(HELP_TEXT)


@status_command.handle()
async def handle_status(event: MessageEvent) -> None:
    await _require_admin(status_command, event)
    plugins = sorted(plugin.name for plugin in nonebot.get_loaded_plugins())
    await status_command.finish(
        "机器人运行正常\n"
        f"Python：{sys.version.split()[0]}\n"
        f"运行时间：{_uptime()}\n"
        f"内存：{_memory_megabytes()}\n"
        f"插件：{len(plugins)} 个\n"
        f"维护模式：{'开启' if maintenance_mode else '关闭'}"
    )


@echo_command.handle()
async def handle_echo(event: MessageEvent, args: Message = CommandArg()) -> None:  # noqa: B008
    await _require_admin(echo_command, event)
    text = args.extract_plain_text().strip()
    if not text:
        await echo_command.finish("用法：/echo 要发送的文本")
    await echo_command.finish(MessageSegment.text(text))


async def _restart(matcher, event: MessageEvent) -> None:
    await _require_admin(matcher, event)
    asyncio.create_task(_exit_later())
    await matcher.finish("正在重新载入全部插件；Docker 会自动拉起机器人。")


@reload_command.handle()
async def handle_reload(event: MessageEvent) -> None:
    # In-place reload duplicates matcher registrations; a clean process restart is safer.
    await _restart(reload_command, event)


@restart_command.handle()
async def handle_restart(event: MessageEvent) -> None:
    await _restart(restart_command, event)


@stop_command.handle()
async def handle_stop(event: MessageEvent) -> None:
    global maintenance_mode
    await _require_admin(stop_command, event)
    maintenance_mode = True
    await stop_command.finish("机器人已进入维护模式，不再处理普通成员指令。发送 /start 恢复。")


@start_command.handle()
async def handle_start(event: MessageEvent) -> None:
    global maintenance_mode
    await _require_admin(start_command, event)
    maintenance_mode = False
    await start_command.finish("维护模式已关闭，机器人恢复服务。")


@api_preset.handle()
async def handle_api_preset(event: MessageEvent) -> None:
    await _require_admin(api_preset, event)
    settings = get_deepseek_settings()
    await api_preset.finish(
        "当前仅配置一个 DeepSeek 预设：\n"
        f"模型：{settings.model}\n"
        f"接口：{settings.base_url}\n"
        f"API Key：{'已配置' if settings.api_key else '未配置'}"
    )
