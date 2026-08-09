"""
睿链 AI · FA Agent MVP (v0.1)
三个核心环节：BP上传解析 → 智能匹配 → 匹配报告生成

启动方式：
    pip install -r requirements.txt
    export DEEPSEEK_API_KEY="你的key"   # 不设置也能跑，会自动降级为关键词规则模式
    streamlit run app.py
"""
import os
import json
import streamlit as st
from dotenv import load_dotenv

from modules.llm_client import LLMClient
from modules.bp_parser import extract_text_from_file, parse_bp
from modules.matcher import load_institutions, match_institutions
from modules.report_generator import generate_match_reasons, export_markdown
from modules.agent_check import check_missing_info
from modules.contact_matcher import parse_contact_list, score_contacts
from modules.institution_verifier import verify_institution
from modules.outreach_drafter import draft_institution_outreach, draft_contact_followup
from modules.pitch_practice import INVESTOR_STYLES, get_next_question, generate_feedback

AGENT_MAX_ROUNDS = 2  # 最多追问2轮，避免无限循环烦到用户

load_dotenv()

st.set_page_config(page_title="睿链 AI · FA Agent", page_icon="🔗", layout="wide")

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "institutions.json")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------- 示例BP：用睿链AI自己的BP做演示案例，方便评委/观众一键体验 ----------
DEMO_BP = {
    "company_name": "睿链 AI",
    "sectors": ["人工智能", "企业服务/SaaS"],
    "stage": "天使轮",
    "funding_ask_wan": 100.0,
    "valuation_wan": 0.0,
    "business_summary": "面向FA机构与融资企业的AI Agent，沉淀赛道数据库，做智能匹配与定制化建议报告，按项目收费",
    "highlights": [
        "赛道-机构-企业三方数据库持续沉淀，形成数据飞轮",
        "从提交需求到拿到匹配清单压缩至48小时",
        "按项目收费，不改变FA行业信任逻辑，只提升效率上限",
    ],
    "team_background": "创始人陈彬彬（Solo Founder），正通过奇绩创坛创业营寻找AI/NLP方向技术合伙人",
    "risks_or_gaps": [
        "早期Solo Founder项目，核心技术合伙人尚未到位",
        "赛道数据库处于冷启动阶段，匹配精度尚无真实成交数据验证",
    ],
    "_source": "demo_preset",
}

# 故意留了信息缺口的示例，专门用来演示"Agent主动追问"这个功能
INCOMPLETE_DEMO_BP = {
    "company_name": "某AI硬件初创公司",
    "sectors": [],
    "stage": "",
    "funding_ask_wan": 0,
    "valuation_wan": 0,
    "business_summary": "未提供",
    "highlights": ["核心团队有大厂芯片研发背景"],
    "team_background": "未提供",
    "risks_or_gaps": ["这是一份信息不全的模拟BP，用于演示Agent主动追问功能"],
    "_source": "demo_preset_incomplete",
}

# ---------- 极简品牌样式（不依赖外部资源，纯CSS） ----------
st.markdown("""
<style>
    .block-container {padding-top: 2rem;}
    h1 {font-weight: 700 !important;}
    .stTabs [data-baseweb="tab"] {font-size: 1rem; padding: 0.5rem 1.2rem;}
    div[data-testid="stMetricValue"] {color: #4F46E5;}
</style>
""", unsafe_allow_html=True)


# ---------- 侧边栏：LLM配置状态 & 机构库信息 ----------
with st.sidebar:
    st.markdown("### ⚙️ 系统状态")
    llm = LLMClient()
    if llm.available:
        st.success(f"LLM 已连接（{llm.model}）")
    else:
        st.warning("未配置 DEEPSEEK_API_KEY，当前为关键词规则降级模式，建议配置后获得更准确的解析与匹配理由。")
        with st.expander("如何配置"):
            st.code('export DEEPSEEK_API_KEY="sk-xxxx"', language="bash")

    institutions = load_institutions(DATA_PATH)
    st.markdown("### 📊 机构数据库")
    st.metric("已收录机构数", len(institutions))
    st.caption("当前为公开信息拼接的种子库，建议后续接入真实成交/反馈数据持续校准。")


# ---------- 主流程 ----------
st.title("🔗 睿链 AI · FA Agent")
st.caption("让每一份 BP，在 48 小时内遇见对的资本。MVP v0.1 · 赛道数据库 · AI智能匹配 · 定制化建议报告")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["① 上传 BP", "② 智能匹配", "③ 匹配报告", "④ 路演联系人匹配", "⑤ 投资人话术演练"]
)

if "bp_data" not in st.session_state:
    st.session_state.bp_data = None
if "matches" not in st.session_state:
    st.session_state.matches = None
if "agent_questions" not in st.session_state:
    st.session_state.agent_questions = None
if "agent_round" not in st.session_state:
    st.session_state.agent_round = 0
if "contact_result" not in st.session_state:
    st.session_state.contact_result = None
if "verify_results" not in st.session_state:
    st.session_state.verify_results = {}
if "outreach_drafts" not in st.session_state:
    st.session_state.outreach_drafts = {}  # 机构名/联系人名 -> 草拟文案
if "pitch_history" not in st.session_state:
    st.session_state.pitch_history = []
if "pitch_feedback" not in st.session_state:
    st.session_state.pitch_feedback = None


def run_agent_check(bp_data):
    """跑一次Agent自检，把结果存进session_state。"""
    with st.spinner("🤖 Agent 正在检查信息是否足够支撑精准匹配..."):
        st.session_state.agent_questions = check_missing_info(bp_data, llm)

with tab1:
    st.subheader("上传企业 BP")

    demo_col, upload_col = st.columns([1, 2])
    with demo_col:
        st.markdown("**没有BP文件？先体验一下：**")
        if st.button("🎯 一键加载示例（睿链AI 自己的BP）", use_container_width=True):
            st.session_state.bp_data = dict(DEMO_BP)
            st.session_state.matches = None
            st.session_state.agent_round = 0
            st.session_state.pop("report_md", None)
            run_agent_check(st.session_state.bp_data)
            st.rerun()
        st.caption("用睿链AI自己的融资BP作为示例，跑一遍完整的解析→匹配→报告流程")

        if st.button("🤖 体验 Agent 主动追问（模拟信息不全的BP）", use_container_width=True):
            st.session_state.bp_data = dict(INCOMPLETE_DEMO_BP)
            st.session_state.matches = None
            st.session_state.agent_round = 0
            st.session_state.pop("report_md", None)
            run_agent_check(st.session_state.bp_data)
            st.rerun()
        st.caption("特意留了信息缺口的模拟BP，能看到Agent自己判断该问什么、为什么问")

    with upload_col:
        uploaded = st.file_uploader("或上传真实 BP，支持 PDF / PPTX 格式", type=["pdf", "pptx"])

    if uploaded is not None:
        save_path = os.path.join(UPLOAD_DIR, uploaded.name)
        with open(save_path, "wb") as f:
            f.write(uploaded.getbuffer())
        st.success(f"已接收文件：{uploaded.name}")

        if st.button("开始解析", type="primary"):
            with st.spinner("正在提取文本并结构化解析..."):
                try:
                    raw_text = extract_text_from_file(save_path)
                    if not raw_text.strip():
                        st.error("未能从文件中提取到文本，请确认文件是否为纯图片版PDF（暂不支持OCR）。")
                    else:
                        bp_data = parse_bp(raw_text, llm)
                        st.session_state.bp_data = bp_data
                        st.session_state.matches = None  # 重新解析后清空旧匹配结果
                        st.session_state.agent_round = 0
                        run_agent_check(bp_data)
                except Exception as e:
                    st.error(f"解析失败：{e}")

    # ---------- Agent 主动追问区块：信息不全时，先问再往下走 ----------
    if (
        st.session_state.bp_data
        and st.session_state.agent_questions
        and st.session_state.agent_round < AGENT_MAX_ROUNDS
    ):
        st.markdown("---")
        with st.container(border=True):
            st.markdown("#### 🤖 Agent 追问：这几个信息不确认清楚，匹配质量会打折扣")
            st.caption("这是Agent自己检查后判断需要确认的点，不是随便问的——每条都写了为什么重要。")

            answers = {}
            with st.form("agent_followup_form"):
                for q in st.session_state.agent_questions:
                    st.markdown(f"**{q['question']}**")
                    st.caption(f"💡 为什么问这个：{q.get('why_it_matters', '')}")
                    answers[q["field"]] = st.text_input(
                        "你的回答", key=f"agent_answer_{q['field']}_{st.session_state.agent_round}",
                        label_visibility="collapsed",
                    )
                submitted = st.form_submit_button("提交补充信息，让Agent重新判断", type="primary")

            if submitted:
                bp = st.session_state.bp_data
                for field, answer in answers.items():
                    if not answer.strip():
                        continue
                    if field == "funding_ask_wan":
                        # 尝试从回答里提取数字，提取不到就原样存进business_summary里当补充说明
                        import re as _re
                        m = _re.search(r"(\d+(?:\.\d+)?)", answer)
                        if m:
                            bp["funding_ask_wan"] = float(m.group(1))
                    elif field == "sectors":
                        bp["sectors"] = list(set(bp.get("sectors", []) + [answer.strip()]))
                    elif field == "stage":
                        for s in ["天使轮", "Pre-A轮", "A轮", "B轮", "C轮+"]:
                            if s in answer:
                                bp["stage"] = s
                                break
                    elif field == "business_summary":
                        bp["business_summary"] = answer.strip()
                st.session_state.bp_data = bp
                st.session_state.agent_round += 1
                run_agent_check(bp)  # 补充完再检查一遍，看Agent还有没有其他疑问
                st.rerun()

    if st.session_state.bp_data:
        bp = st.session_state.bp_data
        st.markdown("---")
        if st.session_state.agent_questions and st.session_state.agent_round >= AGENT_MAX_ROUNDS:
            st.caption("🤖 已追问2轮，剩余信息缺口请在下方表单里手动补充确认。")
        elif st.session_state.agent_round > 0:
            st.caption("🤖 Agent 已确认信息基本完整，可以直接进入匹配，或在下方微调。")
        st.markdown("#### 解析结果（可手动修正后再进入匹配）")

        col1, col2 = st.columns(2)
        with col1:
            bp["company_name"] = st.text_input("公司名称", bp.get("company_name", ""))
            bp["stage"] = st.selectbox(
                "融资阶段",
                ["天使轮", "Pre-A轮", "A轮", "B轮", "C轮+"],
                index=["天使轮", "Pre-A轮", "A轮", "B轮", "C轮+"].index(bp.get("stage", "A轮"))
                if bp.get("stage") in ["天使轮", "Pre-A轮", "A轮", "B轮", "C轮+"] else 2,
            )
            bp["funding_ask_wan"] = st.number_input("本轮融资金额（万元）", value=float(bp.get("funding_ask_wan", 0)), step=100.0)
        with col2:
            all_sectors = ["硬科技", "半导体", "人工智能", "医疗健康", "创新药", "新能源",
                            "新消费", "企业服务/SaaS", "TMT", "机器人/智能制造", "出海"]
            bp["sectors"] = st.multiselect("所属赛道（可多选）", all_sectors, default=[s for s in bp.get("sectors", []) if s in all_sectors])
            bp["valuation_wan"] = st.number_input("估值（万元，可不填）", value=float(bp.get("valuation_wan", 0)), step=100.0)

        bp["business_summary"] = st.text_area("商业模式概括", bp.get("business_summary", ""), height=70)

        if bp.get("_source", "").startswith("rule_fallback"):
            st.info("提示：当前解析结果来自关键词规则降级方案，建议人工核对字段准确性。")

        st.session_state.bp_data = bp

with tab2:
    st.subheader("智能匹配")
    if not st.session_state.bp_data:
        st.info("请先在「① 上传 BP」完成解析。")
    else:
        top_n = st.slider("匹配机构数量", min_value=5, max_value=20, value=12)
        if st.button("运行匹配", type="primary"):
            with st.spinner("正在对照机构数据库多维度打分..."):
                matches = match_institutions(st.session_state.bp_data, institutions, top_n=top_n)
                st.session_state.matches = matches

        if st.session_state.matches:
            st.success(f"匹配完成，共找到 {len(st.session_state.matches)} 家候选机构")

            if llm.search_available:
                if st.button("🔍 联网核实 Top5 机构最新动态", type="secondary"):
                    top5 = st.session_state.matches[:5]
                    progress = st.progress(0, text="正在联网核实...")
                    for i, m in enumerate(top5):
                        sector_hint = m.get("matched_sectors", [""])[0] if m.get("matched_sectors") else ""
                        st.session_state.verify_results[m["name"]] = verify_institution(m["name"], sector_hint, llm)
                        progress.progress((i + 1) / len(top5), text=f"已核实 {i + 1}/{len(top5)}")
                    progress.empty()
                    st.rerun()
            else:
                st.caption("💡 配置支持联网搜索的智谱Key后，可以对Top5机构做实时动态核实（不只依赖静态种子库）")

            for m in st.session_state.matches:
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.markdown(f"**{m['name']}**　`{m.get('type', '')}`")
                        st.caption(f"赛道：{'、'.join(m.get('sectors', []))}　|　阶段：{'、'.join(m.get('stages', []))}")
                        st.caption(f"单笔规模：{m.get('check_size_min_wan')}万 - {m.get('check_size_max_wan')}万元")
                    with c2:
                        st.metric("匹配度", f"{m['match_score']}分")
                    bd = m["score_breakdown"]
                    st.progress(m["match_score"] / 100)
                    st.caption(f"赛道{bd['赛道匹配']} · 阶段{bd['阶段匹配']} · 规模{bd['规模匹配']} · 其他{bd['其他信号']}")

                    verify = st.session_state.verify_results.get(m["name"])
                    if verify:
                        icon = {"True": "✅", "False": "⚠️", "None": "❓"}.get(str(verify.get("verified")), "❓")
                        st.markdown(f"{icon} **联网核实**：{verify.get('summary', '')}")
                        if verify.get("source_titles"):
                            st.caption("信息来源：" + "；".join(verify["source_titles"]))

                    draft_key = f"inst_{m['name']}"
                    if st.button("✍️ 生成打招呼语", key=f"draft_btn_{draft_key}"):
                        with st.spinner("正在草拟联系消息..."):
                            st.session_state.outreach_drafts[draft_key] = draft_institution_outreach(
                                st.session_state.bp_data, m, llm
                            )
                    if draft_key in st.session_state.outreach_drafts:
                        st.text_area(
                            "可直接复制修改后使用",
                            value=st.session_state.outreach_drafts[draft_key],
                            key=f"draft_text_{draft_key}",
                            height=100,
                        )

with tab3:
    st.subheader("生成匹配报告")
    if not st.session_state.matches:
        st.info("请先在「② 智能匹配」运行匹配。")
    else:
        if st.button("生成完整报告（含匹配理由与沟通建议）", type="primary"):
            with st.spinner("正在为每家机构生成匹配理由与沟通建议..."):
                enriched = generate_match_reasons(st.session_state.bp_data, st.session_state.matches, llm)
                st.session_state.enriched = enriched
                st.session_state.report_md = export_markdown(st.session_state.bp_data, enriched)

        if st.session_state.get("report_md"):
            st.markdown(st.session_state.report_md)
            st.download_button(
                "⬇️ 下载报告（Markdown）",
                data=st.session_state.report_md,
                file_name=f"{st.session_state.bp_data.get('company_name', '匹配报告')}_睿链AI匹配报告.md",
                mime="text/markdown",
            )

with tab4:
    st.subheader("路演联系人匹配")
    st.caption(
        "路演/活动上加了一堆人，回头看着长长的联系人列表不知道谁值得优先跟进？"
        "把随手记的联系人信息贴进去，Agent 帮你判断谁是真投资人、跟你赛道对不对得上——"
        "信息不够判断的不瞎猜，会明确标出来还缺什么信息。"
    )

    if not st.session_state.bp_data:
        st.warning("建议先在「① 上传 BP」完成解析（哪怕用示例），这样才能对照你的赛道/阶段做相关度打分。")

    contact_raw = st.text_area(
        "把联系人信息贴进来，一行一个（格式不用统一，姓名/机构/职位/交流片段都行）",
        height=160,
        placeholder="例：\n王总 - 红杉中国 投资经理\n陈总监 - IDG资本\n李四\n张经理，某某科技创始人，做电商的",
    )

    if st.button("🤖 让 Agent 帮我分优先级", type="primary", disabled=not contact_raw.strip()):
        with st.spinner("正在解析联系人信息并对照赛道打分..."):
            contacts = parse_contact_list(contact_raw, llm)
            bp_for_score = st.session_state.bp_data or {"sectors": [], "stage": ""}
            result = score_contacts(bp_for_score, contacts, institutions)
            st.session_state.contact_result = result

    if st.session_state.get("contact_result"):
        result = st.session_state.contact_result
        st.markdown("---")

        st.markdown(f"#### 🎯 高优先级，建议尽快跟进（{len(result['high'])}人）")
        if result["high"]:
            for idx, c in enumerate(result["high"]):
                with st.container(border=True):
                    st.markdown(f"**{c['name']}**　`{c.get('org') or c.get('raw')}`")
                    st.caption(c["reason"])

                    draft_key = f"contact_{idx}_{c['name']}"
                    if st.button("✍️ 生成跟进语", key=f"draft_btn_{draft_key}"):
                        with st.spinner("正在草拟跟进消息..."):
                            bp_for_draft = st.session_state.bp_data or {}
                            st.session_state.outreach_drafts[draft_key] = draft_contact_followup(bp_for_draft, c, llm)
                    if draft_key in st.session_state.outreach_drafts:
                        st.text_area(
                            "可直接复制修改后发送",
                            value=st.session_state.outreach_drafts[draft_key],
                            key=f"draft_text_{draft_key}",
                            height=90,
                        )
        else:
            st.caption("暂时没有能确定高相关的联系人。")

        st.markdown(f"#### 🤔 待确认，信息不足以判断（{len(result['pending'])}人）")
        if result["pending"]:
            for c in result["pending"]:
                with st.container(border=True):
                    st.markdown(f"**{c['name']}**　`{c.get('raw', '')}`")
                    st.caption(c["reason"])
        else:
            st.caption("没有信息不足的联系人。")

        with st.expander(f"⚪ 低相关 / 非投资人（{len(result['low'])}人）"):
            for c in result["low"]:
                st.markdown(f"**{c['name']}**　`{c.get('raw', '')}`")
                st.caption(c["reason"])
                st.markdown("---")

with tab5:
    st.subheader("投资人话术演练")
    st.caption(
        "模拟投资人追问，练习临场表达。Agent会针对你BP里没讲清楚的地方追问——"
        "练完可以生成反馈，指出具体哪句话/哪个数据没站住，而不是'讲得不错'这种空话。"
    )

    if not st.session_state.bp_data:
        st.warning("建议先在「① 上传 BP」完成解析（哪怕用示例），这样投资人角色才能针对你的项目提问。")

    style = st.selectbox(
        "选择这一轮的投资人风格",
        list(INVESTOR_STYLES.keys()),
        format_func=lambda s: f"{s} — {INVESTOR_STYLES[s]}",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🎬 开始 / 重新开始演练", type="primary"):
            st.session_state.pitch_history = []
            st.session_state.pitch_feedback = None
            bp_for_practice = st.session_state.bp_data or {}
            with st.spinner("投资人正在准备第一个问题..."):
                first_q = get_next_question(bp_for_practice, style, [], llm)
            st.session_state.pitch_history.append({"role": "investor", "content": first_q})
            st.rerun()
    with col2:
        if st.session_state.pitch_history and st.button("📋 结束并生成反馈"):
            with st.spinner("正在复盘这场对话..."):
                st.session_state.pitch_feedback = generate_feedback(st.session_state.pitch_history, llm)

    for msg in st.session_state.pitch_history:
        is_investor = msg["role"] == "investor"
        with st.chat_message("assistant" if is_investor else "user"):
            st.markdown(f"**{'🧑‍💼 投资人' if is_investor else '🙋 你'}**：{msg['content']}")

    if st.session_state.pitch_history and not st.session_state.pitch_feedback:
        answer = st.chat_input("输入你的回答，回车发送...")
        if answer:
            st.session_state.pitch_history.append({"role": "founder", "content": answer})
            bp_for_practice = st.session_state.bp_data or {}
            with st.spinner("投资人正在追问..."):
                next_q = get_next_question(bp_for_practice, style, st.session_state.pitch_history, llm)
            st.session_state.pitch_history.append({"role": "investor", "content": next_q})
            st.rerun()

    if st.session_state.pitch_feedback:
        fb = st.session_state.pitch_feedback
        st.markdown("---")
        st.markdown("#### 📋 演练反馈")
        st.markdown("**做得好的地方：**")
        for s in fb.get("strengths", []):
            st.markdown(f"- {s}")
        st.markdown("**建议改进：**")
        for imp in fb.get("improvements", []):
            st.markdown(f"- {imp}")
        st.caption(fb.get("overall_comment", ""))
