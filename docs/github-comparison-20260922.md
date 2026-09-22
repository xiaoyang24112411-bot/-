# GitHub 同类项目比较与功能整合记录

调研日期：2026-09-22。资料来自下列项目的 GitHub 官方仓库、README、LICENSE，
提交号使用调研时 `git ls-remote <repo> HEAD` 的结果固定。仓库存在、README 宣称支持某项
功能，不等于该项目已在本机器人的运行环境中通过测试。

## 本项目的对照基线

当前项目使用 Python + NoneBot2 + OneBot v11，协议端为 NapCat；通过
`src/plugins/` 注册消息处理模块，业务逻辑放在 `src/services/`，配置沿用
`.env.prod`，已使用 SQLite 存储积分、商店及其他业务数据。

调研前已有签到积分、转账红包、商店订单、群管、早晚安、天气、表情包、
骰子与小游戏、运势塔罗、随机老婆、AI 对话、词云、RSS/B站订阅等功能。
这些不应因为其他项目也有而重复安装。数字骰子不等同于从任意文字选项中选择；
RSS/B站更新推送也不等同于用户设置的定时提醒。

## 确认的同类项目与候选功能

| 项目与官方来源 | 已核实的许可证 | 与本项目的重复部分 | 可补充部分和整合判断 |
| --- | --- | --- | --- |
| [绪山真寻 Bot](https://github.com/zhenxun-org/zhenxun_bot) | [AGPL-3.0](https://github.com/zhenxun-org/zhenxun_bot/blob/33d6ea1335e496d41abf6958dc00b0541ef10bcd/LICENSE) | 同为 NoneBot2/OneBot；签到、金币商店、群管、帮助、早晚安、运行状态等 | WebUI、插件级群开关、功能调用统计、自动备份值得后续评估；涉及框架、数据模型及权限结构，不整包替换或复制 |
| [LittlePaimon](https://github.com/CMHopeSunshine/LittlePaimon) | [AGPL-3.0](https://github.com/CMHopeSunshine/LittlePaimon/blob/3b2e89fa66bd3a6254afae38538403844c83e02a/LICENSE) | 同为 NoneBot2/OneBot；群聊功能、群管、原神主题娱乐部分重合 | 真实游戏 UID 面板、攻略、树脂提醒不同于本项目的娱乐抽卡；需要游戏服务适配及可能的用户 Cookie，本轮不接入 |
| [nonebot-plugin-remind](https://github.com/H-Elden/nonebot-plugin-remind) | [MIT](https://github.com/H-Elden/nonebot-plugin-remind/blob/0d626740ca821c04e4ea6744e647f72349854298/LICENSE)，H-Elden，2025 | 本项目已有定期订阅推送，但没有对应的个人定时提醒管理 | 参考“创建提醒、列表、取消”交互；本地独立实现明确的时间格式和持久化，不引入其 jionlp 或可选 GLM 解析链路 |
| [nonebot-plugin-make-choice](https://github.com/SherkeyXD/nonebot-plugin-make-choice) | [MIT](https://github.com/SherkeyXD/nonebot-plugin-make-choice/blob/95896613aedc4c28c116ee3286a455aa59fe09df/LICENSE)，SherkeyXD，2023 | 本项目已有数字骰子，但没有任意文字选项选择 | 参考帮用户选择的功能；改为显式“帮我选”命令、多选项分隔及严格校验，避免宽泛匹配普通聊天 |
| [koishi-plugin-realtime-vote](https://github.com/KIRA2ZERO/koishi-plugin-realtime-vote) | [MIT](https://github.com/KIRA2ZERO/koishi-plugin-realtime-vote/blob/817ee30c0312ecdd82d0785f3ae49f1a750101ad/LICENSE)，KIRA2ZERO，2023 | 本项目调研前无群投票模块；该项目使用 Koishi/TypeScript，不能直接作为 Python 插件加载 | 参考“发起、投票、查看结果、创始人管理”；在 NoneBot2 内独立实现群隔离、权限和并发防重票，不复制其数据库计数逻辑 |

### 固定版本记录

| 仓库 | 调研时 HEAD |
| --- | --- |
| `zhenxun-org/zhenxun_bot` | `33d6ea1335e496d41abf6958dc00b0541ef10bcd` |
| `CMHopeSunshine/LittlePaimon` | `3b2e89fa66bd3a6254afae38538403844c83e02a` |
| `H-Elden/nonebot-plugin-remind` | `0d626740ca821c04e4ea6744e647f72349854298` |
| `SherkeyXD/nonebot-plugin-make-choice` | `95896613aedc4c28c116ee3286a455aa59fe09df` |
| `KIRA2ZERO/koishi-plugin-realtime-vote` | `817ee30c0312ecdd82d0785f3ae49f1a750101ad` |

## 本轮选择范围

优先补充以下三项没有重复、无需额外付费 API 的能力：

1. 定时提醒：明确时间解析、列出和取消本人提醒、SQLite 持久化。
2. 帮我选：显式命令选择文字选项，使用本地随机数，不调用 AI。
3. 群投票：显式创建/参与/查询/结束，群与群隔离，事务和唯一约束避免重复票。

这些是基于功能需求的本地独立实现，不是安装或整体移植上述第三方插件。
具体命令、配置和验证结果以本项目 README 及实际交付记录为准。

本轮最终已按上述范围落地“帮我选／随机排序、群投票、一次性群提醒”三个独立模块；
没有安装或运行第三方仓库代码，没有加入新依赖、密钥或付费接口。整合后的全项目自动化测试、
代码检查和插件加载检查均通过，生产部署仍以当次发布记录和健康检查结果为准。

## 为什么不直接复制整套项目

- 真寻和小派蒙采用 AGPL-3.0，且自带配置、数据库、权限和插件管理体系。
  直接复制会引入许可证合规工作与结构冲突；本轮仅作为功能对照来源。
- 三个小插件的 MIT 许可证允许在遵守条款的前提下复用源码；若后续复制了源码或实质部分，
  应保留对应版权声明和完整许可文本。本轮不复制第三方源码、回复文案、图片或其他素材。
- 投票来源的数据库结构没有群号字段，票数采用读后写方式更新；本项目必须另行保证
  群隔离、原子操作及一人一票，而不是照搬。
- 提醒来源支持复杂自然语言、富文本和可选大模型兜底；本轮不接入这些链路，
  避免增加模型费用、账号密钥或不必要依赖，也不承诺具备上游全部能力。
- 不替换现有管理员 `2448821316` 的全局权限，不修改积分余额、聊天模型设置或问候冷却偏好。

## 排除记录

- [Old-Second/nonebot-plugin-vote](https://github.com/Old-Second/nonebot-plugin-vote)
  虽然仓库名含 vote，调研时内容只是插件模板 README 和许可证，未发现投票实现，
  因此不把它当作已可用插件或功能移植来源。
- 未确认许可证的仓库不复制源码；依赖新账号、Cookie、外部付费服务的功能暂不整合。
- 调研时没有运行第三方仓库代码、安装其依赖或使用其部署脚本。
