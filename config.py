"""
全局配置

集中管理 API 配置、温度、批量阈值等参数。
密钥不再硬编码，优先从环境变量 / Streamlit secrets 读取。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# =========================
# 🔐 API 密钥（安全优先）
# =========================
# 旧版硬编码 Key 已移除。读取顺序：
#   1. Streamlit secrets (st.secrets["api_key"])
#   2. 环境变量 LLM_API_KEY
#   3. 环境变量 ZHIPU_API_KEY
# 若都未设置，app 层会提示用户在侧栏手动输入。

DEFAULT_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-4-air"


def resolve_default_api_key(st_secrets=None) -> str:
    """安全地解析默认 API Key。

    Args:
        st_secrets: 可选的 streamlit secrets 对象（st.secrets）。

    Returns:
        API Key 字符串；未找到返回空字符串。
    """
    if st_secrets is not None:
        try:
            key = st_secrets.get("api_key", "")
            if key and key.strip():
                return key.strip()
        except Exception:
            pass
    for env_var in ("LLM_API_KEY", "ZHIPU_API_KEY"):
        key = os.getenv(env_var, "")
        if key and key.strip():
            return key.strip()
    return ""


# =========================
# 🌡️ 采样温度
# =========================
ANSWER_TEMPERATURE: float = 0.3
RECHECK_TEMPERATURE: float = 0.1
GENERAL_TEMPERATURE: float = 0.6

# =========================
# 🔁 重试 / 超时
# =========================
MAX_RETRIES: int = 3
RETRY_BACKOFF_BASE: float = 1.5
REQUEST_TIMEOUT: int = 30

# =========================
# 🔁 批量核查
# =========================
BATCH_SIZE: int = 10

# =========================
# 🎚️ 提示阈值
# =========================
HINT_THRESHOLD: int = 6

# =========================
# 📁 数据路径
# =========================
PEOPLE_MD_PATH = "peoples_names.md"
PEOPLE_JSON_PATH = "data/people.json"


@dataclass
class APIConfig:
    """API 调用参数容器。"""
    api_key: str
    api_url: str
    model: str
