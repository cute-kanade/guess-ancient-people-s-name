"""
猜中国古人（AI海龟汤 v2.02）—— 降错率 + 重答疑惑版

基于 app_02_01.py 的改进：
    ✅ 降低 AI 回答错误率：
       - temperature 0.7 → 0.3（更严谨、更确定性）
       - 新增【事实核查强化层】：强制 LLM 在回答前先默想事实依据
       - 强化规则层：对"XX之称 / 几大名将"等固定头衔明确警示
    ✅ 增加重答疑惑答案的选项：
       - 玩家可用"重答""我怀疑""你确定吗""答案不对"等触发重新核查
       - 触发后 AI 以"二次核查"模式重新评估上一条问题，
         并给出"维持原判 / 更正为XX"及简要理由，便于玩家复核
       - 重答不计入有效提问次数（dialogue_count 不自增）

复用模块（不改共享代码）：
    prompts/         —— 模块化 Prompt（本文件在调用后追加强化层）
    game_state.py    —— Python 状态逻辑
"""

import streamlit as st
import random
import requests
import os

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

# 默认 LLM API（智谱AI GLM-4-Air）
DEFAULT_API_KEY = "2decccf007f4414b8c71cda0b8e3cf26.TeiHdRMi4Pxs1Fx3"
DEFAULT_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-4-air"

# v2.02：降低 temperature 以减少事实性错误
ANSWER_TEMPERATURE: float = 0.3
# 重答核查用更低 temperature，追求最严谨
RECHECK_TEMPERATURE: float = 0.1

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
    # v2.02：记录上一条"待核查"的玩家提问，供重答使用
    if "last_user_question" not in st.session_state:
        st.session_state.last_user_question = ""


init_session_state()


# =========================
# 🧠 v2.02：事实核查强化层（追加在标准 system prompt 之后）
# =========================
def build_fact_check_layer() -> str:
    """构建事实核查强化层 prompt。

    该层在标准分层 prompt 基础上追加，进一步降低 AI 回答错误率：
        - 强制"先默想、再回答"的两步机制
        - 对固定历史头衔、并列称谓给出明确警示
        - 对不确定的事实允许使用"或许是 / 或许不是"而非冒险下判断
    """
    return """【事实核查强化规则（v2.02 新增）】
为了最大限度降低回答错误率，你在每次回答前【必须】执行以下两步：
第一步（默想，不输出）：在内心默想该问题针对【目标人物】是否成立，回忆其朝代、身份、主要事迹、是否有特定头衔。
第二步（输出）：基于默想结果，只返回【回答规则】允许的五种内容之一。

特别警示（高频错误场景）：
1. 涉及"XX四杰""几大名将""唐宋八大家""XX之称"等固定并列头衔时，必须先确认目标人物是否确实在该并列名单中，再回答"是"或"否"。若不确定，宁可回答"或许是"或"或许不是"，绝不冒险。
2. 涉及朝代、生卒年、籍贯等可查证事实时，若记忆模糊，优先使用"或许是 / 或许不是"，避免给出错误的"是 / 否"。
3. 涉及人物关系（父子、君臣、师徒、政敌）时，先在内心交叉验证，再回答。
4. 若玩家的问题表述本身有歧义，回答"无可奉告，换个问法吧。"。

【绝对禁止】
- 禁止在输出中展示你的"默想过程"，玩家只能看到最终的那五种回答之一。
- 禁止凭借模糊印象直接回答"是"或"否"——宁可保守，不可错答。"""


# =========================
# 🔁 v2.02：重答核查 prompt
# =========================
def build_recheck_prompt(target_answer: str, questioned_question: str, previous_answer: str) -> str:
    """构建重答核查 system prompt。

    当玩家对上一条 AI 回答产生怀疑时，使用该 prompt 让 AI 进入
    "二次核查"模式：重新评估、给出维持或更正结论及简要理由。

    Args:
        target_answer: 本局目标人物。
        questioned_question: 被怀疑的那条玩家提问。
        previous_answer: AI 上一次给出的回答。

    Returns:
        重答核查 system prompt。
    """
    return f"""你是严谨的历史事实核查员。玩家对你刚才在"海龟汤"游戏中的回答产生了怀疑，请你重新核查。

【最高机密】本局目标人物：{target_answer}

【被怀疑的玩家提问】
{questioned_question}

【你上一次的回答】
{previous_answer}

【二次核查要求】
1. 针对目标人物【{target_answer}】，重新核实该提问的事实真相。
2. 比对你上一次的回答是否正确。
3. 严格按以下格式输出（不要输出其他任何内容）：

🔍 二次核查结果：[维持原判 / 更正为：是。 / 更正为：否。 / 更正为：或许是。 / 更正为：或许不是。 / 更正为：无可奉告，换个问法吧。]
📝 核查依据：[用 40 个字以内简述事实依据，例如该人物的朝代/身份/事迹/是否属于某固定头衔]
⚠️ 若你无法确定，请输出"更正为：或许是。"或"更正为：或许不是。"，绝不冒险给出错误的"是/否"。

记住：宁可保守，不可错答。"""


# =========================
# 🕵️ v2.02：检测玩家是否怀疑上一条答案
# =========================
def is_doubt_request(user_input: str) -> bool:
    """检测玩家是否在质疑上一条 AI 回答、请求重答。

    Args:
        user_input: 玩家输入文本。

    Returns:
        是否疑似怀疑 / 请求重答。
    """
    doubt_keywords = [
        "重答", "重新回答", "重新判断", "再确认一下", "再确认",
        "我怀疑", "答案不对", "答错了吧", "你答错了", "不对吧",
        "你确定吗", "确定吗", "真的吗", "再想想", "再核实一下",
        "我觉得不对", "不可能吧", "重新评估",
    ]
    text = user_input.strip().lower()
    return any(kw in text for kw in doubt_keywords)


def find_last_user_question(messages: list[dict]) -> tuple[str, str]:
    """从历史消息中找到上一条玩家提问及其对应的 AI 回答。

    Returns:
        (上一条玩家提问, 上一条 AI 回答)；若找不到返回 ("", "")。
    """
    last_user = ""
    last_assistant = ""
    # 从后往前找，跳过最后一条（即当前刚追加的怀疑输入）
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m["role"] == "user" and not is_doubt_request(m["content"]):
            last_user = m["content"]
            # 找到紧随其后的 assistant 回复
            for j in range(i + 1, len(messages)):
                if messages[j]["role"] == "assistant":
                    last_assistant = messages[j]["content"]
                    break
            break
    return last_user, last_assistant


# =========================
# 🤖 调用 LLM API（通用，v2.02 支持自定义 temperature）
# =========================
def call_llm(messages, api_key, api_url, model, temperature=ANSWER_TEMPERATURE):
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
                "temperature": temperature
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

st.title("🎭 猜中国古人（AI海龟汤 v2.02 降错率+重答版）")
st.caption("🔧 对比 v2.01：降低 temperature、新增事实核查强化层、支持对疑惑答案请求重答")

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
        st.info("当前使用默认 API：智谱AI GLM-4-Air（temperature=0.3 严谨模式）")
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

    # =========================
    # 📊 游戏状态调试面板（v2.0 新增）
    # =========================
    st.divider()
    st.subheader("📊 游戏状态（调试）")
    gs: GameState = st.session_state.game_state
    st.json(gs.snapshot())

    # v2.02：重答功能说明
    st.divider()
    st.subheader("🔁 重答疑惑答案")
    st.caption('若你认为 AI 刚才回答有误，可输入"重答""我怀疑""你确定吗""答案不对"等触发重新核查。')
    st.caption(f"待核查的上一个问题：{st.session_state.last_user_question or '（暂无）'}")


# 显示历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# 用户输入
user_input = st.chat_input('输入"开始"或"再来一局"启动游戏；怀疑答案可输入"重答""我怀疑"等')
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
        st.session_state.last_user_question = ""

        reply = '写好了，请猜猜看，我会回答"是"或"否"'

    # =========================
    # 🔁 v2.02：重答疑惑答案分支（不计入有效提问次数）
    # =========================
    elif is_doubt_request(user_input):
        if not gs.target_answer:
            reply = '游戏还没开始，请输入"开始"启动一局。'
        else:
            questioned_question, previous_answer = find_last_user_question(st.session_state.messages)
            if not questioned_question:
                reply = "没有找到上一条可核查的提问。请先正常提问，再对回答表示怀疑。"
            else:
                # 构建重答核查 prompt，使用更低 temperature
                recheck_system = build_recheck_prompt(
                    target_answer=gs.target_answer,
                    questioned_question=questioned_question,
                    previous_answer=previous_answer or "（未记录）",
                )
                recheck_messages = [
                    {"role": "system", "content": recheck_system},
                    {"role": "user", "content": f"请重新核查我刚才的问题：{questioned_question}"},
                ]
                reply = call_llm(
                    recheck_messages,
                    current_api_key,
                    current_api_url,
                    current_model,
                    temperature=RECHECK_TEMPERATURE,
                )

    else:
        # =========================
        # 📊 计数（每轮+1）—— Python 层
        # =========================
        gs.increment_dialogue()
        # 记录本轮提问，供重答使用
        st.session_state.last_user_question = user_input

        # =========================
        # 🧠 构建 Prompt（模块化分层 + v2.02 事实核查强化层）
        # =========================
        # ✅ hint_mode 由 Python 计算，不再让 LLM 查表
        system_prompt = build_system_prompt(
            target_answer=gs.target_answer,
            dialogue_count=gs.dialogue_count,
            hint_mode=gs.hint_mode,  # ← Python 算好的 "blocked" / "enabled"
            theme="历史",
            enable_tools=False,
        )
        # v2.02：追加事实核查强化层
        system_prompt = system_prompt + "\n\n" + build_fact_check_layer()

        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # 加入历史对话（保留上下文）
        for m in st.session_state.messages:
            messages.append(m)

        # =========================
        # 🤖 调用模型（v2.02：使用更低的 temperature）
        # =========================
        reply = call_llm(
            messages,
            current_api_key,
            current_api_url,
            current_model,
            temperature=ANSWER_TEMPERATURE,
        )

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
