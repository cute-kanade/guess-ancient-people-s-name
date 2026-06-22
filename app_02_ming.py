"""
猜明朝人物（AI海龟汤 v2.0）—— 模块化 Prompt 重构版

以 app_02_01.py 为框架，知识库切换为《明朝名人二百人表》CSV，
迭代掉 app_01_ming.py。

重构要点（对比 app_01_ming.py）：
    ❌ 旧版：四大铁律全塞在 system prompt，让 LLM 做 N>=6 查表判定
    ✅ 新版：Prompt 分层（prompts/ 包）+ Python 状态逻辑（game_state.py）

架构：
    prompts/                          —— 模块化 Prompt（persona/rules/state/hint/output/tools/builder）
    game_state.py                     —— Python 状态逻辑（GameState 数据类 + 纯函数）
    明朝名人二百人表 - 明朝名人二百人表.csv  —— 知识库（200 位明朝名人）
    app_02_ming.py                    —— 本文件，Streamlit 应用层

逻辑归属：
    | 逻辑       | 放哪里    |
    | N >= 6     | Python   |  ← game_state.GameState.hint_mode
    | 状态判断    | Python   |  ← game_state.GameState.phase
    | prompt行为 | Prompt   |  ← prompts/rules.py, prompts/hint.py
    | 输出格式    | Prompt   |  ← prompts/output.py
    | 规则约束    | Prompt   |  ← prompts/rules.py
"""

import streamlit as st
import random
import requests
import os
import csv

# =========================
# 🔧 Streamlit 页面配置（必须为第一个 Streamlit 命令）
# =========================
st.set_page_config(page_title="猜明朝人物", page_icon="🎭")

# 导入模块化 Prompt 系统
from prompts import build_system_prompt
from game_state import (
    GameState,
    GamePhase,
    compute_hint_mode,
    is_likely_surrender,
    is_likely_hint_request,
    is_replay_request,
)

# =========================
# ⚙️ 基础配置
# =========================

# 默认 LLM API（智谱AI GLM-4.5-Air）
DEFAULT_API_KEY = "91cf038ac2f14fa0bbed2f38bc1d4c8d.Cus7ruJGpfpz0fSG"
DEFAULT_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-4.5-air"

# PC 系统环境 LLM API（多提供商自动探测）
# 格式: { 显示名: (环境变量名, 默认URL, 默认模型) }
ENV_PROVIDERS = {
    "DeepSeek":        ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1/chat/completions", "deepseek-chat"),
    "OpenAI":          ("OPENAI_API_KEY",   "https://api.openai.com/v1/chat/completions",   "gpt-4o-mini"),
    "智谱AI (GLM)":     ("ZHIPU_API_KEY",    "https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm-4.5-air"),
    "xAI (Grok)":      ("XAI_API_KEY",      "https://api.x.ai/v1/chat/completions",         "grok-2"),
    "自定义环境变量":     ("", "", ""),  # 占位，由用户手动输入
}


def detect_env_providers():
    """扫描所有预设提供商，返回 [(显示名, 是否已设置, api_key, api_url, model)]"""
    results = []
    for name, (env_var, url, model) in ENV_PROVIDERS.items():
        if name == "自定义环境变量":
            key = os.getenv("CUSTOM_ENV_KEY", "")
            url = os.getenv("CUSTOM_ENV_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions")
            model = os.getenv("CUSTOM_ENV_MODEL", "glm-4.5-air")
            has_key = bool(key and key.strip())
        else:
            key = os.getenv(env_var, "")
            has_key = bool(key and key.strip())
        results.append((name, has_key, key, url, model))
    return results


# =========================
# 📄 读取人物库（明朝名人二百人表 CSV）
# =========================
def load_people_names():
    """依次尝试多种编码读取 CSV 文件，兼容 UTF-8、GBK、GB18030 等编码。

    知识库：《明朝名人二百人表 - 明朝名人二百人表.csv》
    读取列：简体人名
    """
    csv_path = "明朝名人二百人表 - 明朝名人二百人表.csv"
    encodings_to_try = ["utf-8", "utf-8-sig", "gbk", "gb2312", "gb18030"]
    for enc in encodings_to_try:
        try:
            with open(csv_path, "r", encoding=enc) as f:
                reader = csv.DictReader(f)
                names = [row["简体人名"].strip() for row in reader if row.get("简体人名", "").strip()]
                if names:
                    return names
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception as e:
            st.error(f"人物库加载失败: {e}")
            return ["王阳明"]  # fallback
    st.error("人物库加载失败: 无法识别的文件编码，请确认 CSV 文件编码格式。")
    return ["王阳明"]  # fallback


# =========================
# 🎯 初始化 session_state（使用 GameState 数据类）
# =========================
def init_session_state():
    """初始化 Streamlit session_state。

    使用 GameState 数据类统一管理游戏状态，
    替代旧版散落的 target_answer / dialogue_count / game_active。
    """
    if "game_state" not in st.session_state:
        st.session_state.game_state = GameState(target_answer="")
    if "messages" not in st.session_state:
        st.session_state.messages = []


init_session_state()


# =========================
# 🤖 调用 LLM API（通用）
# =========================
def call_llm(messages, api_key, api_url, model):
    if not api_key or not api_key.strip():
        return "❌ API Key 为空，请先在侧栏配置有效的 API Key。"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            api_url,
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.7
            },
            timeout=30
        )

        if response.status_code != 200:
            return f"❌ API 请求失败 (HTTP {response.status_code}): {response.text[:200]}"

        data = response.json()

        if "choices" not in data:
            error_msg = data.get("error", {}).get("message", str(data))
            return f"❌ API 返回异常（缺少 choices 字段）: {error_msg}"

        return data["choices"][0]["message"]["content"]

    except requests.exceptions.Timeout:
        return "❌ API 请求超时（30秒），请检查网络或 API 地址。"
    except Exception as e:
        return f"❌ API调用失败: {e}"


# =========================
# 🎮 Streamlit UI
# =========================

st.title("🎭 猜明朝人物（AI海龟汤 v2.0 模块化版）")
st.caption("🔧 架构升级：Prompt 分层 + Python 状态逻辑（N>=6 判定已迁移至代码层）｜ 知识库：明朝名人二百人表")

# =========================
# 🎚️ 侧栏：LLM API 设置
# =========================
with st.sidebar:
    st.header("⚙️ LLM API 设置")

    api_mode = st.radio(
        "选择 API 来源：",
        ["🔹 默认LLM API", "🔹 PC系统环境 LLM API", "🔹 自定义LLM API"],
        index=0
    )

    if api_mode == "🔹 默认LLM API":
        st.info("当前使用默认 API：智谱AI GLM-4.5-Air")
        current_api_key = DEFAULT_API_KEY
        current_api_url = DEFAULT_API_URL
        current_model = DEFAULT_MODEL

    elif api_mode == "🔹 PC系统环境 LLM API":
        # 扫描所有预设提供商
        providers = detect_env_providers()
        provider_names = [name for name, *_ in providers]

        # 找到第一个已设置 Key 的提供商作为默认选中项
        default_idx = 0
        for i, (_, has_key, *_key) in enumerate(providers):
            if has_key:
                default_idx = i
                break

        chosen_provider = st.selectbox(
            "选择 API 提供商：",
            provider_names,
            index=default_idx,
            format_func=lambda x: f"{x}  ✅ 已检测到" if providers[provider_names.index(x)][1] else f"{x}  ❌ 未设置"
        )

        # 获取选中提供商的信息
        idx = provider_names.index(chosen_provider)
        name, has_key, auto_key, auto_url, auto_model = providers[idx]

        if chosen_provider == "自定义环境变量":
            st.caption("请手动指定要读取的环境变量名（注意：不是在下方输 Key，是输变量名）")
            custom_env_key_name = st.text_input("Key 环境变量名", value="CUSTOM_ENV_KEY", placeholder="如 MY_KEY")
            custom_env_url_name = st.text_input("URL 环境变量名", value="CUSTOM_ENV_URL", placeholder="如 MY_URL")
            custom_env_model_name = st.text_input("Model 环境变量名", value="CUSTOM_ENV_MODEL", placeholder="如 MY_MODEL")
            current_api_key = os.getenv(custom_env_key_name, "")
            current_api_url = os.getenv(custom_env_url_name, "https://open.bigmodel.cn/api/paas/v4/chat/completions")
            current_model = os.getenv(custom_env_model_name, "glm-4.5-air")
        else:
            current_api_key = auto_key
            current_api_url = auto_url
            current_model = auto_model

        # 状态提示
        if current_api_key and current_api_key.strip():
            st.success(f"✅ 已从环境变量检测到 {chosen_provider} 的 API Key")
            st.caption(f"URL: {current_api_url}")
            st.caption(f"模型: {current_model}")
        else:
            env_var_name = ENV_PROVIDERS[chosen_provider][0] if chosen_provider != "自定义环境变量" else custom_env_key_name
            st.error(f"❌ 未检测到 {chosen_provider} 的 API Key（环境变量: {env_var_name}）")
            st.markdown("""
            **设置方法（Windows CMD）：**
            ```cmd
            set 变量名=你的API_Key
            ```
            **设置方法（PowerShell）：**
            ```powershell
            $env:变量名="你的API_Key"
            ```
            设置完成后请重启 Streamlit。
            """)

    else:  # 自定义LLM API
        custom_api_key = st.text_input("API Key", type="password", placeholder="请输入 API Key")
        custom_api_url = st.text_input("API URL", value="https://open.bigmodel.cn/api/paas/v4/chat/completions", placeholder="请输入 API URL")
        custom_model = st.text_input("模型名称", value="glm-4.5-air", placeholder="请输入模型名称，如 glm-4.5-air")
        st.caption("示例 URL（智谱AI）：https://open.bigmodel.cn/api/paas/v4/chat/completions")
        current_api_key = custom_api_key
        current_api_url = custom_api_url
        current_model = custom_model

    # =========================
    # 📊 游戏状态调试面板（v2.0 新增）
    # =========================
    st.divider()
    st.subheader("📊 游戏状态（调试）")
    gs: GameState = st.session_state.game_state
    st.json(gs.snapshot())


# 显示历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# 用户输入
user_input = st.chat_input('输入"开始"或"再来一局"启动游戏（明朝人物）')

if user_input:
    # 显示用户消息
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    gs: GameState = st.session_state.game_state

    # =========================
    # 🎯 游戏初始化 / 重开判断（Python 层）
    # =========================
    is_start = (not gs.target_answer) or is_replay_request(user_input) or ("开始" in user_input)

    if is_start:
        names = load_people_names()
        target = random.choice(names)

        # ✅ 用 GameState.reset() 统一重置，替代旧版散落赋值
        gs.reset(target_answer=target)

        reply = '写好了，请猜猜看，我会回答"是"或"否"'

    else:
        # =========================
        # 📊 计数（每轮+1）—— Python 层
        # =========================
        gs.increment_dialogue()

        # =========================
        # 🧠 构建 Prompt（模块化分层）
        # =========================
        # ✅ hint_mode 由 Python 计算，不再让 LLM 查表
        system_prompt = build_system_prompt(
            target_answer=gs.target_answer,
            dialogue_count=gs.dialogue_count,
            hint_mode=gs.hint_mode,  # ← Python 算好的 "blocked" / "enabled"
            theme="明朝历史",
            enable_tools=False,
        )

        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # 加入历史对话（保留上下文）
        for m in st.session_state.messages:
            messages.append(m)

        # =========================
        # 🤖 调用模型
        # =========================
        reply = call_llm(messages, current_api_key, current_api_url, current_model)

        # =========================
        # 📝 状态后处理（Python 层辅助）
        # =========================
        # 检测是否触发了提示（用于记录 hint_history 防重复）
        if is_likely_hint_request(user_input) and gs.hint_available:
            # 简单记录：把 AI 回复中"提示："之后的内容存入历史
            # （实际防重复主要靠 prompt 约束，这里仅做辅助记录）
            if "提示：" in reply:
                hint_text = reply.split("提示：", 1)[-1].strip()
                if hint_text:
                    gs.add_hint(hint_text)

        # 检测投降（Python 预判 + LLM 实际回复）
        if is_likely_surrender(user_input):
            gs.mark_surrendered()

    # 显示 AI 回复
    st.session_state.messages.append({"role": "assistant", "content": reply})

    with st.chat_message("assistant"):
        st.markdown(reply)
