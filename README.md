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

### 签到与积分系统

积分按群隔离并保存在 SQLite 数据库中。Docker 部署使用独立的 `economy-data`
持久化卷，重建机器人容器不会清空积分。

普通成员指令（均支持带 `/` 或不带 `/`）：

```text
签到
积分
我的积分
转账 @群友 100
发红包 100 5
抢红包 [红包编号]
打劫
商店
兑换 商品编号 [数量]
```

群主或全局机器人管理员可用的商店管理指令：

```text
添加商品 名称|价格|库存|说明
修改商品 编号|名称|价格|库存|说明
上架商品 商品编号
下架商品 商品编号
核销订单 订单号
退款订单 订单号
```

库存填写 `无限`、`不限` 或 `-` 表示无限库存。签到奖励、打劫冷却和红包有效期可在
`.env.prod` 中通过 `CHECKIN_REWARD_MIN`、`CHECKIN_REWARD_MAX`、
`ROBBERY_COOLDOWN_SECONDS` 和 `RED_PACKET_TTL_SECONDS` 调整。全局管理员通过
`BOT_ADMIN_IDS` 配置，支持用英文逗号、中文逗号或空格填写多个 QQ 号；默认包含
`2448821316`，在所有群聊中生效。本功能不需要外部 API Key。

### 每日随机老婆

发送 `今日老婆` 或 `/今日老婆`，机器人会从当前群成员中抽取一人，发送对方的 QQ
头像并 @ 对方。同一发送者在同一个群里当天的结果固定，次日 0 点刷新。发送
`强娶 @群友` 可以每天一次把当天结果改成指定群友，不能强娶自己或机器人。结果保存
在 SQLite 的 `daily_spouses` 和 `daily_spouse_forces` 表中，机器人重启后不会改变。
头像发送失败时会自动退回纯文字结果。本功能不需要额外依赖或 API Key。

### 占卜与娱乐

以下指令均支持带 `/` 或不带 `/`，使用内置数据，不需要额外 API Key：

```text
每日运势
今日运势
魔法占卜
塔罗占卜
答案之书 [你的问题]
舔狗日记
```

每日运势按群、用户和日期固定，结果保存在 SQLite 的 `daily_fortunes` 表中，次日
0 点刷新。魔法占卜从内置的 22 张塔罗大阿卡纳中抽取一张，并随机解释正位或逆位。
答案之书和舔狗日记使用本地文案库，不进行外部网络请求。

### 批次三小游戏

```text
掷骰子                 # 默认 1d6
掷骰子 3d20            # 最多 20 个、每个最多 1000 面
五子棋                 # 创建对局并执黑
加入五子棋             # 第二位玩家加入并执白
落子 H8                # 棋盘坐标 A1～O15
五子棋棋盘
结束五子棋
人生重开
人生模拟
牛牛修仙
修仙状态
修炼
突破
俄罗斯轮盘 10          # 使用签到积分，最低 5 积分
游戏王查卡 青眼白龙
游戏王查卡 Dark Magician
游戏王查卡 89631139
```

五子棋对局保存在 `gomoku_games` 表中，每个群同时只能有一局，机器人重启后仍可继续。
牛牛修仙使用 `cultivation_profiles` 和 `cultivation_actions` 保存境界、修为、灵石和操作
记录。俄罗斯轮盘会原子写入现有积分账本与 `roulette_records`，默认冷却 60 秒，安全时
获得投入积分的 20%，击发时损失投入积分；仅使用机器人虚拟积分。

游戏王查卡使用免费的 YGOPRODeck API v7，不需要 API Key。接口主要支持英文卡名和
卡片密码，项目额外内置了一组常见中文卡名别名；查询结果缓存在 `yugioh_card_cache`
表中 7 天，以减少重复请求并遵守接口限流。当前只回复文字卡片资料，不热链卡图。

### 批次四媒体工具

```text
图片分类
随机图片 [分类]
视频分类
随机视频 [分类]
图转字符 + 图片              # 也可回复图片后发送
网页截图 https://example.com
视频解析 URL                  # 仅限有权下载的内容
图集解析 URL                  # 最多返回 9 张，平台支持取决于 yt-dlp
取CQ码                        # 回复目标消息后发送
图片来源 + 图片               # 需要 SAUCENAO_API_KEY
```

本地素材放在 `data/media/images/分类名` 和 `data/media/videos/分类名`。Docker 中使用
独立的 `media-data` 持久化卷，并同时挂载给机器人和 NapCat。网页截图使用 Playwright
Chromium；本地 Windows 优先复用 Microsoft Edge。视频/图集解析使用 yt-dlp，平台规则
变化或内容需要登录时可能需要更新 yt-dlp 或提供 Cookie。本功能只应用于用户拥有权利
下载或处理的内容。

图片来源查询使用 SauceNAO。需要在 `.env.prod` 设置 `SAUCENAO_API_KEY`；查询图片会
上传给 SauceNAO 处理，未配置 Key 时插件只返回配置提示。随机媒体、字符画、CQ 码和
网页截图不需要 API Key。

### 批次五信息查询

```text
今日油价 北京
每日油价 广东深圳
每天60秒                     # 默认返回今日简报图片
每天60秒 文字                # 返回文字版
热搜                         # 默认微博热搜
热搜 微博
热搜 抖音
热搜 知乎
热搜 头条
热搜 B站
热搜 小红书
热搜平台
影视搜索 流浪地球           # 需要 TMDB_ACCESS_TOKEN
漫画搜索 葬送的芙莉莲       # MangaDex 公开 API，无需密钥
高质量文案
高质量文案 治愈             # 治愈/热血/成长/古风
```

油价、60 秒简报和热搜使用开源的 60s API，默认公共地址为
`https://60s.viki.moe/v2`。公共实例有调用额度，服务器长期运行时建议自行部署该服务，
再通过 `INFO_60S_API_BASE_URL` 切换地址。油价是第三方汇总信息，仅供参考，以当地
加油站公示为准。

影视搜索只查询 TMDB 的电影、电视剧元数据和官方详情入口，不提供盗版播放链接。请在
TMDB 账户的 API 设置页申请 API Read Access Token，并只写入本机 `.env.prod` 的
`TMDB_ACCESS_TOKEN`。漫画搜索只返回 MangaDex 的检索结果和详情入口，不抓取番茄漫画
等平台内容；使用 MangaDex 数据时保留服务名称以满足其署名要求。高质量文案为项目内置
的短句库，不需要 API Key。

### 批次六 AI、音乐、语音与词云

```text
/问 你的问题                    # DeepSeek，多轮上下文保留到机器人重启
/清空对话                       # 清除自己的临时对话上下文
设置人格 用简洁的侦探口吻回答
查看人格
重置人格

点歌 稻香 周杰伦                # 返回 Apple/iTunes 官方曲目页
随机唱鸭                         # 也可发送“唱鸭”

语音角色
语音 大家晚上好                  # 默认“晓晓”音色
语音 云希 大家晚上好

开启词云记录 [保留天数]          # 仅群主/群管理员/机器人管理员
关闭词云记录
词云状态
生成词云 [统计天数]              # 默认统计最近 7 天
清空词云记录                     # 仅管理者
```

AI 人格按群和用户保存在 `ai_personas`；最近四轮问答仅保存在内存，机器人重启即清除。
人格只是表达风格偏好，不改变模型的事实可靠性要求。DeepSeek 沿用已有
`DEEPSEEK_API_KEY`，本批次没有新增大模型密钥。

点歌使用 Apple 的 iTunes Search API，只返回官方曲目页，不缓存或转发试听音频。随机
唱鸭使用 60s API 的公开 `changya` 数据，并在官方主域名不可达时尝试配置的公共实例；
下载地址仅允许唱鸭音频 CDN。语音合成使用 Edge 在线语音，无需 Key，支持晓晓、云希、
晓伊和云扬；合成文字会发送给微软在线服务，因此不要提交隐私或敏感文本。

词云记录默认关闭。开启时只保存群消息的纯文本，不保存图片、语音、文件或 QQ 原始消息
对象；默认保留 30 天，范围 1～90 天。成员可查看状态和生成词云，管理者可停止收集或
清空本群数据。机器人无法读取开启之前的历史聊天。数据表为 `wordcloud_group_settings`
和 `wordcloud_messages`，数据库架构版本为 6。

“消息伪造”未实现。该功能容易被用于冒充真实聊天、造谣或欺骗，不属于本项目提供的
安全功能范围。

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
