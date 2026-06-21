"""
模块化 Prompt 系统（LangChain 分层思路）

将原本"一整坨规则型超长 system prompt"拆分为可组合、可复用的分层结构：
    1. Base Persona  （角色层）      -> persona.py
    2. Rule Layer    （行为约束）    -> rules.py
    3. State Layer   （状态描述）    -> state.py
    4. Hint Strategy （提示策略）    -> hint.py
    5. Output Format （输出格式）    -> output.py
    6. Tool Prompt   （工具化预留）  -> tools.py
    7. Builder       （组合器）      -> builder.py

设计原则：
    - 数学/状态判断（如 N >= 6）交给 Python（见 game_state.py）
    - Prompt 只负责"描述状态"和"约束行为"，不做 if/else 计算
    - 各层可独立替换，换项目（明朝版/欧洲版）只需替换 persona + 人物库
"""

from .persona import build_persona
from .rules import build_rules
from .state import build_state
from .hint import build_hint_strategy
from .output import build_output_format
from .tools import build_tool_prompt
from .builder import build_system_prompt

__all__ = [
    "build_persona",
    "build_rules",
    "build_state",
    "build_hint_strategy",
    "build_output_format",
    "build_tool_prompt",
    "build_system_prompt",
]