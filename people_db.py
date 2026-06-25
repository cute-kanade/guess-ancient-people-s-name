"""
结构化人物库

把原先只有"人名列表"的 peoples_names.md 升级为结构化数据，
为 fact_checker.py 的确定性事实判定提供数据基础。

数据来源策略（按优先级）：
    1. data/people.json   —— 结构化数据（人工/脚本维护，字段完整）
    2. peoples_names.md   —— 退化为"仅人名"，其余字段为 None

Person 字段缺失时，fact_checker 会跳过该维度的结构化判定，交给 LLM。
后续可用脚本批量生成 JSON 补齐字段。
"""

from __future__ import annotations

import json
import os
import csv
import re
from dataclasses import dataclass, asdict, field
from typing import Optional

#: 人物库默认路径
PEOPLE_MD_PATH = "peoples_names.md"
PEOPLE_JSON_PATH = "data/people.json"

#: "序号. 姓名" 行的解析正则
_NAME_LINE = re.compile(r"^\s*\d+\s*[.、]\s*(.+?)\s*$")


@dataclass
class Person:
    """一个历史人物的结构化记录。

    所有可选字段允许 None，表示"未知"——fact_checker 遇到 None 会跳过该维度判定。
    """
    name: str
    dynasty: Optional[str] = None          # 朝代：唐/宋/明/清...
    gender: Optional[str] = None           # 男/女
    identity: list[str] = field(default_factory=list)  # 皇帝/文臣/诗人/将领/思想家...
    titles: list[str] = field(default_factory=list)    # 唐宋八大家/凌烟阁二十四功臣...
    aliases: list[str] = field(default_factory=list)   # 字/号/别称
    year_birth: Optional[int] = None
    year_death: Optional[int] = None
    summary: Optional[str] = None          # 一句话简介

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_md(path: str) -> list[Person]:
    """从 peoples_names.md 解析人名列表（去除序号前缀）。

    修正原 load_people_names 的隐藏 bug：原版直接 strip 整行，
    会把"1. 黄帝"当作完整人名。本函数只保留序号后的姓名。
    """
    persons: list[Person] = []
    if not os.path.exists(path):
        return persons
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = _NAME_LINE.match(line)
            name = m.group(1) if m else line
            persons.append(Person(name=name))
    return persons


def _parse_csv(
    path: str,
    name_column: str = "简体人名",
    encodings: tuple[str, ...] = ("utf-8", "utf-8-sig", "gbk", "gb2312", "gb18030"),
) -> list[Person]:
    """从 CSV 文件解析人名列表。

    自动尝试多种编码以兼容历史数据文件。
    所有人物 dynasty 固定为 CSV 所属主题（如"明"），由调用方传入覆盖。

    Args:
        path: CSV 文件路径。
        name_column: 人名所在列名，默认 "简体人名"。
        encodings: 依次尝试的编码列表。

    Returns:
        Person 列表（仅含 name）；解析失败返回空列表。
    """
    if not os.path.exists(path):
        return []
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                reader = csv.DictReader(f)
                persons: list[Person] = []
                for row in reader:
                    name = (row.get(name_column) or "").strip()
                    if name:
                        persons.append(Person(name=name))
                if persons:
                    return persons
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            continue
    return []


def _load_json(path: str) -> list[Person]:
    """从 data/people.json 加载结构化人物数据。"""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    persons = []
    for item in data:
        persons.append(Person(
            name=item["name"],
            dynasty=item.get("dynasty"),
            gender=item.get("gender"),
            identity=item.get("identity", []) or [],
            titles=item.get("titles", []) or [],
            aliases=item.get("aliases", []) or [],
            year_birth=item.get("year_birth"),
            year_death=item.get("year_death"),
            summary=item.get("summary"),
        ))
    return persons


def load_people(md_path: str = PEOPLE_MD_PATH, json_path: str = PEOPLE_JSON_PATH) -> list[Person]:
    """加载人物库（合并策略）。

    以 MD 为全集基础（保证人物池不缩小），JSON 的结构化字段
    覆盖到同名 Person 上。MD 中有但 JSON 没有的人，字段全为 None。

    Returns:
        Person 列表（至少含 name 字段），顺序与 MD 一致。
    """
    md_persons = _parse_md(md_path)
    json_persons = _load_json(json_path)
    if not md_persons:
        # 无 MD 时退化为 JSON
        return json_persons if json_persons else []

    if not json_persons:
        return md_persons

    # 以 MD 为基础，JSON 字段覆盖
    json_map = {p.name: p for p in json_persons}
    merged: list[Person] = []
    for p in md_persons:
        jp = json_map.get(p.name)
        if jp:
            merged.append(jp)
        else:
            merged.append(p)
    # JSON 中有但 MD 没有的，追加到末尾（避免漏人）
    md_names = {p.name for p in md_persons}
    for jp in json_persons:
        if jp.name not in md_names:
            merged.append(jp)
    return merged


def load_people_from_csv(
    csv_path: str,
    json_path: str = PEOPLE_JSON_PATH,
    name_column: str = "简体人名",
    default_dynasty: Optional[str] = None,
) -> list[Person]:
    """从 CSV 加载人物库（明朝版等主题变体用）。

    以 CSV 为全集基础，JSON 的结构化字段覆盖到同名 Person 上。
    可选 default_dynasty 给所有 CSV 人物补默认朝代（如"明"）。

    Args:
        csv_path: CSV 文件路径。
        json_path: 结构化数据 JSON 路径（可选覆盖）。
        name_column: CSV 人名列名。
        default_dynasty: 给 CSV 人物补的默认朝代，None 则不补。

    Returns:
        Person 列表。
    """
    csv_persons = _parse_csv(csv_path, name_column=name_column)
    if default_dynasty:
        for p in csv_persons:
            if p.dynasty is None:
                p.dynasty = default_dynasty
    json_persons = _load_json(json_path)
    if not csv_persons:
        return json_persons if json_persons else []
    if not json_persons:
        return csv_persons
    json_map = {p.name: p for p in json_persons}
    merged: list[Person] = []
    csv_names: set[str] = set()
    for p in csv_persons:
        jp = json_map.get(p.name)
        merged.append(jp if jp else p)
        csv_names.add(p.name)
    for jp in json_persons:
        if jp.name not in csv_names:
            merged.append(jp)
    return merged


def load_people_names(md_path: str = PEOPLE_MD_PATH, json_path: str = PEOPLE_JSON_PATH) -> list[str]:
    """仅加载人名列表（向后兼容原 load_people_names 接口）。

    修正了原版"1. 黄帝"前缀 bug。
    """
    return [p.name for p in load_people(md_path, json_path)]


def get_person_by_name(name: str, persons: list[Person]) -> Optional[Person]:
    """按姓名查找 Person（精确匹配，找不到返回 None）。"""
    for p in persons:
        if p.name == name:
            return p
    return None


def save_people_json(persons: list[Person], path: str = PEOPLE_JSON_PATH) -> None:
    """把 Person 列表保存为 JSON（供人工/脚本维护）。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in persons], f, ensure_ascii=False, indent=2)
