"""
④ Hint Strategy（提示策略层）

⚠️ 关键重构点：替代原"铁律二：玩家求提示判定"。

原版问题：让 LLM 做"N >= 6 查表判定"——LLM 本质不是 if-else engine。
重构方案：
    - Python（game_state.py）计算 hint_mode = "blocked" / "enabled"
    - 本层只根据已计算好的 hint_mode 描述对应行为，不做数学判断
"""


def build_hint_strategy(hint_mode: str) -> str:
    """构建提示策略层 prompt。

    Args:
        hint_mode: 提示状态，由 Python 计算得出。
                   "blocked" = 次数不足，不允许提示
                   "enabled" = 次数达标，可以提供线索

    Returns:
        提示策略层 prompt 字符串。

    Raises:
        ValueError: 当 hint_mode 不是合法值时。
    """
    if hint_mode not in ("blocked", "enabled"):
        raise ValueError(f"非法的 hint_mode: {hint_mode!r}，应为 'blocked' 或 'enabled'")

    if hint_mode == "blocked":
        return """【提示规则】
当前提示状态为 blocked（提问次数尚不足）。
当玩家发送"求提示"、"给点线索"、"猜不出"等【索要提示】的词汇时：
- 不允许提供任何提示
- 只准回复："目前有效提问次数尚不足，暂不提供提示，请继续提问。"
（警告：严禁在回复中编造"因为 X 小于 Y"之类的废话逻辑！）"""

    # hint_mode == "enabled"
    return """【提示规则】
当前提示状态为 enabled（提问次数已达标）。
当玩家发送"求提示"、"给点线索"、"猜不出"等【索要提示】的词汇时：
- 可以结合目标人物的生平，提供一个不包含该人名的典故或特征
- 回复格式："提问已达标！考官给你一个提示：[在此处给出线索]。"
【绝不重复警告】：若玩家多次索要提示，你每次给出的提示【必须完全不同】！
请强制切换信息维度（例如：第一次提示朝代背景，第二次提示关联人物，第三次提示特殊官职、死因或著名癖好），
确保每次生成的新提示绝对不与之前的提示重复。"""