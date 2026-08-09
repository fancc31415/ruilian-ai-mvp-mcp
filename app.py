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

tab1, tab2, tab3 = st.tabs(["① 上传 BP", "② 智能匹配", "③ 匹配报告"])

if "bp_data" not in st.session_state:
    st.session_state.bp_data = None
if "matches" not in st.session_state:
    st.session_state.matches = None

with tab1:
    st.subheader("上传企业 BP")

    demo_col, upload_col = st.columns([1, 2])
    with demo_col:
        st.markdown("**没有BP文件？先体验一下：**")
        if st.button("🎯 一键加载示例（睿链AI 自己的BP）", use_container_width=True):
            st.session_state.bp_data = dict(DEMO_BP)
            st.session_state.matches = None
            st.session_state.pop("report_md", None)
            st.rerun()
        st.caption("用睿链AI自己的融资BP作为示例，跑一遍完整的解析→匹配→报告流程")

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
                except Exception as e:
                    st.error(f"解析失败：{e}")

    if st.session_state.bp_data:
        bp = st.session_state.bp_data
        st.markdown("---")
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
