"""prompts 拼装快照测试，防止改 prompt 时回退。"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from prompts import (
    build_system_prompt,
    build_persona,
    build_rules,
    build_state,
    build_hint_strategy,
    build_output_format,
    build_fact_check_layer,
    build_recheck_prompt,
    build_batch_recheck_prompt,
)


def test_build_persona_contains_role():
    p = build_persona("历史")
    assert "海龟汤" in p
    assert "历史" in p


def test_build_rules_has_five_answers():
    r = build_rules()
    for ans in ["是。", "否。", "或许是。", "或许不是。", "无可奉告"]:
        assert ans in r


def test_build_state_contains_secret():
    s = build_state("李白", 3, "blocked")
    assert "李白" in s
    assert "blocked" in s
    assert "3" in s


def test_build_hint_strategy_blocked():
    h = build_hint_strategy("blocked")
    assert "blocked" in h
    assert "尚不足" in h


def test_build_hint_strategy_enabled():
    h = build_hint_strategy("enabled")
    assert "enabled" in h
    assert "绝不重复" in h or "不重复" in h


def test_build_hint_strategy_invalid_raises():
    import pytest
    with pytest.raises(ValueError):
        build_hint_strategy("invalid")


def test_build_output_format_contains_target():
    o = build_output_format("李白")
    assert "李白" in o
    assert "猜中" in o
    assert "投降" in o


def test_build_fact_check_layer_has_warnings():
    f = build_fact_check_layer()
    assert "事实核查强化规则" in f
    assert "唐宋八大家" in f or "并列头衔" in f or "固定" in f
    assert "宁可保守" in f


def test_build_system_prompt_assembles_all_layers():
    sp = build_system_prompt("李白", 5, "blocked", theme="历史", enable_fact_check=True)
    assert "李白" in sp
    assert "海龟汤" in sp
    assert "事实核查强化规则" in sp
    assert "回答规则" in sp
    assert "提示规则" in sp


def test_build_system_prompt_fact_check_toggle():
    with_fc = build_system_prompt("李白", 5, "blocked", enable_fact_check=True)
    without_fc = build_system_prompt("李白", 5, "blocked", enable_fact_check=False)
    assert "事实核查强化规则" in with_fc
    assert "事实核查强化规则" not in without_fc


def test_build_recheck_prompt_single():
    p = build_recheck_prompt("李白", "是男的吗", "否。")
    assert "李白" in p
    assert "是男的吗" in p
    assert "否。" in p
    assert "二次核查结果" in p


def test_build_batch_recheck_prompt_lists_all():
    pairs = [(1, "是男的吗", "是。"), (2, "唐朝的吗", "否。"), (3, "文臣吗", "或许是。")]
    p = build_batch_recheck_prompt("李白", pairs)
    assert "李白" in p
    assert "第1条" in p
    assert "第3条" in p
    assert "整体更正摘要" in p
    assert "3" in p  # 条数
