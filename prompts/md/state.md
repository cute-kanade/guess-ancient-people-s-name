# ③ State Layer（状态描述层）

> 替代原 prompt 中"当前系统状态"部分。
> 关键原则：只"描述"状态，不让模型计算。
> 所有数值判断（如 N >= 6）由 Python 在 `game_state.py` 中完成，
> 本层只把计算结果以文字形式注入 prompt。

---

## 输入参数

| 参数             | 说明                                       |
| ---------------- | ------------------------------------------ |
| `target_answer`  | 本局目标人物（最高机密）                   |
| `dialogue_count` | 已提问次数（仅用于展示，不用于判断）       |
| `hint_mode`      | 提示状态，由 Python 计算：`blocked` / `enabled` |

---

## Prompt 内容

【最高机密】本局的唯一正确答案是：{target_answer}。绝对禁止在玩家完全猜中或主动投降前以任何形式泄露。

【当前游戏状态】

- 目标人物：{target_answer}
- 已提问次数：{dialogue_count}
- 提示状态：{hint_mode}
