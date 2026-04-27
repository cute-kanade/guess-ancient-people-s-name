import streamlit as st
import random
import requests
import os

# =========================
# ⚙️ 基础配置
# =========================

# 默认 LLM API（智谱AI GLM-4-Air）
DEFAULT_API_KEY = "2decccf007f4414b8c71cda0b8e3cf26.TeiHdRMi4Pxs1Fx3"
DEFAULT_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-4-air"

# PC 系统环境 LLM API（多提供商自动探测）
# 格式: { 显示名: (环境变量名, 默认URL, 默认模型) }
ENV_PROVIDERS = {
    "DeepSeek":        ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1/chat/completions", "deepseek-chat"),
    "OpenAI":          ("OPENAI_API_KEY",   "https://api.openai.com/v1/chat/completions",   "gpt-4o-mini"),
    "智谱AI (GLM)":     ("ZHIPU_API_KEY",    "https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm-4-air"),
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
            model = os.getenv("CUSTOM_ENV_MODEL", "glm-4-air")
            has_key = bool(key and key.strip())
        else:
            key = os.getenv(env_var, "")
            has_key = bool(key and key.strip())
        results.append((name, has_key, key, url, model))
    return results

# =========================
# 📄 读取人物库
# =========================
def load_people_names():
    try:
        with open("peoples_names.md", "r", encoding="utf-8") as f:
            names = [line.strip() for line in f if line.strip()]
            return names
    except Exception as e:
        st.error(f"人物库加载失败: {e}")
        return ["王阳明"]  # fallback


# =========================
# 🎯 初始化 session_state
# =========================
if "target_answer" not in st.session_state:
    st.session_state.target_answer = ""

if "dialogue_count" not in st.session_state:
    st.session_state.dialogue_count = 0

if "messages" not in st.session_state:
    st.session_state.messages = []

if "game_active" not in st.session_state:
    st.session_state.game_active = False


# =========================
# 🧠 System Prompt（四大铁律版 v1.2）
# =========================
def build_system_prompt(target_answer, N):
    return f"""你是一个冷酷、极其死板的历史"海龟汤"考官。
【最高机密】本局的唯一正确答案是:{target_answer}。绝对禁止在玩家完全猜中前以任何形式泄露。

【当前系统状态】
系统记录的当前对话轮数（N）: {N}

【四大铁律（作为机器，你必须严格遵守，不可违背，不可自我矛盾）】

铁律一：常规提问（只答是非）
当玩家询问目标人物的特征（如：是男的吗？唐朝的吗？文臣吗？）或猜测了错误的人名时，你【必须且只能】回复以下五种内容之一，严禁多加任何解释文字或标点符号：
1. 是。
2. 否。
3. 或许是。
4. 或许不是。
5. 无可奉告，换个问法吧。
（注：在回答'是'或'否'之前，请在内心先进行一次事实核查，尤其是涉及'XX之称'、'几大名将'等固定历史头衔时。）

铁律二：玩家求助与提示判定（绝对禁止进行数学大小计算）
当玩家明确发送"求提示"、"给点线索"、"猜不出"等【索要提示】的词汇时，你必须且只能根据上方的【当前系统状态】数字 N，进行"查表判定"：

查表 A 组：如果 N 是 1, 2, 3, 4, 5 中的一个数字，说明次数不足。
【强制回复动作】：只准回复"目前系统记录轮数为 N，有效提问次数尚不足，暂不提供提示，请继续提问。"（警告：严禁在回复中编造"因为 X 小于 Y"之类的废话逻辑！）

查表 B 组：如果 N 是 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 或更大数字，说明次数达标。
【强制回复动作】：回复"提问已达标！考官给你一个提示：[在此处结合目标人物的生平，提供一个不包含该人名的典故或特征]。"
【绝不重复警告】：若玩家多次触发查表 B 组，你每次给出的提示【必须完全不同】！请强制切换信息维度（例如：第一次提示朝代背景，第二次提示关联人物，第三次提示特殊官职、死因或著名癖好），确保每次生成的新提示绝对不与之前的提示重复。

铁律三：胜利结算
只有当玩家输入的名字与【{target_answer}】是同一个人时，触发胜利机制：
【强制回复动作】：立刻切换为热情语气大声宣布："🎉 恭喜你，完全正确！答案正是【{target_answer}】！[此处用 50 个以内字简短科普 TA 的功绩]。还要再来一局吗？请输入'再来一局'。"，并在用户发送"再来一局"前，暂时转为通用人工智能状态。

铁律四：玩家投降机制
当玩家明确发送"我投降"、"公布答案吧"、"不猜了直接告诉我"等【直接放弃游戏】的词汇时，触发投降机制：
【强制回复动作】：以冷酷、居高临下的考官语气进行一句简短的嘲讽（如："看来你的历史知识不过如此。"），然后直接公布："本局的正确答案是【{target_answer}】。[此处用 50 个以内字简短科普 TA 的功绩]。还要再来一局吗？请输入'再来一局'。"
"""


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

st.title("🎭 猜中国古人（AI海龟汤 v1.2）")

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
        st.info("当前使用默认 API：智谱AI GLM-4-Air")
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
            current_model = os.getenv(custom_env_model_name, "glm-4-air")
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
        custom_model = st.text_input("模型名称", value="glm-4-air", placeholder="请输入模型名称，如 glm-4-air")
        st.caption("示例 URL（智谱AI）：https://open.bigmodel.cn/api/paas/v4/chat/completions")
        current_api_key = custom_api_key
        current_api_url = custom_api_url
        current_model = custom_model

# 显示历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# 用户输入
user_input = st.chat_input('输入"开始"或"再来一局"启动游戏')

if user_input:
    # 显示用户消息
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # =========================
    # 🎯 游戏初始化判断（对应 if-else）
    # =========================
    if (not st.session_state.target_answer) or ("再来一局" in user_input) or ("开始" in user_input):
        names = load_people_names()
        target = random.choice(names)

        st.session_state.target_answer = target
        st.session_state.dialogue_count = 0
        st.session_state.game_active = True

        reply = '写好了，请猜猜看，我会回答"是"或"否"'

    else:
        # =========================
        # 📊 计数（每轮+1）
        # =========================
        st.session_state.dialogue_count += 1

        # =========================
        # 🧠 构建 Prompt
        # =========================
        system_prompt = build_system_prompt(
            st.session_state.target_answer,
            st.session_state.dialogue_count
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

    # 显示 AI 回复
    st.session_state.messages.append({"role": "assistant", "content": reply})

    with st.chat_message("assistant"):
        st.markdown(reply)
