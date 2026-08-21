# QQ 机器人：NoneBot2 + OneBot V11

一个可直接运行、方便继续加插件的 QQ 机器人骨架。已实现：

- 群聊或私聊发送 `ping`，回复 `pong`；
- 发送 `/天气 城市名`，通过 Open-Meteo 查询实时天气；
- 新成员进群时自动 `@` 并欢迎；
- 可选的敏感词消息撤回（默认关闭）。
- `/问 内容` 调用 DeepSeek V4 回答问题。
- `摸摸`、`搓头`、`拍拍` 和常用 GIF 指令根据群友头像生成表情包。

> QQ 协议端并非腾讯官方机器人接口。请了解账号风控和平台规则，建议使用专门的测试账号，不要对外暴露 WebUI 或 OneBot 端口。

## 1. 项目结构

```text
.
├── bot.py                         # 应用入口：初始化 NoneBot、注册适配器、加载插件
├── pyproject.toml                 # Python 版本、运行/开发依赖和工具配置
├── .env                           # 选择 prod 环境
├── .env.prod.example              # 可提交的配置模板
├── src/
│   ├── config.py                  # 项目自定义配置
│   ├── services/
│   │   └── weather.py             # Open-Meteo API 客户端与天气格式化
│   └── plugins/
│       ├── basic.py               # ping / pong
│       ├── weather.py             # /天气 命令
│       ├── ai_chat.py             # /问 DeepSeek 对话
│       └── group_management.py    # 入群欢迎与敏感词撤回
└── tests/
    ├── test_config.py
    └── test_weather.py
```

添加功能时，在 `src/plugins/` 下新建一个模块即可；公共业务逻辑和外部 API 调用建议放进 `src/services/`，不要堆在指令处理函数中。

## 2. 搭建本地 Python 环境

以下命令均在本项目根目录执行。推荐 Python 3.10～3.12；本项目要求 3.10 及以上。

### Windows PowerShell

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install --no-deps --force-reinstall Pillow==10.4.0
Copy-Item .env.prod.example .env.prod
```

如果 PowerShell 阻止激活脚本，可只对当前窗口放开：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pip install --no-deps --force-reinstall Pillow==10.4.0
cp .env.prod.example .env.prod
```

先运行自动化检查：

```bash
pytest
ruff check .
```

## 3. 配置机器人

编辑刚复制出的 `.env.prod`：

```dotenv
HOST=127.0.0.1
PORT=8080
DRIVER=~fastapi
LOG_LEVEL=INFO
COMMAND_START=["/"]
ONEBOT_ACCESS_TOKEN=
ENABLE_SENSITIVE_RECALL=false
SENSITIVE_WORDS=广告
```

- 本机首次测试可以让 `ONEBOT_ACCESS_TOKEN` 和协议端的 token 都为空。
- 更稳妥的做法是生成一个长随机字符串，并在两端填写完全相同的 token。
- 多个敏感词用英文逗号隔开，例如 `广告,加群,返利`。
- 自动撤回默认关闭。机器人被设为群管理员后，将 `ENABLE_SENSITIVE_RECALL` 改为 `true` 再重启。

天气功能使用 [Open-Meteo](https://open-meteo.com/en/docs) 的地理编码和天气接口，无需 API Key。免费开放接口的使用需遵守其许可及非商业使用条款。

## 4. 先启动 NoneBot

```bash
python bot.py
```

正常时日志会出现类似：

```text
Uvicorn running on http://127.0.0.1:8080
```

保持这个终端运行。NoneBot 当前推荐 OneBot V11 协议端使用反向 WebSocket，连接地址是：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

本机完成 NapCat 安装和首次配置后，也可以用项目内脚本同时启动两端：

```powershell
.\scripts\start-all.ps1
```

也可安装 `nb-cli` 后用 `nb run --reload` 获得开发热重载；直接运行 `python bot.py` 不依赖 CLI。参考 [NoneBot 手动创建项目](https://nonebot.dev/docs/tutorial/application) 和 [OneBot V11 连接配置](https://onebot.adapters.nonebot.dev/docs/guide/setup/)。

## 5A. 使用 NapCatQQ（推荐入门）

下面是 Windows 本机的最短路径：

1. 从 [NapCatQQ Releases](https://github.com/NapNeko/NapCatQQ/releases) 下载 `NapCat.Shell.zip`，解压到路径简单、具有写权限的目录。确保已安装最新版 QQ。
2. Windows 11 双击 `launcher.bat`；Windows 10 使用 `launcher-win10.bat`。也可在命令行把机器人 QQ 号作为参数传入，例如 `launcher.bat 123456789`。
3. 按终端或界面提示登录机器人 QQ。建议机器人账号与日常主账号分开。
4. 打开 NapCat WebUI。默认监听端口是 `6099`，本机通常访问 `http://127.0.0.1:6099`；登录地址或凭据以 NapCat 启动日志为准。
5. 进入 **网络配置 → 新建 → WebSocket 客户端**（这里的“客户端”就是反向 WS）。
6. 启用配置，URL 填 `ws://127.0.0.1:8080/onebot/v11/ws`。
7. Token 留空，或填写与 `.env.prod` 中 `ONEBOT_ACCESS_TOKEN` 完全相同的值；保存并启用。
8. 日志看到 WebSocket 连接成功后，把机器人账号拉进测试群。

官方参考：[NapCat Shell 安装](https://napneko.github.io/guide/boot/Shell)、[WebUI 配置](https://napneko.github.io/config/basic)、[接入 NoneBot](https://napneko.github.io/use/integration)。

如果 NapCat 与 NoneBot 不在同一台机器：把 `.env.prod` 的 `HOST` 改为 `0.0.0.0`，NapCat URL 中的 `127.0.0.1` 改为 NoneBot 主机的局域网 IP，并在防火墙仅允许可信来源访问 8080。此时必须配置强 Token；不要把端口直接暴露到公网。

## 5B. 使用 Lagrange.OneBot（备选）

NapCat 和 Lagrange 二选一，不要让同一机器人账号同时由两个协议端登录。

1. 从 [Lagrange.Core Releases](https://github.com/LagrangeDev/Lagrange.Core/releases) 下载与系统匹配的 Lagrange.OneBot 自包含包并解压。非自包含构建需要相应的 .NET Runtime。
2. Windows 运行 `Lagrange.OneBot.exe`；Linux/macOS 赋予执行权限后运行 `./Lagrange.OneBot`。
3. 首次运行会生成同目录下的 `appsettings.json`。先退出程序，编辑该文件。
4. 在 `Implementations` 数组中保留或加入下面的反向 WebSocket 项；不要把下面片段直接当成完整配置文件：

```json
{
  "Type": "ReverseWebSocket",
  "Host": "127.0.0.1",
  "Port": 8080,
  "Suffix": "/onebot/v11/ws",
  "ReconnectInterval": 5000,
  "HeartBeatInterval": 5000,
  "HeartBeatEnable": true,
  "AccessToken": ""
}
```

5. `AccessToken` 与 `.env.prod` 保持一致。
6. 再次启动 Lagrange，使用手机 QQ 扫描生成的 `qr-0.png` 完成登录。建议勾选下次登录无需确认。
7. 等待 Lagrange 日志显示反向 WebSocket 已连接。

完整配置结构和登录说明以 [Lagrange.OneBot 官方配置文档](https://lagrangedev.github.io/Lagrange.Doc/v1/Lagrange.OneBot/Config/) 为准。

## 6. 验证功能

在私聊或测试群依次发送：

```text
ping
/天气 上海
摸摸
搓头 @群友
拍拍 @群友
亲亲 @群友
贴贴 @群友
啃 @群友
抛 @群友
滚 @群友
锤 @群友
吸 @群友
鼓掌 @群友
拍头 @群友
挠头 @群友
抱大腿 @群友
踢球 @群友
```

不指定目标时，头像表情包默认使用发送者自己的头像；也可以使用 `@群友`、QQ 号、`自己`或图片作为目标。然后邀请一个测试账号入群，机器人应发送欢迎消息。

所有头像表情指令不指定目标时都默认使用发送者头像，并且支持不带 `/` 和带 `/` 的形式，例如 `小天使`、`亲亲` 与 `/亲亲`。发送 `头像表情包` 可查看插件支持的完整效果列表。Docker 镜像已经安装 Pillow、fontconfig、FreeType 和 Noto CJK 中文字体，并将下载的 petpet 资源保存在持久化卷中。

要测试撤回：

1. 将机器人设为该群管理员；
2. `.env.prod` 设置 `ENABLE_SENSITIVE_RECALL=true`；
3. 重启机器人；
4. 用其他账号发送包含“广告”的群消息。

机器人需要管理员权限，而且消息必须仍在平台允许撤回的时间窗口内。撤回失败会记录异常，但不会让整个机器人退出。

## 7. 常见问题

- **协议端提示 connection refused**：先确认 `python bot.py` 仍在运行，并核对端口是否为 8080。
- **连接时报 403**：通常是两端 Token 不一致；包括空格在内都必须完全相同，修改后重启两端。
- **连接成功但 `ping` 无回复**：确认登录的是机器人账号、机器人确实在群里，并查看 NoneBot 是否收到 `GroupMessageEvent`。
- **`/天气` 不触发**：确认使用半角 `/`，并保留 `.env.prod` 中的 `COMMAND_START=["/"]`。
- **天气总是失败**：检查运行机器人机器能否访问 `geocoding-api.open-meteo.com` 和 `api.open-meteo.com`。
- **欢迎消息不出现**：确认协议端上报了 `group_increase` 通知事件，并检查是否启用了事件过滤。
- **敏感词不撤回**：确认功能开关已开启、机器人是群管理员，并查看控制台中的撤回错误日志。
- **表情包不生成**：首次启动时插件会检查资源；查看日志是否出现下载错误，并确认服务器能够访问 `raw.githubusercontent.com` 和 `q1.qlogo.cn`。

## 8. 如何继续加功能

### DeepSeek AI 对话

先在 PowerShell 中运行安全配置脚本。输入密钥时屏幕不会显示字符：

```powershell
.\scripts\configure-deepseek.ps1
```

重启机器人后，在 QQ 中发送：

```text
/问 用一句话解释什么是 Python
```

默认模型为 `deepseek-v4-flash`，接口地址为 `https://api.deepseek.com`。API Key 仅保存在被 Git 忽略的 `.env.prod` 中。每位用户有 15 秒调用冷却，问题上限为 1000 字符，单次输出上限可通过 `DEEPSEEK_MAX_OUTPUT_TOKENS` 调整。

### 编写更多插件

插件的最小形式如下：

```python
from nonebot import on_command

hello = on_command("你好", priority=10, block=True)


@hello.handle()
async def handle_hello() -> None:
    await hello.finish("你好呀！")
```

保存为 `src/plugins/hello.py` 后重启机器人即可自动加载。需要数据库、定时任务或复杂 API 时，建议继续保持“插件只负责收发消息，业务逻辑放 `src/services/`”的边界。
