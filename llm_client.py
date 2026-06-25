"""
LLM 客户端层

从 app 层抽离所有 LLM 调用相关逻辑：
    - call_llm 通用调用（支持自定义 temperature、重试）
    - detect_env_providers 环境变量多提供商探测
    - LLMClient 语义化封装：answer() / recheck_batch()

设计目标：
    - app 层只调语义化方法，不关心 URL/header/重试细节
    - 重试与超时集中管理，便于后续切换为异步
"""

from __future__ import annotations

import os
import time
import requests
from dataclasses import dataclass
from typing import Optional

from prompts import build_batch_recheck_prompt
from game_state import collect_fact_qa_pairs


# =========================
# ⚙️ 默认配置（可被 config.py 覆盖）
# =========================

DEFAULT_API_KEY = "2decccf007f4414b8c71cda0b8e3cf26.TeiHdRMi4Pxs1Fx3"
DEFAULT_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-4-air"

#: 常规回答温度（v2.02 降低以减少事实性错误）
ANSWER_TEMPERATURE: float = 0.3
#: 重答核查温度（更低，追求最严谨）
RECHECK_TEMPERATURE: float = 0.1

#: 重试配置
MAX_RETRIES: int = 3
RETRY_BACKOFF_BASE: float = 1.5  # 指数退避基数（秒）
REQUEST_TIMEOUT: int = 30

#: 批量核查每批最大 Q&A 对数（防 token 超限）
BATCH_SIZE: int = 10

#: PC 系统环境 LLM API（多提供商自动探测）
# 格式: { 显示名: (环境变量名, 默认URL, 默认模型) }
ENV_PROVIDERS = {
    "DeepSeek":        ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1/chat/completions", "deepseek-chat"),
    "OpenAI":          ("OPENAI_API_KEY",   "https://api.openai.com/v1/chat/completions",   "gpt-4o-mini"),
    "智谱AI (GLM)":     ("ZHIPU_API_KEY",    "https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm-4-air"),
    "xAI (Grok)":      ("XAI_API_KEY",      "https://api.x.ai/v1/chat/completions",         "grok-2"),
    "自定义环境变量":     ("", "", ""),  # 占位，由用户手动输入
}


# =========================
# 🔍 环境变量提供商探测
# =========================

def detect_env_providers():
    """扫描所有预设提供商，返回 [(显示名, 是否已设置, api_key, api_url, model)]"""
    results = []
    for name, (env_var, url, model) in ENV_PROVIDERS.items():
        if name == "自定义环境变量":
            key = os.getenv("CUSTOM_ENV_KEY", "")
            url = os.getenv("CUSTOM_ENV_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions")
            model = os.getenv("CUSTOM_ENV_MODEL", "glm-4-air")
            has_key = bool(key and key.strip())
        else:
            key = os.getenv(env_var, "")
            has_key = bool(key and key.strip())
        results.append((name, has_key, key, url, model))
    return results


# =========================
# 📞 通用 LLM 调用（带重试）
# =========================

def call_llm(
    messages,
    api_key: str,
    api_url: str,
    model: str,
    temperature: float = ANSWER_TEMPERATURE,
    max_retries: int = MAX_RETRIES,
    timeout: int = REQUEST_TIMEOUT,
) -> str:
    """调用 LLM API，带指数退避重试。

    Args:
        messages: OpenAI 风格的消息列表。
        api_key: API 密钥。
        api_url: API URL。
        model: 模型名。
        temperature: 采样温度。
        max_retries: 最大重试次数（仅对网络/5xx 错误重试，4xx 不重试）。
        timeout: 单次请求超时秒数。

    Returns:
        模型回复文本；失败时返回以 ❌ 开头的错误说明字符串。
    """
    if not api_key or not api_key.strip():
        return "❌ API Key 为空，请先在侧栏配置有效的 API Key。"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    last_err = ""
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)

            # 4xx 错误通常不可重试（如鉴权失败、参数错误）
            if 400 <= response.status_code < 500 and response.status_code != 429:
                return f"❌ API 请求失败 (HTTP {response.status_code}): {response.text[:200]}"

            # 5xx / 429 可重试
            if response.status_code >= 500 or response.status_code == 429:
                last_err = f"HTTP {response.status_code}: {response.text[:200]}"
                if attempt < max_retries:
                    time.sleep(RETRY_BACKOFF_BASE ** attempt)
                    continue
                return f"❌ API 请求失败（已重试 {max_retries} 次）: {last_err}"

            if response.status_code != 200:
                return f"❌ API 请求失败 (HTTP {response.status_code}): {response.text[:200]}"

            data = response.json()
            if "choices" not in data:
                error_msg = data.get("error", {}).get("message", str(data))
                return f"❌ API 返回异常（缺少 choices 字段）: {error_msg}"

            return data["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout:
            last_err = f"请求超时（{timeout}秒）"
            if attempt < max_retries:
                time.sleep(RETRY_BACKOFF_BASE ** attempt)
                continue
            return f"❌ API {last_err}，已重试 {max_retries} 次，请检查网络或 API 地址。"
        except requests.exceptions.ConnectionError as e:
            last_err = str(e)
            if attempt < max_retries:
                time.sleep(RETRY_BACKOFF_BASE ** attempt)
                continue
            return f"❌ API 连接失败（已重试 {max_retries} 次）: {last_err}"
        except Exception as e:
            # 非网络类异常不重试
            return f"❌ API 调用失败: {e}"

    return f"❌ API 调用失败（已重试 {max_retries} 次）: {last_err}"


# =========================
# 🤖 LLMClient 语义化封装
# =========================

@dataclass
class LLMClient:
    """LLM 客户端，封装语义化调用方法。

    app 层实例化后调用：
        client = LLMClient(api_key, api_url, model)
        reply = client.answer(messages)
        recheck_text = client.recheck_batch(target, messages)
    """
    api_key: str
    api_url: str
    model: str

    def answer(self, messages, temperature: float = ANSWER_TEMPERATURE) -> str:
        """常规回答（temperature 默认 0.3 严谨模式）。"""
        return call_llm(messages, self.api_key, self.api_url, self.model, temperature=temperature)

    def recheck_batch(
        self,
        target_answer: str,
        messages,
        batch_size: int = BATCH_SIZE,
        on_progress=None,
    ) -> str:
        """对整段聊天记录进行批量二次核查（分批 + 汇总）。

        Args:
            target_answer: 本局目标人物。
            messages: 历史消息列表。
            batch_size: 每批最大 Q&A 对数。
            on_progress: 可选回调 (已处理批数, 总批数) -> None，用于 UI 进度反馈。

        Returns:
            汇总后的核查结果文本。若无 Q&A 对，返回提示字符串。
        """
        qa_pairs = collect_fact_qa_pairs(messages)
        if not qa_pairs:
            return "当前没有可核查的提问。请先正常提问，再对回答表示怀疑。"

        # 分批
        batches = [qa_pairs[i:i + batch_size] for i in range(0, len(qa_pairs), batch_size)]
        total = len(batches)
        batch_results: list[str] = []

        for i, batch in enumerate(batches, 1):
            system_prompt = build_batch_recheck_prompt(target_answer, batch)
            recheck_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请逐条核查以上 {len(batch)} 条历史问答。"},
            ]
            result = call_llm(
                recheck_messages,
                self.api_key,
                self.api_url,
                self.model,
                temperature=RECHECK_TEMPERATURE,
            )
            batch_results.append(f"### 第 {i}/{total} 批（第 {batch[0][0]}~{batch[-1][0]} 条）\n{result}")
            if on_progress is not None:
                on_progress(i, total)

        # 汇总
        summary_header = f"🔁 整段聊天记录二次核查（共 {len(qa_pairs)} 条问答，分 {total} 批）\n"
        return summary_header + "\n\n".join(batch_results)
