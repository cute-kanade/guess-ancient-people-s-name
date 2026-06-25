"""fact_checker.py 与 people_db.py 测试。"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from people_db import Person, load_people_names, get_person_by_name, load_people, _parse_md
from fact_checker import build_fact_hints, build_fact_check_layer_with_hints


# ---------- people_db ----------

def test_parse_md_strips_index_prefix():
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("1. 黄帝\n2. 炎帝\n\n3. 尧\n")
        path = f.name
    persons = _parse_md(path)
    os.unlink(path)
    assert [p.name for p in persons] == ["黄帝", "炎帝", "尧"]
    assert all(p.dynasty is None for p in persons)


def test_load_people_names_non_empty():
    names = load_people_names()
    assert len(names) > 0
    assert isinstance(names[0], str)


def test_get_person_by_name_found():
    persons = load_people()
    p = get_person_by_name("苏轼", persons)
    assert p is not None
    assert p.dynasty == "宋"
    assert "唐宋八大家" in p.titles


def test_get_person_by_name_missing_returns_none():
    persons = load_people()
    assert get_person_by_name("不存在的某某某", persons) is None


# ---------- fact_checker ----------

def test_build_fact_hints_full():
    p = Person(
        name="苏轼", dynasty="宋", gender="男",
        identity=["文学家", "词人"], titles=["唐宋八大家"],
        aliases=["号东坡居士"], year_birth=1037, year_death=1101,
        summary="北宋文学家",
    )
    hints = build_fact_hints(p)
    assert "朝代：宋" in hints
    assert "性别：男" in hints
    assert "唐宋八大家" in hints
    assert "1037–1101" in hints


def test_build_fact_hints_empty_person():
    p = Person(name="某古人")
    assert build_fact_hints(p) == ""


def test_build_fact_hints_none_person():
    assert build_fact_hints(None) == ""


def test_build_fact_check_layer_with_hints_merges():
    p = Person(name="苏轼", dynasty="宋", gender="男")
    layer = build_fact_check_layer_with_hints(p)
    assert "朝代：宋" in layer
    assert "事实核查强化规则" in layer


def test_build_fact_check_layer_with_hints_none_falls_back():
    layer = build_fact_check_layer_with_hints(None)
    assert "事实核查强化规则" in layer
    # 不应包含具体结构化数据行（如"朝代：宋"）
    assert "朝代：" not in layer
    assert "性别：" not in layer
