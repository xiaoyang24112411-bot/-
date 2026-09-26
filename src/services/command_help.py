"""Category and keyword navigation over the existing command menu."""

import re
from dataclasses import dataclass

MAX_QUERY_LENGTH = 64
SEARCH_RESULT_LIMIT = 12

# These are category names only; command definitions stay in HELP_TEXT.
CATEGORY_ALIASES = {
    "ai": "AI 对话",
    "问答": "AI 对话",
    "对话": "AI 对话",
    "群管理": "群管",
    "实用": "群聊实用",
    "投票": "群聊实用",
    "提醒": "群聊实用",
    "积分": "积分与商店",
    "商店": "积分与商店",
    "娱乐": "娱乐与群友互动",
    "老婆": "娱乐与群友互动",
    "表情": "头像表情包",
    "表情包": "头像表情包",
    "头像": "头像表情包",
    "游戏": "群聊游戏",
    "媒体": "媒体与信息",
    "信息": "媒体与信息",
    "语音": "语音与群聊统计",
    "词云": "语音与群聊统计",
    "订阅": "订阅与撤回",
    "撤回": "订阅与撤回",
    "主人": "机器人终极管理员",
    "终极管理员": "机器人终极管理员",
}


@dataclass(frozen=True)
class HelpSection:
    title: str
    lines: tuple[str, ...]

    @property
    def category(self) -> str:
        return self.title.split("｜", 1)[0]

    def render(self) -> str:
        return f"【{self.title}】\n" + "\n".join(self.lines)


def _normalize(text: str) -> str:
    return "".join(text.casefold().split())


def parse_help_sections(help_text: str) -> tuple[HelpSection, ...]:
    sections: list[HelpSection] = []
    title = ""
    lines: list[str] = []
    for raw_line in help_text.splitlines():
        line = raw_line.strip()
        heading = re.fullmatch(r"【([^】]+)】", line)
        if heading:
            if title:
                sections.append(HelpSection(title, tuple(lines)))
            title = heading[1]
            lines = []
        elif title and line:
            lines.append(line)
    if title:
        sections.append(HelpSection(title, tuple(lines)))
    return tuple(sections)


def category_index(help_text: str) -> str:
    names = "、".join(section.category for section in parse_help_sections(help_text))
    return (
        f"帮助分类：{names}\n"
        "发送 /help 表情、/help 积分、/help AI 等查看分类。\n"
        "查找指令：/指令搜索 关键词（例如 /指令搜索 老婆）。\n"
        "完整菜单：/help 或 完整指令。"
    )


def search_commands(help_text: str, keyword: str) -> str:
    keyword = keyword.strip()
    if not keyword:
        return "用法：/指令搜索 关键词\n例如：/指令搜索 老婆、/指令搜索 头像"
    if len(keyword) > MAX_QUERY_LENGTH:
        return f"搜索词请控制在 {MAX_QUERY_LENGTH} 个字符以内。"
    query = _normalize(keyword)
    matches = [
        (section.category, line)
        for section in parse_help_sections(help_text)
        for line in section.lines
        if query in _normalize(line) or query in _normalize(section.category)
    ]
    if not matches:
        return f"没有找到“{keyword}”相关指令。\n发送 /help 分类 查看可用分类。"
    rows = [f"指令搜索“{keyword}”：共 {len(matches)} 条"]
    rows.extend(f"【{category}】{line}" for category, line in matches[:SEARCH_RESULT_LIMIT])
    if len(matches) > SEARCH_RESULT_LIMIT:
        rows.append(f"仅显示前 {SEARCH_RESULT_LIMIT} 条，请换更具体的关键词。")
    return "\n".join(rows)


def render_help(help_text: str, category: str = "") -> str:
    category = category.strip()
    if not category or category in {"全部", "完整", "完整指令"}:
        return help_text
    if len(category) > MAX_QUERY_LENGTH:
        return f"分类名请控制在 {MAX_QUERY_LENGTH} 个字符以内。\n发送 /help 分类 查看分类。"
    key = _normalize(category)
    if key in {"分类", "目录", "菜单"}:
        return category_index(help_text)
    target = _normalize(CATEGORY_ALIASES.get(key, category))
    for section in parse_help_sections(help_text):
        if target in {_normalize(section.title), _normalize(section.category)}:
            return section.render()
    return (
        f"没有“{category}”这个帮助分类。\n"
        f"{category_index(help_text)}\n\n"
        f"{search_commands(help_text, category)}"
    )
