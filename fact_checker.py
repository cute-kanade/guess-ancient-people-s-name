"""
事实判定器

基于 people_db.Person 的结构化字段，对玩家提问生成"确定性事实提示"，
注入 system prompt 供 LLM 参考（按确认的分工方式）。

分工原则：
    - 可结构化判定的维度（朝代/性别/身份/头衔/生卒年）→ 生成提示注入
    - 模糊问题（如"是否被冤杀""性格如何"）→ 交给 LLM 自行判断
    - Person 字段为 None 时 → 跳过该维度，不生成提示，交给 LLM

注意：本模块不直接回答玩家，只生成"供 LLM 参考的事实清单"，
最终输出仍由 LLM 按【回答规则】的五种规范答案给出。
"""

from __future__ import annotations

import re
from typing import Optional

from people_db import Person


# =========================
# 关键词模式
# =========================

#: 朝代提问模式
_DYNASTY_PATTERN = re.compile(r"(是|属于|哪.*朝|.*朝代|.*朝的)(吗)?")
_DYNASTY_KEYWORDS = [
    "先秦", "秦", "汉", "西汉", "东汉", "三国", "魏晋", "晋", "西晋", "东晋",
    "南北朝", "隋", "唐", "五代", "十国", "宋", "北宋", "南宋", "辽", "金",
    "元", "明", "清", "民国", "春秋", "战国",
]

#: 性别提问
_GENDER_PATTERN = re.compile(r"(男|女)(的)?(吗|人)?")

#: 身份/头衔关键词
_IDENTITY_KEYWORDS = [
    "皇帝", "皇帝", "帝王", "文臣", "武将", "将领", "诗人", "词人", "思想家",
    "哲学家", "军事家", "政治家", "文学家", "史学家", "科学家", "医学家",
    "画家", "书法家", "宰相", "丞相", "太傅", "大将", "名将", "太监", "后妃",
    "皇后", "公主", "太子", "王爷", "宗室", "外戚", "宦官", "起义", "领袖",
]

#: 固定并列头衔（高频错误场景）
_TITLE_KEYWORDS = [
    "唐宋八大家", "凌烟阁", "二十四功臣", "麒麟阁", "十一功臣",
    "四大美女", "初唐四杰", "建安七子", "竹林七贤", "扬州八怪",
    "明初", "开国", "功臣",
]


def _detect_dynasty_in_question(question: str) -> Optional[str]:
    """从提问中提取玩家问到的朝代名。"""
    for kw in _DYNASTY_KEYWORDS:
        if kw in question:
            return kw
    return None


def build_fact_hints(person: Person) -> str:
    """为目标人物生成"确定性事实提示"清单。

    根据 Person 的非空字段，列出可由代码判定的事实维度。
    这些提示会注入 system prompt，LLM 在回答相关问题时应直接据此判断。

    Args:
        person: 本局目标人物的结构化记录。

    Returns:
        事实提示文本块；若 person 字段全为空，返回空字符串。
    """
    if not person:
        return ""

    lines: list[str] = []

    if person.dynasty:
        lines.append(f"- 朝代：{person.dynasty}")
    if person.gender:
        lines.append(f"- 性别：{person.gender}")
    if person.identity:
        lines.append(f"- 身份：{'、'.join(person.identity)}")
    if person.titles:
        lines.append(f"- 固定头衔/并列称谓：{'、'.join(person.titles)}（回答相关问题时务必据此判定）")
    if person.aliases:
        lines.append(f"- 别称：{'、'.join(person.aliases)}")
    if person.year_birth is not None or person.year_death is not None:
        b = person.year_birth if person.year_birth is not None else "?"
        d = person.year_death if person.year_death is not None else "?"
        lines.append(f"- 生卒年：{b}–{d}")
    if person.summary:
        lines.append(f"- 简介：{person.summary}")

    if not lines:
        return ""

    return "【目标人物确定性事实（代码层判定，请严格据此回答，勿凭记忆矛盾）】\n" + "\n".join(lines)


def build_fact_check_layer_with_hints(person: Optional[Person]) -> str:
    """构建带人物事实提示的核查层 prompt。

    若 person 为 None 或字段全空，退化为通用事实核查强化层（不含具体事实）。
    """
    from prompts.fact_check import build_fact_check_layer

    base = build_fact_check_layer()
    hints = build_fact_hints(person) if person else ""
    if hints:
        return hints + "\n\n" + base
    return base
