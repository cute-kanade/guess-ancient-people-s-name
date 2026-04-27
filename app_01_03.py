import streamlit as st
import random
import requests
import os

# =========================
# ⚙️ 基础配置
# =========================

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")  # 建议用环境变量
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

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

查表 A 组：如果 N 是 1, 2, 3, 4, 5, 6, 7 中的一个数字，说明次数不足。
【强制回复动作】：只准回复"目前系统记录轮数为 N，有效提问次数尚不足，暂不提供提示，请继续提问。"（警告：严禁在回复中编造"因为 X 小于 Y"之类的废话逻辑！）

查表 B 组：如果 N 是 8, 9, 10, 11, 12, 13, 14, 15 或更大数字，说明次数达标。
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
# 🤖 调用 DeepSeek API
# =========================
def call_deepseek(messages):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            DEEPSEEK_URL,
            headers=headers,
            json={
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": 0.7
            },
            timeout=30
        )

        data = response.json()

        return data["choices"][0]["message"]["content"]

    except Exception as e:
        return f"API调用失败: {e}"


# =========================
# 🎮 Streamlit UI
# =========================

st.title("🎭 猜中国古人（AI海龟汤 v1.2）")

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
        reply = call_deepseek(messages)

    # 显示 AI 回复
    st.session_state.messages.append({"role": "assistant", "content": reply})

    with st.chat_message("assistant"):
        st.markdown(reply)
