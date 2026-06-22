# ⑥ Tool Prompt（工具化预留层）

> 为未来 LangChain Agent 化预留的接口说明层。
> 当前版本不实现真正的工具调用（仍由 LLM 直接生成回复），
> 但 prompt 结构已为未来升级做好准备。

---

## 未来升级路径

```
System: persona + rules + state + hint + output
Human:  question
Memory: history
Tool:   check_answer(name) / give_hint(level) / reveal_answer()
```

当真正 Agent 化时，本层会描述可用工具，逻辑从 prompt 迁移到 tools。

---

## 输入参数

| 参数            | 默认值   | 说明                                       |
| --------------- | -------- | ------------------------------------------ |
| `enable_tools`  | `False`  | 当前版本默认纯 prompt 模式；LangChain 化时设为 `True` |

---

## Prompt 内容（`enable_tools=False` 时为空字符串，不注入）

【可用工具（未来 LangChain Agent 化预留）】
你可以在以下场景调用对应工具：

1. `check_answer(name)` —— 当玩家猜测具体人名时，校验是否正确
2. `give_hint(level)`   —— 当玩家索要提示且提示状态为 enabled 时，生成不重复线索
3. `reveal_answer()`    —— 当玩家投降时，公布答案并评价

注意：当前版本尚未启用工具调用，请直接按上述规则生成回复。
