"""Small built-in major-arcana tarot deck and interpretations."""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class TarotCard:
    name: str
    upright: str
    reversed: str


@dataclass(frozen=True)
class TarotResult:
    card_name: str
    orientation: str
    interpretation: str


CARDS = (
    TarotCard("愚者", "新的开始、自由与勇气", "冲动、冒险过度与准备不足"),
    TarotCard("魔术师", "行动力、创造力与掌控机会", "犹豫、技巧未发挥或被误导"),
    TarotCard("女祭司", "直觉、沉静与隐藏的答案", "忽略直觉、信息不明或情绪封闭"),
    TarotCard("皇后", "丰盛、关怀与创造", "依赖、过度付出或缺乏照顾"),
    TarotCard("皇帝", "秩序、责任与稳定领导", "固执、控制欲或规则僵化"),
    TarotCard("教皇", "传统、学习与可靠建议", "打破惯例、质疑权威或另寻道路"),
    TarotCard("恋人", "真诚关系、选择与价值一致", "关系失衡、犹豫或价值冲突"),
    TarotCard("战车", "意志坚定、推进与胜利", "方向混乱、急躁或失去控制"),
    TarotCard("力量", "温柔的勇气、自信与耐心", "自我怀疑、焦虑或力量失衡"),
    TarotCard("隐者", "独处思考、寻找智慧与方向", "封闭、孤立或逃避现实"),
    TarotCard("命运之轮", "转机、周期变化与好运", "计划受阻、重复旧问题或抗拒变化"),
    TarotCard("正义", "公平、责任与理性决定", "偏见、逃避责任或结果失衡"),
    TarotCard("倒吊人", "换个角度、暂停与领悟", "无谓牺牲、拖延或拒绝改变"),
    TarotCard("死神", "结束旧阶段、转化与重生", "留恋过去、停滞或害怕结束"),
    TarotCard("节制", "平衡、疗愈与循序渐进", "失衡、过度或缺少耐心"),
    TarotCard("恶魔", "看见欲望、束缚与执念", "挣脱束缚、恢复清醒与自主"),
    TarotCard("高塔", "真相显现、结构重建与突然改变", "抗拒变化、危机延后或内在震荡"),
    TarotCard("星星", "希望、灵感与重新相信未来", "失望、信心不足或目标模糊"),
    TarotCard("月亮", "潜意识、想象与尚未明朗", "误会消散、真相渐明或情绪释放"),
    TarotCard("太阳", "快乐、成功与清晰活力", "短暂低落、进展延迟或过度乐观"),
    TarotCard("审判", "觉醒、复盘与重要决定", "自我否定、逃避总结或迟迟不决"),
    TarotCard("世界", "完成、整合与阶段性圆满", "尚差一步、计划未收尾或缺少闭环"),
)


def draw_tarot(rng: random.Random | None = None) -> TarotResult:
    generator = rng or random.SystemRandom()
    card = generator.choice(CARDS)
    upright = bool(generator.randint(0, 1))
    return TarotResult(
        card_name=card.name,
        orientation="正位" if upright else "逆位",
        interpretation=card.upright if upright else card.reversed,
    )
