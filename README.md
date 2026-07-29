# Guess Ancient Chinese People

这是一个“猜中国古代人物”本地游戏项目。

## 当前状态

- V3：历史版本；
- V4：已于 2026-07-29 正式判定为废案，现有源码和 EXE 只保留作历史验证；
- V5：处于鲁棒性优先架构设计阶段，尚未开始实现。

V5 不再采用“规则解析失败就调用 LLM”的路径。核心游戏必须在无 API Key、无网络和 Provider 故障时完整运行。

## 权威文档

- [V5 中文架构](doc_CN/ARCHITECTURE.md)
- [V5 English Architecture](doc_EN/ARCHITECTURE.md)
- [V4 废案说明](V4_DEPRECATED.md)
- [V4 中文历史记录](doc_CN/ARCHITECTURE_V4_DEPRECATED.md)
- [V4 English Historical Record](doc_EN/ARCHITECTURE_V4_DEPRECATED.md)

请勿将 `app_v4.py`、`src/guess_history/` 或当前 `GuessHistory.exe` 作为 V5 发布物。
