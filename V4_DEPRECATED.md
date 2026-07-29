# V4 已废弃

自 2026-07-29 起，V4 被正式判定为废案。

废弃范围：

- `app_v4.py`
- `launcher.py` 中的 V4 运行路径
- `src/guess_history/`
- `data/v4/`
- `tests/test_m1_domain.py` 至 `tests/test_m5_launcher.py` 中的 V4 验证
- `doc_CN/ARCHITECTURE_V4_DEPRECATED.md`
- `doc_EN/ARCHITECTURE_V4_DEPRECATED.md`

这些文件仅作为历史、迁移输入和反例保留。V5 不得导入 V4 业务模块，也不得用 V4 测试作为 V5 验收证据。

当前权威文档：

- 中文：`doc_CN/ARCHITECTURE.md`
- English: `doc_EN/ARCHITECTURE.md`

V5 尚未实现。在 V5 架构签署和 V5-M0 完成前，不应将任何现有 EXE 或 Streamlit 入口称为 V5。
