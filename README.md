# QQ 机器人：NoneBot2 + OneBot V11

一个可直接运行、方便继续加插件的 QQ 机器人骨架。已实现：

- 群聊或私聊发送 `ping`，回复 `pong`；
- 发送 `/天气 城市名`，通过 Open-Meteo 查询实时天气；
- 新成员进群时自动 `@` 并欢迎；
- 群聊 `早安`、`早上好`、`晚安` 自动问候，内置随机文案，默认无冷却；
- 群聊文字选项、持久化投票和一次性定时提醒；
- 可选的敏感词消息撤回（默认关闭）。
- `/问 内容` 调用 DeepSeek V4.1 Flash 回答问题。
- `摸摸`、`搓头`、`拍拍` 和常用 GIF 指令根据群友头像生成表情包。
- QQ `2448821316` 可管理跨群、跨私聊的全局用户黑名单；被拉黑者的消息不触发机器人回复。

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

### 全局黑名单

只有 QQ `2448821316` 能管理。群聊或私聊发送 `拉黑 123456789`、`解除拉黑 123456789`
（也可用 `放出 123456789`）；群聊还可发送 `拉黑 @群友`、`放出 @群友`。
支持加 `/` 前缀。发送 `黑名单` 或 `黑名单 2` 可分页查看，每页 20 人。
一次只指定一人；终极管理员和机器人自身不能被拉黑。被拉黑用户在**所有群聊和私聊**
发送的新消息都会被静默忽略，不会触发 AI、签到、表情包等插件；解除后立即恢复。
黑名单记录保存在现有 SQLite 数据库中，重启不会丢失，无需新增依赖或配置。

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

### 群聊早安、晚安自动回复

独立插件 `src/plugins/greetings.py` 会随项目自动加载；匹配和冷却逻辑在
`src/services/greetings.py`。沿用 NoneBot2 的群消息事件、`bot.send` 和日志机制，
不新增依赖、不调用大模型或付费 API，也不更改管理员权限。

默认在所有群、全天启用；不受 AI 自主聊天开关、峰价暂停或夜间静默影响。
直接发送 `早安`、`早上好！`、`早晨好 ☀️`、`晚安～🌙`、`晚上好` 即可，
**无需 `/` 前缀，也无需 @**。支持末尾 QQ 表情；每类内置 5 条回复，随机选一条。
`他说了晚安`、`怎么还没说早安`、`早安，今天去哪里` 不会触发。
仅接受完整问候加末尾标点/表情；引用消息、图片消息和 @其他人的问候不处理，
可 @机器人本身。要支持 `早呀` 等说法，请加入对应触发词数组。

在已有 `.env.prod` 中添加或修改以下设置（不要用示例文件覆盖真实密钥配置）：

```dotenv
GREETING_ENABLED=true
# 留空表示所有群；指定多个群时使用英文逗号或空格分隔。
GREETING_GROUP_IDS=977358466
# 可选：填写其他机器人的 QQ 号，避免互相问候。
GREETING_IGNORED_USER_IDS=
GREETING_USER_COOLDOWN_SECONDS=0
GREETING_GROUP_COOLDOWN_SECONDS=0
# 下列数组替换内置列表；不配置或留空则使用内置值。
GREETING_MORNING_WORDS='["早安", "早上好", "早晨好", "早呀"]'
GREETING_NIGHT_WORDS='["晚安", "晚上好", "好梦"]'
GREETING_MORNING_REPLIES='["早安呀，本鲸祝你今天顺顺利利！", "哼，记得吃早餐呀。"]'
GREETING_NIGHT_REPLIES='["晚安，今天辛苦啦。", "本鲸祝你做个好梦。"]'
```

- `GREETING_ENABLED=false` 关闭全局问候；群列表只控制本插件，不改变其他群聊功能。
- 默认两项冷却均为 `0`，连续或并发发送有效问候都会尝试回复，没有用户等待时间、群间隔
  或每日次数限制。发送失败/超时会记日志，不自动重试，不影响后续消息。
- 如果日后需要限频，可手动把上述两项配置改为正整数秒数：用户冷却按“群号 + QQ 号 +
  早安/晚安类别”分别计算，群间隔覆盖同群所有用户和问候类别。启用限制时从成功发送后
  开始计时，同群正在发送时不并发发送第二条。可选冷却状态仅存在本进程内，重启清空。
- 忽略自身、当前 NoneBot 已连接的其他账号、协议明确标记 `is_bot=true` 的发送者及
  `GREETING_IGNORED_USER_IDS`。OneBot v11 不保证识别所有第三方机器人，应手动补充其 QQ 号。
- 已识别问候（包括冷却命中和发送失败）不会再交给 AI 自动回复，避免重复回复/额外费用；
  词云、撤回缓存等普通消息观察功能仍可处理它。不匹配或关闭本插件后沿用原有 AI 行为。
- 文案作为纯文本发送；无需模板变量，中文标点可直接写入 JSON 字符串。修改配置需重启。

本地重启：在正在运行 `bot.py` 的窗口按 `Ctrl+C`，然后在项目根目录执行
`powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1`。不需要退出 QQ 或重启 NapCat，
不要同时启动多个 bot 进程。服务器日后更新源码后，执行
`docker compose up -d --no-deps --build bot`；仅修改 `.env.prod` 时使用
`docker compose up -d --no-deps --force-recreate bot`（`restart` 不会刷新容器环境变量）。

测试建议：

1. 发 `早安！☀️`，应收到一条早安；立刻重复发送 `早安`，仍应回复。
2. 发 `他说了晚安`、`怎么还没说早安`，本问候插件不应回复。
3. 无需等待，同一用户或另一位群友发 `晚安`，应收到晚安回复。
4. 保持两项冷却为 `0`；如历史配置里仍有 `1800`、`60`，需改为 `0` 并重启。
5. 自动化验证：`.\.venv\Scripts\python.exe -m pytest tests/test_greetings.py -q`。

若启用了 AI 主动插话，它仍可能回答第 2 步的普通聊天，这不是问候误判；可先关闭自主回答
以单独验证本功能。日志中的 `Greeting sent` 表示发送成功，`Greeting send failed` 表示失败。

### 群聊表情包收藏与看图

这部分复用现有 NoneBot2、SQLite、Pillow 和 DeepSeek 配置，不需要新增依赖或新的密钥。
看图会消耗已配置的 DeepSeek API 额度；普通收藏和随机发送不调用模型。

```text
收藏表情包 + 图片                 （群管理或终极管理员）
回复一张群图片后发送：收藏表情包   （群管理或终极管理员）
随机表情包
表情包状态
删除表情包 编号                 （群管理或终极管理员）
看图 + 图片／回复图片
/问 这张表情包是什么意思 + 图片
@机器人 + 图片 + 问题              （本群自主回答已开启时）
开启表情包自主发送／关闭表情包自主发送（仅 2448821316，且只影响本群）
```

- 表情包只在上传的群里保存和发送；按内容去重，默认每群最多 200 张，文件位于
  `data/memes/群号/`，元数据在现有 SQLite 中。不会自动收集所有群图片，也不会跨群转发。
- 主动发送默认关闭。开启后，机器人只有在本群原有自主回答决定发言时，才以默认 10% 的
  概率附上本群收藏图；同群两次附图至少间隔 1800 秒。原有峰价、静默及自主回答总开关
  仍然生效。发送图片失败时退回文字，避免吞掉正常回答。
- 在 `.env.prod` 中用 `MEME_LIBRARY_ROOT`、`MEME_MAX_IMAGE_MB`、`MEME_MAX_PER_GROUP`、
  `MEME_PROACTIVE_PERCENT`、`MEME_PROACTIVE_INTERVAL_SECONDS` 调整存储及发送频率；
  可参考 `.env.prod.example`，修改后重启。切勿将真实 API Key 或收藏图提交到 GitHub。
- 只接收 QQ 图片的 HTTPS 链接，支持 JPG、PNG、GIF、WebP；下载不跟随重定向，限制
  文件大小及像素数。看图会把图片内容发送给 DeepSeek；仅在明确使用指令或 @ 机器人时进行。
- 目前没有接入新的 AI 绘图服务。DeepSeek V4.1 Flash 在这里负责理解图片，头像
  表情包的生成仍由已有的 petpet 插件处理。

本机修改代码后需重启 `bot.py` 才会加载新插件和数据库表；云端还未自动更新。

### 群聊选择、投票与提醒

这三项功能来自对 GitHub 同类机器人的功能对照，按本项目的 NoneBot2、SQLite 和权限结构
独立实现，不调用 AI 或付费 API，也不会消耗积分。详细来源、许可证和取舍记录见
`docs/github-comparison-20260922.md`。

```text
帮我选 火锅 | 烧烤 | 面条
随机排序 A | B | C

发起投票 周末吃什么 | 火锅 | 烧烤 | 面条
投票 1 2
投票结果 1
投票列表
结束投票 1

提醒我 10分钟 喝水
提醒我 2026-09-23 08:00 开会
我的提醒
取消提醒 1
```

- 指令均只在群聊生效，支持可选 `/` 前缀；使用 `|` 或 `｜` 分隔“帮我选”的 2～20 个
  选项，投票则为标题加 2～10 个选项。标题和选项作为纯文本发送，不会执行 CQ 码。
- 投票按机器人账号和群隔离；每人一票，再投会修改选择。创建者、群主、群管理员及终极
  管理员 `2448821316` 可以结束投票。默认每群同时最多 5 个进行中投票。
- 提醒只支持本人、纯文字的一次性提醒；相对时间支持秒、分钟、小时、天，至少 5 秒、
  最长 30 天；绝对时间使用 `YYYY-MM-DD HH:MM`，按北京时间解释。
- 提醒和投票保存在现有 SQLite 数据库中，重启后仍在。机器人离线时不会发送；重新上线后
  最多补发 24 小时内的提醒。发送失败或发送结果未知时不会自动重试，以免重复提醒；
  终态记录保留 30 天。提醒检查默认每 5 秒运行一次。
- `我的提醒` 最多显示 15 条。自己可取消自己的提醒；群管理和终极管理员可取消本群提醒。
  已进入发送阶段的提醒无法保证取消。
- 默认上限：每人 10 个待执行提醒、每群 100 个待执行提醒。这些是存储与滥用保护，不是
  聊天冷却或每日次数限制。

相关配置位于 `.env.prod.example`，可通过 `GROUP_CHOICES_ENABLED`、`GROUP_POLLS_ENABLED`、
`GROUP_REMINDERS_ENABLED` 分别关闭；上限和检查间隔也可配置，修改后需要重启机器人。

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

默认模型为 `deepseek-flash`，接口地址为 `https://api.deepseek.com`。API Key 仅保存在被 Git 忽略的 `.env.prod` 中。每位用户有 15 秒调用冷却，问题上限为 1000 字符，普通回答输出上限可通过 `DEEPSEEK_MAX_OUTPUT_TOKENS` 调整。

- `/问 问题` 或 `/ai 问题`：快速问答，不自动搜索互联网。询问天气或热搜时，模型可调用现有的只读查询接口。
- `/深度问 问题`：启用 DeepSeek 深度推理，通常更慢且消耗更多 token；上限由 `DEEPSEEK_DEEP_MAX_OUTPUT_TOKENS` 控制。
- `/联网问 问题`：先查 Brave Search，再用网页摘要回答并附来源；`/深度联网问 问题` 同时启用深度推理。
- 联网搜索需要自行在 [Brave Search API](https://api.search.brave.com/) 申请独立密钥，并把 `BRAVE_SEARCH_API_KEY` 写入 `.env.prod`，再执行 `docker compose up -d --force-recreate bot` 使环境变量生效。未配置时，联网指令会明确提示，普通与深度问答不受影响。联网问题会发送给 Brave；请勿提交密钥或在群里输入隐私信息。机器人仅引用搜索摘要，不保证网页内容正确。
- AI 工具仅允许查询天气和热搜，不提供群管、积分、转账等写操作。已有的 15 秒冷却适用于所有 AI 问答指令。

### 小鲸鱼人格与自主回答

AI 默认使用“小鲸鱼”人格；`设置人格 内容` 只会叠加当前用户的表达偏好，
不会覆盖安全和权限规则。自主回答按群默认关闭，并同时控制“被 @ 自动回答”和
“主动参与讨论”。只有固定终极管理员 QQ `2448821316` 可以操作：

```text
开启自主回答
关闭自主回答
自主回答状态
开启高峰期自主回答
关闭高峰期自主回答
高峰期自主回答状态
```

六条指令都只管理发送指令的群，只有 QQ `2448821316` 可以使用，也接受 `/` 前缀。
开启峰价开关不会替本群开启普通自主回答，也不会影响其他群。

基础人格统一维护在 `src/services/ai_features/personas.py`，`/问`、被 @ 回答和主动插话
共用这套设定。默认傲娇、嘴硬心软，偶尔用开玩笑的吃醋或海洋比喻；遇到严肃、难过或
紧急的问题会收起玩笑，先认真回答。`src/config.py` 中的 `GreetingSettings` 集中维护
早晚安随机文案，原有触发词、全天生效及冷却规则不变。业务指令仍直接返回准确的操作结果。

想微调 AI 语气，可在 `.env.prod` 中加入 `WHALE_PERSONA_EXTRA="说话再俏皮一点"`
（最多 500 字），然后重启机器人；此项只补充表达风格，不覆盖基础行为边界。
群管理员也可用 `修改设定 内容` 调整本群默认表达风格，群友可用 `设置人格 内容`
设置自己的偏好。早晚安文案可用 `GREETING_MORNING_REPLIES`、`GREETING_NIGHT_REPLIES`
填写非空 JSON 字符串数组替换内置列表；示例见上文和 `.env.prod.example`。
`查看人格` 显示风格摘要或已设置的附加偏好，不公开内部完整提示词。

开启后，直接 `@机器人 问题` 即可结合近期群聊获得回答。被 @ 回答和主动发言均不设置
冷却时间或每日次数限制；基础触发率为 100%，0:00～7:00 主动插话静默，模型认为没有
参与价值时不会发送。
同群已有回答正在生成时不重复发起主动插话；明确 `@` 的提问仍可发起回答。
关闭开关会清空该群近期上下文，并阻止关闭前尚未完成的回答继续发送。
未开启的群收到 `@机器人` 时会说明开启方法，避免看起来像掉线。
近期上下文只在进程内存中保留约 20 分钟，不写入聊天记录数据库；数据库仅保存群开关、
相关阈值可通过 `.env.prod` 中的 `AUTO_CHAT_*` 配置调整。

为控制费用，首次启动默认遵循 DeepSeek 官方峰谷价：工作日北京时间 9:00～12:00、
14:00～18:00 为峰价，这些时段暂停 `@` 自动回答和主动插话；其他时段、周末及中国法定节假日
自动恢复，不改变群开关。终极管理员在某群发送 `开启高峰期自主回答` 后，该群若已开启自主回答，
在峰价时也可自动回复，会按峰价消耗额度；发送 `关闭高峰期自主回答` 即恢复峰价暂停。
每群选择分别保存在 SQLite 中，重启后仍生效。`高峰期自主回答状态` 可查看本群开关和当前计价。
如果尚未通过群指令选择，`DEEPSEEK_SUSPEND_AUTOCHAT_DURING_PEAK` 决定初始策略；
执行指令后数据库设置优先。`/问`、`/深度问` 等明确调用的指令始终可使用。
计价时段依据 [DeepSeek 官方说明](https://api-docs.deepseek.com/quick_start/pricing/)。
内置假期表覆盖 2026 年，下一年公布后需更新 `src/services/deepseek_pricing.py`；
未知年份按周一至周五的峰时保守暂停，不推测假期。

### 运行健康检查

启动时检查所有本地插件是否成功加载，并初始化数据库，避免插件加载失败后部分指令无响应。
管理员发送 `/status` 可同时查看 QQ 实际在线状态和数据库状态；Docker 每 30 秒检查一次，
只查询 OneBot 状态，不调用大模型或向群里发送消息。服务日志统一采用北京时间。

```bash
docker compose ps
docker compose exec -T bot python -m src.services.healthcheck
docker compose logs --since=10m bot
```

`healthy` 表示 HTTP 服务、数据库和 QQ 在线状态均正常；断开 OneBot 或 QQ 离线时显示
`unhealthy`。健康检查只报告状态，不会反复重启 NapCat；QQ 被要求扫码时仍需重新登录。
`/healthz` 只返回聚合状态，不返回密钥或聊天内容，机器人 HTTP 端口仍只在 Docker 内网使用。
升级前应同时备份源码和 SQLite 数据库；复制数据库请使用 SQLite 的 `backup` 接口，避免漏掉 WAL 数据。

### 本次可靠性修复

- 转账和红包金额严格要求正整数；负数、小数和额外文本会被拒绝。
- 核销、退款及抢指定红包遇到重复短编号时要求提供完整编号，避免处理错对象。
- 表情包渲染锁在事件被忽略或取消时也会释放；回复图片指令识别 OneBot 已解析的引用。
- 图片下载执行流式大小上限；网页截图在离线浏览器中渲染，资源由限定公网地址的下载器提供。
- `/今日词云` 按北京时间当天零点统计，`/本周词云` 从本周一零点开始；`生成词云 N` 仍统计最近 N 天。

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
和 `wordcloud_messages`。

“消息伪造”未实现。该功能容易被用于冒充真实聊天、造谣或欺骗，不属于本项目提供的
安全功能范围。

### 常用指令兼容与管理扩展

QQ `2448821316` 默认属于 `BOT_ADMIN_IDS`，因此在所有群聊中拥有机器人终极管理员
权限；修改环境变量时应保留该号码。

```text
/help 或 完整指令
/ping
/status                         # 仅机器人终极管理员
/echo 文本                      # 仅机器人终极管理员
/reload 或 /restart             # 退出进程，由 Docker 自动重新拉起
/stop 或 /start                 # 开启/关闭维护模式

/ban @群友 分钟
/unban @群友
/kick @群友 [理由]
/set_title @群友 头衔
/ban_all 或 /unban_all
/withdraw                       # 也可回复机器人消息后使用

/记忆清除
/修改设定 本群默认人格          # 群管理权限
/API预设                        # 仅显示当前配置，不输出密钥
/缩写 yyds                      # 公开 nbnhhsh 服务，无需 Key
/calc 1+2*3                     # 本地安全计算
/roll 1-100
/排行榜
/今日词云 或 /本周词云
/表情列表
/表情 模板名 [文字/@群友]
/原神10抽 或 /方舟十连 或 /fgo一井
```

群管、订阅和撤回记录的管理操作允许群主、群管理员或 `BOT_ADMIN_IDS` 中的终极管理员
执行。机器人账号本身仍需在群内拥有足够权限，QQ 服务端才会执行禁言、踢人、头衔和
撤回操作。

撤回记录默认关闭。发送 `/开启撤回记录` 后，只在内存中缓存机器人此后看到的纯文本，
机器人重启即清空；`/查看撤回` 仅管理者可用。发送 `/关闭撤回记录` 会立即清空缓存。

RSS 订阅无需 API Key：

```text
/rss add https://example.com/feed.xml
/rss del 订阅编号或链接
/rss list
```

订阅地址会经过公网地址校验，拒绝访问本机、内网、保留地址及非常用端口。机器人只推送
订阅之后出现的新文章。

B站动态和开播订阅：

```text
/bili_sub 主播UID
/bili_unsub 主播UID
/bili_list
```

B站接口可能限制未登录请求；遇到风控时，需要把已登录测试账号 Cookie 中的 `SESSDATA`
仅写入 `.env.prod` 的 `BILIBILI_SESSDATA`，不得提交 Git 或发到群聊。轮询间隔可通过
`RSS_POLL_SECONDS` 和 `BILI_POLL_SECONDS` 调整。订阅和撤回开关数据存入现有 SQLite，
数据库架构版本为 7。

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
