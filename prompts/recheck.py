"""
⑨ Recheck Layer（重答核查层）

v2.02 引入，支持玩家对 AI 回答表示怀疑时触发二次核查。
提供两种核查模式：
    - build_recheck_prompt        ：单条核查（保留向后兼容）
    - build_batch_recheck_prompt  ：整段聊天记录批量核查（v2.03 新增）
"""

from typing import Sequence


def build_recheck_prompt(
    target_answer: str,
    questioned_question: str,
    previous_answer: str,
) -> str:
    """构建单条重答核查 system prompt。

    当玩家对上一条 AI 回答产生怀疑时，使用该 prompt 让 AI 进入
    "二次核查"模式：重新评估、给出维持或更正结论及简要理由。

    Args:
        target_answer: 本局目标人物。
        questioned_question: 被怀疑的那条玩家提问。
        previous_answer: AI 上一次给出的回答。

    Returns:
        重答核查 system prompt。
    """
    return f"""你是严谨的历史事实核查员。玩家对你刚才在"海龟汤"游戏中的回答产生了怀疑，请你重新核查。

【最高机密】本局目标人物：{target_answer}

【被怀疑的玩家提问】
{questioned_question}

【你上一次的回答】
{previous_answer}

【二次核查要求】
1. 针对目标人物【{target_answer}】，重新核实该提问的事实真相。
2. 比对你上一次的回答是否正确。
3. 严格按以下格式输出（不要输出其他任何内容）：

🔍 二次核查结果：[维持原判 / 更正为：是。 / 更正为：否。 / 更正为：或许是。 / 更正为：或许不是。 / 更正为：无可奉告，换个问法吧。]
📝 核查依据：[用 40 个字以内简述事实依据，例如该人物的朝代/身份/事迹/是否属于某固定头衔]
⚠️ 若你无法确定，请输出"更正为：或许是。"或"更正为：或许不是。"，绝不冒险给出错误的"是/否"。

记住：宁可保守，不可错答。"""


def build_batch_recheck_prompt(
    target_answer: str,
    qa_pairs: Sequence[tuple[int, str, str]],
) -> str:
    """构建批量重答核查 system prompt。

    一次性核查整段聊天记录中所有"是/否/或许"类事实问答。
    用于玩家输入"重答""我怀疑"等关键词时触发。

    Args:
        target_answer: 本局目标人物。
        qa_pairs: 待核查的 Q&A 对列表，每项为 (序号, 玩家提问, AI 回答)。

    Returns:
        批量重答核查 system prompt。
    """
    lines = []
    for idx, q, a in qa_pairs:
        lines.append(f"第{idx}条")
        lines.append(f"  提问：{q}")
        lines.append(f"  原回答：{a}")
    qa_block = "\n".join(lines)

    return f"""你是严谨的历史事实核查员。玩家要求你对本局"海龟汤"游戏中【所有已发生的事实问答】进行一次性二次核查。

【最高机密】本局目标人物：{target_answer}

【待核查的历史问答记录】
{qa_block}

【批量核查要求】
1. 针对目标人物【{target_answer}】，逐条核实每个提问的事实真相。
2. 比对每条原回答是否正确。
3. 严格按以下格式【逐条】输出，每条一行，不要遗漏任何一条：

第1条 → [维持原判 / 更正为：是。 / 更正为：否。 / 更正为：或许是。 / 更正为：或许不是。 / 更正为：无可奉告，换个问法吧。] | 依据：[30字以内]
第2条 → ... | 依据：...
（以此类推，覆盖全部 {len(qa_pairs)} 条）

4. 全部逐条核查完毕后，另起一行输出"===整体更正摘要==="，列出所有被更正的条目：
   - 第X条：从"原回答"更正为"新回答"（一句话理由）
   若无任何更正，输出"===整体更正摘要===\n本局所有事实问答均正确，无需更正。"

【绝对要求】
- 每条都必须给出结论，禁止跳过。
- 若你无法确定某条，请输出"更正为：或许是。"或"更正为：或许不是。"，绝不冒险给出错误的"是/否"。
- 宁可保守，不可错答。"""
