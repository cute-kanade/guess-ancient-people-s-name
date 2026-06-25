"""
⑦ Builder（组合器）

将各分层 prompt 组合成最终的 system prompt。
这是唯一对外暴露的"组装入口"，应用层只需调用 build_system_prompt()。
"""

from .persona import build_persona
from .rules import build_rules
from .state import build_state
from .hint import build_hint_strategy
from .output import build_output_format
from .tools import build_tool_prompt
from .fact_check import build_fact_check_layer


def build_system_prompt(
    target_answer: str,
    dialogue_count: int,
    hint_mode: str,
    theme: str = "历史",
    enable_tools: bool = False,
    enable_fact_check: bool = True,
) -> str:
    """组合所有分层，构建最终 system prompt。

    分层顺序（从上到下）：
        ① Base Persona   —— 角色
        ③ State Layer    —— 状态（含最高机密）
        ② Rule Layer     —— 行为约束
        ④ Hint Strategy  —— 提示策略
        ⑤ Output Format  —— 输出格式
        ⑧ Fact Check     —— 事实核查强化（v2.02，默认开启）
        ⑥ Tool Prompt    —— 工具化预留（可选）

    Args:
        target_answer: 本局目标人物。
        dialogue_count: 已提问次数（仅展示，不用于判断）。
        hint_mode: 提示状态，"blocked" 或 "enabled"（由 Python 计算）。
        theme: 游戏主题，默认 "历史"。
        enable_tools: 是否启用工具说明层，默认 False。
        enable_fact_check: 是否追加事实核查强化层，默认 True。

    Returns:
        完整的 system prompt 字符串。
    """
    layers = [
        build_persona(theme),
        build_state(target_answer, dialogue_count, hint_mode),
        build_rules(),
        build_hint_strategy(hint_mode),
        build_output_format(target_answer),
    ]

    if enable_fact_check:
        layers.append(build_fact_check_layer())

    tool_layer = build_tool_prompt(enable_tools)
    if tool_layer:
        layers.append(tool_layer)

    # 用分隔线连接各层，保持清晰边界
    return "\n\n".join(layers)