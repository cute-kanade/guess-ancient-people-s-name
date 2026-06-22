# ⑦ Builder（组合器）

> 将各分层 prompt 组合成最终的 system prompt。
> 这是唯一对外暴露的"组装入口"，应用层只需调用 `build_system_prompt()`。

---

## 输入参数

| 参数              | 类型   | 默认值     | 说明                                       |
| ----------------- | ------ | ---------- | ------------------------------------------ |
| `target_answer`   | str    | ——         | 本局目标人物                               |
| `dialogue_count`  | int    | ——         | 已提问次数（仅展示，不用于判断）           |
| `hint_mode`       | str    | ——         | `"blocked"` 或 `"enabled"`（由 Python 计算）|
| `theme`           | str    | `"历史"`   | 游戏主题                                   |
| `enable_tools`    | bool   | `False`    | 是否启用工具说明层                         |

---

## 分层组装顺序（从上到下）

1. ① Base Persona   —— 角色（`persona`）
2. ③ State Layer    —— 状态（含最高机密）（`state`）
3. ② Rule Layer     —— 行为约束（`rules`）
4. ④ Hint Strategy  —— 提示策略（`hint`）
5. ⑤ Output Format  —— 输出格式（`output`）
6. ⑥ Tool Prompt    —— 工具化预留（可选，`enable_tools=True` 时追加）

> 各层之间用空行（`\n\n`）连接，保持清晰边界。
