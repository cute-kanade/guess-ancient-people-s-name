"""
猜中国古人（AI海龟汤 v3.0）—— 全量重构全古代 200 人版

以 app_03_01.py 为框架，知识库切换为《top200_famous_people.csv》
（中国全古代 200 名人），是 app_03_ming.py 的姊妹版本
（明朝 200 人 → 全古代 200 人），迭代掉 app_02_mini.py。

对比 app_02_mini.py 的改进：
    ✅ 架构分层：app 层只做 UI，逻辑下沉到 llm_client / game_state / people_db / fact_checker
    ✅ 降低错误率：temperature 0.3 + 事实核查强化层 + 结构化人物库事实注入
    ✅ 批量重答：输入"重答""我怀疑"等触发整段聊天记录一次性核查（分批+汇总）
    ✅ 密钥安全：移除硬编码 Key，改读环境变量 / Streamlit secrets
    ✅ 人物库升级：CSV 人名 + JSON 结构化字段合并（不补默认朝代，覆盖全朝代）

运行：
    streamlit run app_03_mini.py
"""

import streamlit as st
import random
import os

# =========================
# 🔧 Streamlit 页面配置（必须为第一个 Streamlit 命令）
# =========================
st.set_page_config(page_title="猜中国古人", page_icon="🎭")

# =========================
# 导入分层模块
# =========================
from prompts import build_system_prompt
from game_state import (
    GameState,
    GamePhase,
    is_likely_surrender,
    is_likely_hint_request,
    is_replay_request,
    is_doubt_request,
    collect_fact_qa_pairs,
)
from people_db import load_people_from_csv, get_person_by_name
from fact_checker import build_fact_check_layer_with_hints
from llm_client import LLMClient, detect_env_providers, ENV_PROVIDERS
from config import (
    resolve_default_api_key,
    DEFAULT_API_URL,
    DEFAULT_MODEL,
    ANSWER_TEMPERATURE,
    GENERAL_TEMPERATURE,
)


# =========================
# ⚙️ 全古代主题配置
# =========================
MINI_THEME = "中国历史"
MINI_CSV_PATH = "top200_famous_people.csv"
MINI_NAME_COLUMN = "人名"


# =========================
# 🎯 初始化 session_state
# =========================
def init_session_state():
    if "game_state" not in st.session_state:
        st.session_state.game_state = GameState(target_answer="")
    if "messages" not in st.session_state:
        st.session_state.messages = []


init_session_state()


# =========================
# 📄 全古代人物库加载（带缓存）
# =========================
@st.cache_data
def load_mini_people_cached():
    """加载全古代 200 名人库：CSV 人名 + JSON 结构化字段合并。

    不补默认朝代（覆盖全朝代），朝代由 JSON 结构化字段提供（若有）。
    """
    return load_people_from_csv(
        csv_path=MINI_CSV_PATH,
        name_column=MINI_NAME_COLUMN,
        default_dynasty=None,
    )


# =========================
# 🎮 Streamlit UI
# =========================
st.title("🎭 猜中国古人（AI海龟汤 v3.0 全量重构版）")
st.caption("🔧 架构分层 + 结构化人物库 + 批量重答核查 | 知识库：中国全古代 200 名人 | 旧版见 legacy/")

# =========================
# 🎚️ 侧栏：LLM API 设置
# =========================
with st.sidebar:
    st.header("⚙️ LLM API 设置")

    api_mode = st.radio(
        "选择 API 来源：",
        ["🔹 默认LLM API", "🔹 PC系统环境 LLM API", "🔹 自定义LLM API"],
        index=0,
    )

    if api_mode == "🔹 默认LLM API":
        # 安全读取 Key（不再硬编码）
        default_key = resolve_default_api_key(getattr(st, "secrets", None))
        if default_key:
            st.success("✅ 已从环境变量 / secrets 检测到 API Key")
        else:
            st.warning("⚠️ 未检测到 API Key，请在下方手动输入，或设置环境变量 LLM_API_KEY")
            manual_key = st.text_input("API Key（手动输入）", type="password", placeholder="未设置时在此输入")
            default_key = manual_key
        st.caption(f"URL: {DEFAULT_API_URL} | 模型: {DEFAULT_MODEL} | temperature: {ANSWER_TEMPERATURE}")
        current_api_key = default_key
        current_api_url = DEFAULT_API_URL
        current_model = DEFAULT_MODEL

    elif api_mode == "🔹 PC系统环境 LLM API":
        providers = detect_env_providers()
        provider_names = [name for name, *_ in providers]

        default_idx = 0
        for i, (_, has_key, *_key) in enumerate(providers):
            if has_key:
                default_idx = i
                break

        chosen_provider = st.selectbox(
            "选择 API 提供商：",
            provider_names,
            index=default_idx,
            format_func=lambda x: (
                f"{x}  ✅ 已检测到" if providers[provider_names.index(x)][1] else f"{x}  ❌ 未设置"
            ),
        )

        idx = provider_names.index(chosen_provider)
        name, has_key, auto_key, auto_url, auto_model = providers[idx]

        if chosen_provider == "自定义环境变量":
            st.caption("请手动指定要读取的环境变量名")
            custom_env_key_name = st.text_input("Key 环境变量名", value="CUSTOM_ENV_KEY")
            custom_env_url_name = st.text_input("URL 环境变量名", value="CUSTOM_ENV_URL")
            custom_env_model_name = st.text_input("Model 环境变量名", value="CUSTOM_ENV_MODEL")
            current_api_key = os.getenv(custom_env_key_name, "")
            current_api_url = os.getenv(custom_env_url_name, DEFAULT_API_URL)
            current_model = os.getenv(custom_env_model_name, DEFAULT_MODEL)
        else:
            current_api_key = auto_key
            current_api_url = auto_url
            current_model = auto_model

        if current_api_key and current_api_key.strip():
            st.success(f"✅ 已从环境变量检测到 {chosen_provider} 的 API Key")
            st.caption(f"URL: {current_api_url} | 模型: {current_model}")
        else:
            env_var_name = ENV_PROVIDERS[chosen_provider][0] if chosen_provider != "自定义环境变量" else custom_env_key_name
            st.error(f"❌ 未检测到 {chosen_provider} 的 API Key（环境变量: {env_var_name}）")
            st.markdown("""
            **设置方法（Windows CMD）：** `set 变量名=你的API_Key`
            **设置方法（PowerShell）：** `$env:变量名="你的API_Key"`
            """)

    else:  # 自定义LLM API
        custom_api_key = st.text_input("API Key", type="password", placeholder="请输入 API Key")
        custom_api_url = st.text_input("API URL", value=DEFAULT_API_URL)
        custom_model = st.text_input("模型名称", value=DEFAULT_MODEL)
        current_api_key = custom_api_key
        current_api_url = custom_api_url
        current_model = custom_model

    # =========================
    # 📊 游戏状态调试面板
    # =========================
    st.divider()
    st.subheader("📊 游戏状态（调试）")
    gs: GameState = st.session_state.game_state
    st.json(gs.snapshot())

    # =========================
    # 🔁 重答功能说明
    # =========================
    st.divider()
    st.subheader("🔁 批量重答核查")
    st.caption('若认为 AI 回答有误，输入"重答""我怀疑""你确定吗""答案不对"等触发整段聊天记录一次性核查。')
    st.caption('核查会逐条复核所有已发生的"是/否/或许"问答，并附更正摘要。')


# =========================
# 💬 显示历史消息
# =========================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# =========================
# ⌨️ 用户输入
# =========================
user_input = st.chat_input('输入"开始"或"再来一局"启动游戏（中国古人）；怀疑答案可输入"重答""我怀疑"等')

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    gs: GameState = st.session_state.game_state
    client = LLMClient(current_api_key, current_api_url, current_model)

    # =========================
    # 🎯 游戏初始化 / 重开
    # =========================
    is_start = (not gs.target_answer) or is_replay_request(user_input) or ("开始" in user_input)

    if is_start:
        persons = load_mini_people_cached()
        if not persons:
            st.error("人物库加载失败，请确认 top200_famous_people.csv 文件存在。")
            persons = [type("P", (), {"name": "王阳明"})()]  # 紧急 fallback
        target_person = random.choice(persons)
        gs.reset(target_answer=target_person.name)

        reply = '写好了，请猜猜看，我会回答"是"或"否"'

    # =========================
    # 🔁 v3.0：批量重答核查分支（不计入有效提问次数）
    # =========================
    elif is_doubt_request(user_input):
        if not gs.target_answer:
            reply = '游戏还没开始，请输入"开始"启动一局。'
        else:
            qa_pairs = collect_fact_qa_pairs(st.session_state.messages)
            if not qa_pairs:
                reply = "当前没有可核查的提问。请先正常提问，再对回答表示怀疑。"
            else:
                with st.status("🔍 正在对整段聊天记录进行二次核查...", expanded=True) as status:
                    progress_holder = st.empty()

                    def on_progress(done, total):
                        progress_holder.write(f"已完成第 {done}/{total} 批...")

                    reply = client.recheck_batch(
                        target_answer=gs.target_answer,
                        messages=st.session_state.messages,
                        on_progress=on_progress,
                    )
                    status.update(label="✅ 核查完成", state="complete")

    else:
        # =========================
        # 📊 有效提问计数 +1
        # =========================
        gs.increment_dialogue()

        # =========================
        # 🧠 构建 Prompt（分层 + 事实核查强化 + 结构化事实注入）
        # =========================
        system_prompt = build_system_prompt(
            target_answer=gs.target_answer,
            dialogue_count=gs.dialogue_count,
            hint_mode=gs.hint_mode,
            theme=MINI_THEME,
            enable_tools=False,
            enable_fact_check=False,  # 事实核查层带人物提示在下方单独注入
        )

        # v3.0：注入结构化人物事实（若有）
        persons = load_mini_people_cached()
        target_person = get_person_by_name(gs.target_answer, persons)
        fact_layer = build_fact_check_layer_with_hints(target_person)
        system_prompt = system_prompt + "\n\n" + fact_layer

        messages = [{"role": "system", "content": system_prompt}]
        for m in st.session_state.messages:
            messages.append(m)

        # =========================
        # 🤖 调用模型
        # =========================
        current_temp = GENERAL_TEMPERATURE if gs.phase != GamePhase.PLAYING else ANSWER_TEMPERATURE
        reply = client.answer(messages, temperature=current_temp)

        # =========================
        # 📝 状态后处理
        # =========================
        if is_likely_hint_request(user_input) and gs.hint_available:
            if "提示：" in reply:
                hint_text = reply.split("提示：", 1)[-1].strip()
                if hint_text:
                    gs.add_hint(hint_text)

        if is_likely_surrender(user_input):
            gs.mark_surrendered()
            
        if "恭喜" in reply and "答对" in reply:
            gs.mark_won()

    # 显示 AI 回复
    st.session_state.messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.markdown(reply)
