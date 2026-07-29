import streamlit as st
import random
import requests
import csv

# =========================
# 🔧 Streamlit 页面配置（必须为第一个 Streamlit 命令）
# =========================
st.set_page_config(page_title="猜明朝人物", page_icon="🎭")

# =========================
# ⚙️ LLM 提供商注册表
# =========================
LLM_PROVIDER_REGISTRY = {
    "zhipu": {
        "name": "智谱AI GLM-4.5-Air",
        "default_model": "glm-4.5-air",
        "default_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    },
    "deepseek": {
        "name": "DeepSeek",
        "default_model": "deepseek-chat",
        "default_url": "https://api.deepseek.com/v1/chat/completions",
    },
    "openai": {
        "name": "OpenAI GPT-4o",
        "default_model": "gpt-4o",
        "default_url": "https://api.openai.com/v1/chat/completions",
    },
    "qwen": {
        "name": "通义千问 Qwen",
        "default_model": "qwen-turbo",
        "default_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    },
    "moonshot": {
        "name": "月之暗面 Kimi",
        "default_model": "moonshot-v1-8k",
        "default_url": "https://api.moonshot.cn/v1/chat/completions",
    },
    "baichuan": {
        "name": "百川智能 Baichuan4",
        "default_model": "Baichuan4",
        "default_url": "https://api.baichuan-ai.com/v1/chat/completions",
    },
    "ernie": {
        "name": "百度文心一言 ERNIE",
        "default_model": "ernie-3.5",
        "default_url": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions",
    },
}

# =========================
# 🔧 默认配置（无 URL 参数时使用）
# =========================
DEFAULT_PROVIDER = "zhipu"
DEFAULT_API_KEY = ""
DEFAULT_MODEL = "glm-4.5-air"
DEFAULT_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


def get_config_from_query_params():
    """
    从 Streamlit URL 查询参数中读取 LLM 配置。
    若有外部传入则使用外部值；否则使用默认值（智谱 GLM-4.5-Air）。
    """
    params = st.query_params

    provider_id = params.get("provider", DEFAULT_PROVIDER)
    api_key = params.get("api_key", DEFAULT_API_KEY)
    model = params.get("model", DEFAULT_MODEL)
    api_url = params.get("api_url", DEFAULT_API_URL)

    # 验证 provider 是否在注册表中
    if provider_id not in LLM_PROVIDER_REGISTRY:
        st.warning(f"⚠️ 未知的 LLM 提供商 '{provider_id}'，已回退到默认值。")
        provider_id = DEFAULT_PROVIDER
        model = DEFAULT_MODEL
        api_url = DEFAULT_API_URL

    # 若 model 或 api_url 为空，从注册表补全
    if not model.strip():
        model = LLM_PROVIDER_REGISTRY.get(provider_id, {}).get("default_model", DEFAULT_MODEL)
    if not api_url.strip():
        api_url = LLM_PROVIDER_REGISTRY.get(provider_id, {}).get("default_url", DEFAULT_API_URL)

    return {
        "provider_id": provider_id,
        "provider_name": LLM_PROVIDER_REGISTRY.get(provider_id, {}).get("name", provider_id),
        "api_key": api_key,
        "model": model,
        "api_url": api_url,
    }


# =========================
# 📄 读取人物库
# =========================
def load_people_names():
    """依次尝试多种编码读取 CSV 文件，兼容 UTF-8、GBK 等编码"""
    encodings_to_try = ["utf-8", "gbk", "gb2312", "gb18030"]
    for enc in encodings_to_try:
        try:
            with open("明朝名人二百人表 - 明朝名人二百人表.csv", "r", encoding=enc) as f:
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

if "config_loaded" not in st.session_state:
    st.session_state.config_loaded = False

# --- 加载配置（仅首次） ---
if not st.session_state.config_loaded:
    st.session_state.llm_config = get_config_from_query_params()
    st.session_state.config_loaded = True

config = st.session_state.llm_config


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
def call_llm(messages, config):
    """通用 LLM API 调用，根据配置动态切换提供商。"""
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": 0.7
    }

    # 智谱 API 需要 max_tokens（部分模型必需）
    if config["provider_id"] == "zhipu":
        payload["max_tokens"] = 1024

    try:
        response = requests.post(
            config["api_url"],
            headers=headers,
            json=payload,
            timeout=30
        )

        data = response.json()

        # 处理各提供商的错误响应
        if "error" in data:
            error_msg = data["error"]
            if isinstance(error_msg, dict):
                return f"API 错误: {error_msg.get('message', str(error_msg))}"
            return f"API 错误: {error_msg}"

        # 标准 OpenAI 兼容格式
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]

        # 不支持的响应格式
        return f"⚠️ 未识别的 API 响应格式，请检查模型与端点是否正确。原始响应: {str(data)[:300]}"

    except requests.exceptions.Timeout:
        return "⏰ API 调用超时，请检查网络或重试。"
    except requests.exceptions.ConnectionError:
        return "🔌 无法连接 API 服务器，请检查端点 URL 是否正确。"
    except Exception as e:
        return f"❌ API调用失败: {e}"


# =========================
# 🎮 Streamlit UI
# =========================

st.title("🎭 猜明朝人物（AI海龟汤）")

# 侧边栏：显示当前 LLM 配置
with st.sidebar:
    st.markdown("### ⚙️ 当前 LLM 配置")
    st.markdown(f"**提供商:** {config['provider_name']}")
    st.markdown(f"**模型:** `{config['model']}`")
    api_key_display = config['api_key'][:12] + "..." if len(config['api_key']) > 12 else config['api_key']
    st.markdown(f"**API Key:** `{api_key_display}`")
    st.markdown(f"**端点:** `{config['api_url'][:40]}...`")
    st.divider()
    st.markdown("💡 可通过主页面重新选择模型并刷新页面来切换配置。")
    st.caption(f"Provider ID: {config['provider_id']}")

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
        reply = call_llm(messages, config)

    # 显示 AI 回复
    st.session_state.messages.append({"role": "assistant", "content": reply})

    with st.chat_message("assistant"):
        st.markdown(reply)