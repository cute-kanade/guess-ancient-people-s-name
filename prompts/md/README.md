# 模块化 Prompt 系统（v2.0 文档版）

> 对应源码：`prompts/*.py`
> 文档目录：`prompts/md/*.md`
> 应用层入口：`app_02_01.py`

将原本"一整坨规则型超长 system prompt"拆分为可组合、可复用的分层结构：

| # | 层级               | 文件           | 文档               | 职责                                 |
| - | ------------------ | -------------- | ------------------ | ------------------------------------ |
| ① | Base Persona       | `persona.py`   | [persona.md](persona.md)   | 角色定义（"你是谁"、目标）          |
| ② | Rule Layer         | `rules.py`     | [rules.md](rules.md)       | 行为约束（五种标准回答）            |
| ③ | State Layer        | `state.py`     | [state.md](state.md)       | 状态描述（注入最高机密 + hint_mode）|
| ④ | Hint Strategy      | `hint.py`      | [hint.md](hint.md)         | 提示策略（blocked / enabled 分支）  |
| ⑤ | Output Format      | `output.py`    | [output.md](output.md)     | 输出格式（胜利/投降/正常对话）      |
| ⑥ | Tool Prompt        | `tools.py`     | [tools.md](tools.md)       | 工具化预留（LangChain 化接口）      |
| ⑦ | Builder            | `builder.py`   | [builder.md](builder.md)   | 组装入口，拼接上述各层              |

---

## 设计原则

- 数学/状态判断（如 `N >= 6`）交给 Python（见 `game_state.py`）
- Prompt 只负责"描述状态"和"约束行为"，不做 `if/else` 计算
- 各层可独立替换，换项目（明朝版/欧洲版）只需替换 `persona` + 人物库

---

## 最终 system prompt 组装顺序

```
① persona
↓
③ state      （含【最高机密】目标人物）
↓
② rules      （五种标准回答）
↓
④ hint       （按 hint_mode 注入对应分支）
↓
⑤ output     （胜利 / 投降 / 正常对话）
↓
⑥ tools      （可选，enable_tools=True 时追加）
```

各层之间以 `\n\n` 分隔，保持清晰边界。

---

## 与 `app_02_01.py` 的调用关系

```python
from prompts import build_system_prompt

system_prompt = build_system_prompt(
    target_answer=gs.target_answer,
    dialogue_count=gs.dialogue_count,
    hint_mode=gs.hint_mode,   # ← Python 已算好的 "blocked" / "enabled"
    theme="历史",
    enable_tools=False,
)
```
