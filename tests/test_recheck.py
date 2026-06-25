"""批量核查逻辑测试（mock LLM）。"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import llm_client
from llm_client import LLMClient


def _make_messages(n_pairs: int) -> list[dict]:
    """构造含 n_pairs 条事实问答的消息列表。"""
    msgs = [
        {"role": "user", "content": "开始"},
        {"role": "assistant", "content": "写好了"},
    ]
    for i in range(1, n_pairs + 1):
        msgs.append({"role": "user", "content": f"问题{i}"})
        msgs.append({"role": "assistant", "content": "是。"})
    return msgs


def test_recheck_batch_empty_returns_hint(monkeypatch):
    client = LLMClient("k", "u", "m")
    msgs = [{"role": "user", "content": "开始"}, {"role": "assistant", "content": "好"}]
    result = client.recheck_batch("李白", msgs)
    assert "没有可核查" in result


def test_recheck_batch_single_batch(monkeypatch):
    """不足一批时只调用一次 LLM。"""
    calls = []
    def fake_call(messages, api_key, api_url, model, temperature=None, **kw):
        calls.append(messages)
        return "第1条 → 维持原判 | 依据：x\n===整体更正摘要===\n均正确。"
    monkeypatch.setattr(llm_client, "call_llm", fake_call)

    client = LLMClient("k", "u", "m")
    msgs = _make_messages(3)
    result = client.recheck_batch("李白", msgs)
    assert len(calls) == 1
    assert "第 1/1 批" in result
    assert "共 3 条问答" in result


def test_recheck_batch_multi_batch(monkeypatch):
    """超过 BATCH_SIZE 时分批调用。"""
    calls = []
    def fake_call(messages, api_key, api_url, model, temperature=None, **kw):
        calls.append(messages)
        # 从 system prompt 里提取条数
        sys_text = messages[0]["content"]
        return f"核查了若干条\n===整体更正摘要===\n批次结果"
    monkeypatch.setattr(llm_client, "call_llm", fake_call)

    client = LLMClient("k", "u", "m")
    # 用小 batch_size 便于测试
    msgs = _make_messages(25)
    result = client.recheck_batch("李白", msgs, batch_size=10)
    assert len(calls) == 3  # 10 + 10 + 5
    assert "第 1/3 批" in result
    assert "第 3/3 批" in result


def test_recheck_batch_progress_callback(monkeypatch):
    def fake_call(messages, api_key, api_url, model, temperature=None, **kw):
        return "ok"
    monkeypatch.setattr(llm_client, "call_llm", fake_call)

    progress = []
    client = LLMClient("k", "u", "m")
    msgs = _make_messages(15)
    client.recheck_batch("李白", msgs, batch_size=10, on_progress=lambda done, total: progress.append((done, total)))
    assert progress == [(1, 2), (2, 2)]


def test_recheck_batch_uses_low_temperature(monkeypatch):
    temps = []
    def fake_call(messages, api_key, api_url, model, temperature=None, **kw):
        temps.append(temperature)
        return "ok"
    monkeypatch.setattr(llm_client, "call_llm", fake_call)

    client = LLMClient("k", "u", "m")
    msgs = _make_messages(3)
    client.recheck_batch("李白", msgs)
    assert temps[0] == llm_client.RECHECK_TEMPERATURE
    assert temps[0] < llm_client.ANSWER_TEMPERATURE
