"""game_state.py 纯函数与状态机测试。"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from game_state import (
    GameState,
    GamePhase,
    HINT_THRESHOLD,
    compute_hint_mode,
    is_likely_surrender,
    is_likely_hint_request,
    is_replay_request,
    is_doubt_request,
    collect_fact_qa_pairs,
    _is_canonical_answer,
)


# ---------- hint_mode / compute_hint_mode ----------

def test_hint_mode_blocked_below_threshold():
    gs = GameState(target_answer="李白", dialogue_count=0)
    assert gs.hint_mode == "blocked"
    gs.dialogue_count = HINT_THRESHOLD - 1
    assert gs.hint_mode == "blocked"
    assert gs.hint_available is False


def test_hint_mode_enabled_at_threshold():
    gs = GameState(target_answer="李白", dialogue_count=HINT_THRESHOLD)
    assert gs.hint_mode == "enabled"
    assert gs.hint_available is True


def test_compute_hint_mode_pure_function():
    assert compute_hint_mode(0) == "blocked"
    assert compute_hint_mode(HINT_THRESHOLD) == "enabled"
    assert compute_hint_mode(999) == "enabled"


# ---------- reset / phase ----------

def test_reset_clears_state():
    gs = GameState(target_answer="李白", dialogue_count=10)
    gs.mark_surrendered()
    gs.add_hint("某提示")
    gs.reset(target_answer="杜甫")
    assert gs.target_answer == "杜甫"
    assert gs.dialogue_count == 0
    assert gs.phase == GamePhase.PLAYING
    assert gs.hint_history == []


def test_mark_won_and_surrendered():
    gs = GameState(target_answer="李白")
    gs.mark_won()
    assert gs.phase == GamePhase.WON
    gs.mark_surrendered()
    assert gs.phase == GamePhase.SURRENDERED


# ---------- keyword detectors ----------

def test_is_likely_surrender():
    assert is_likely_surrender("我投降") is True
    assert is_likely_surrender("公布答案吧") is True
    assert is_likely_surrender("是男的吗") is False


def test_is_likely_hint_request():
    assert is_likely_hint_request("求提示") is True
    assert is_likely_hint_request("给点线索") is True
    assert is_likely_hint_request("是男的吗") is False


def test_is_replay_request():
    assert is_replay_request("再来一局") is True
    assert is_replay_request("重新开始") is True
    assert is_replay_request("是男的吗") is False


def test_is_doubt_request():
    assert is_doubt_request("重答") is True
    assert is_doubt_request("我怀疑刚才的答案") is True
    assert is_doubt_request("你确定吗") is True
    assert is_doubt_request("答案不对") is True
    assert is_doubt_request("是男的吗") is False
    assert is_doubt_request("开始") is False


# ---------- _is_canonical_answer ----------

def test_is_canonical_answer_exact():
    assert _is_canonical_answer("是。") is True
    assert _is_canonical_answer("否。") is True
    assert _is_canonical_answer("或许是。") is True
    assert _is_canonical_answer("或许不是。") is True
    assert _is_canonical_answer("无可奉告，换个问法吧。") is True


def test_is_canonical_answer_loose():
    assert _is_canonical_answer("  是。  ") is True
    assert _is_canonical_answer("答：是。") is True
    assert _is_canonical_answer("这是一个很长的不规范回答") is False
    assert _is_canonical_answer("") is False
    assert _is_canonical_answer("写好了，请猜猜看") is False


# ---------- collect_fact_qa_pairs ----------

def _msgs():
    return [
        {"role": "user", "content": "开始"},
        {"role": "assistant", "content": "写好了，请猜猜看，我会回答是或否"},
        {"role": "user", "content": "是男的吗"},
        {"role": "assistant", "content": "是。"},
        {"role": "user", "content": "唐朝的吗"},
        {"role": "assistant", "content": "否。"},
        {"role": "user", "content": "求提示"},
        {"role": "assistant", "content": "目前有效提问次数尚不足，暂不提供提示，请继续提问。"},
        {"role": "user", "content": "是文臣吗"},
        {"role": "assistant", "content": "或许是。"},
        {"role": "user", "content": "我投降"},
        {"role": "assistant", "content": "本局答案是李白。"},
        {"role": "user", "content": "重答"},
    ]


def test_collect_fact_qa_pairs_filters_non_fact():
    pairs = collect_fact_qa_pairs(_msgs())
    assert len(pairs) == 3
    assert pairs[0] == (1, "是男的吗", "是。")
    assert pairs[1] == (2, "唐朝的吗", "否。")
    assert pairs[2] == (3, "是文臣吗", "或许是。")


def test_collect_fact_qa_pairs_empty_when_only_meta():
    msgs = [
        {"role": "user", "content": "开始"},
        {"role": "assistant", "content": "好"},
        {"role": "user", "content": "求提示"},
        {"role": "assistant", "content": "暂不提供提示。"},
    ]
    assert collect_fact_qa_pairs(msgs) == []


def test_collect_fact_qa_pairs_skips_non_canonical_assistant():
    # 提问后的 assistant 回复不是规范答案，应被跳过
    msgs = [
        {"role": "user", "content": "是男的吗"},
        {"role": "assistant", "content": "我认为这个问题很复杂，需要从历史背景说起..."},
        {"role": "user", "content": "唐朝的吗"},
        {"role": "assistant", "content": "否。"},
    ]
    pairs = collect_fact_qa_pairs(msgs)
    assert len(pairs) == 1
    assert pairs[0][1] == "唐朝的吗"


def test_collect_fact_qa_pairs_doubt_input_excluded():
    pairs = collect_fact_qa_pairs(_msgs())
    # 最后的"重答""我投降"不应作为待核查提问
    for _, q, _ in pairs:
        assert "重答" not in q
        assert "投降" not in q
