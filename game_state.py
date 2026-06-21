"""
游戏状态逻辑（Python 层）

核心重构思想：
    ❌ 不要做：用 prompt 写 if/else、用 prompt 做数学判断、用 prompt 管状态机
    ✅ 应该做：N >= 6 放 Python、状态判断放 Python、prompt 行为放 Prompt

本模块负责所有"数值/状态判断"，把计算结果交给 prompts/ 层去描述。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ============================================================
# 常量配置
# ============================================================

#: 开启提示所需的最小有效提问次数（原"铁律二"的 N >= 6）
HINT_THRESHOLD: int = 6

#: 提示状态枚举
HINT_BLOCKED: str = "blocked"
HINT_ENABLED: str = "enabled"


class GamePhase(str, Enum):
    """游戏阶段枚举。"""

    PLAYING = "playing"        # 进行中
    WON = "won"                # 玩家猜中
    SURRENDERED = "surrendered"  # 玩家投降


# ============================================================
# GameState 数据类
# ============================================================


@dataclass
class GameState:
    """海龟汤猜人游戏的完整状态。

    所有"数学/逻辑判断"都在这里用 Python 完成，
    prompt 层只读取计算结果，不做任何 if/else。
    """

    target_answer: str                    # 本局目标人物
    dialogue_count: int = 0               # 有效提问次数
    phase: GamePhase = GamePhase.PLAYING  # 当前阶段
    hint_history: list[str] = field(default_factory=list)  # 已给过的提示（防重复）

    # --------------------------------------------------------
    # 提示状态计算（替代原"铁律二：N >= 6 查表"）
    # --------------------------------------------------------

    @property
    def hint_mode(self) -> str:
        """计算提示状态。

        ✅ 正确方式（交给代码）：
            if dialogue_count < 6:
                hint_mode = "blocked"
            else:
                hint_mode = "enabled"

        Returns:
            HINT_BLOCKED 或 HINT_ENABLED
        """
        if self.dialogue_count < HINT_THRESHOLD:
            return HINT_BLOCKED
        return HINT_ENABLED

    @property
    def hint_available(self) -> bool:
        """提示是否可用（布尔便捷接口）。"""
        return self.hint_mode == HINT_ENABLED

    # --------------------------------------------------------
    # 提问计数
    # --------------------------------------------------------

    def increment_dialogue(self) -> int:
        """有效提问次数 +1，返回新值。"""
        self.dialogue_count += 1
        return self.dialogue_count

    # --------------------------------------------------------
    # 阶段流转
    # --------------------------------------------------------

    def mark_won(self) -> None:
        """标记为胜利。"""
        self.phase = GamePhase.WON

    def mark_surrendered(self) -> None:
        """标记为投降。"""
        self.phase = GamePhase.SURRENDERED

    def reset(self, target_answer: str) -> None:
        """重置为新的一局。"""
        self.target_answer = target_answer
        self.dialogue_count = 0
        self.phase = GamePhase.PLAYING
        self.hint_history.clear()

    # --------------------------------------------------------
    # 提示历史管理（防重复）
    # --------------------------------------------------------

    def add_hint(self, hint: str) -> None:
        """记录已给出的提示，供 LLM 防重复参考。"""
        self.hint_history.append(hint)

    def get_hint_context(self) -> str:
        """获取提示历史上下文（供 prompt 注入）。

        Returns:
            如果有历史提示，返回编号列表；否则返回"无"。
        """
        if not self.hint_history:
            return "无"
        lines = [f"  {i}. {h}" for i, h in enumerate(self.hint_history, 1)]
        return "\n".join(lines)

    # --------------------------------------------------------
    # 便捷快照
    # --------------------------------------------------------

    def snapshot(self) -> dict:
        """返回当前状态的字典快照（用于调试/日志）。"""
        return {
            "target_answer": self.target_answer,
            "dialogue_count": self.dialogue_count,
            "hint_mode": self.hint_mode,
            "phase": self.phase.value,
            "hint_count": len(self.hint_history),
        }


# ============================================================
# 纯函数接口（便于在不维护实例时使用）
# ============================================================


def compute_hint_mode(dialogue_count: int, threshold: int = HINT_THRESHOLD) -> str:
    """纯函数：根据提问次数计算提示状态。

    这是"铁律二"重构的核心——把 N >= 6 的判断从 prompt 搬到 Python。

    Args:
        dialogue_count: 已提问次数。
        threshold: 开启提示的阈值，默认 6。

    Returns:
        "blocked" 或 "enabled"
    """
    return HINT_ENABLED if dialogue_count >= threshold else HINT_BLOCKED


def is_likely_surrender(user_input: str) -> bool:
    """检测玩家是否意图投降。

    简单的关键词匹配（Python 层预判），最终是否触发投降仍由 LLM 判断。
    这一步只是辅助，减少 LLM 误判。

    Args:
        user_input: 玩家输入文本。

    Returns:
        是否疑似投降意图。
    """
    surrender_keywords = [
        "我投降", "投降", "公布答案", "不猜了", "直接告诉我",
        "放弃", "认输", "不玩了", "揭晓答案", "告诉我答案",
    ]
    text = user_input.strip().lower()
    return any(kw in text for kw in surrender_keywords)


def is_likely_hint_request(user_input: str) -> bool:
    """检测玩家是否在索要提示。

    简单的关键词匹配（Python 层预判），辅助 LLM 判断。

    Args:
        user_input: 玩家输入文本。

    Returns:
        是否疑似索要提示。
    """
    hint_keywords = [
        "求提示", "给点线索", "猜不出", "猜不出来", "给个提示",
        "提示一下", "线索", "给提示", "帮帮我", "太难了",
    ]
    text = user_input.strip().lower()
    return any(kw in text for kw in hint_keywords)


def is_replay_request(user_input: str) -> bool:
    """检测玩家是否请求再来一局。"""
    replay_keywords = ["再来一局", "重新开始", "新一局", "再玩一局", "重新玩"]
    text = user_input.strip().lower()
    return any(kw in text for kw in replay_keywords)