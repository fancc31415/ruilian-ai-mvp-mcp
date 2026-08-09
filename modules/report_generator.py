"""
匹配报告生成模块。
- generate_match_reasons: 给Top N机构逐条生成『为什么匹配 + 怎么谈』（LLM优先，模板降级）
- export_markdown: 拼成完整报告，供下载
"""
from datetime import datetime

REASON_SYSTEM_PROMPT = """你是一名资深FA顾问，正在为一份BP撰写"机构匹配理由与沟通建议"。
输入是企业信息和一家候选投资机构的信息，请输出JSON：
{
  "match_reason": "为什么这家机构值得联系，2-3句话，结合赛道/阶段/规模/机构风格具体展开，不要套话",
  "talking_points": ["与该机构沟通时建议突出的1-2个点，要具体，结合企业亮点和机构偏好"],
  "caution": "如果有需要注意的匹配风险或需要提前准备的材料，用一句话说明；没有则填'无明显风险点'"
}
只返回JSON，不要多余文字。
"""


def generate_match_reasons(bp: dict, matched_institutions: list, llm_client) -> list:
    enriched = []
    for inst in matched_institutions:
        if llm_client.available:
            try:
                user_prompt = (
                    f"企业信息：{bp}\n\n候选机构信息：{ {k: v for k, v in inst.items() if k not in ['score_breakdown']} }"
                )
                reason_data = llm_client.chat_json(REASON_SYSTEM_PROMPT, user_prompt)
            except Exception:
                reason_data = _template_reason(bp, inst)
        else:
            reason_data = _template_reason(bp, inst)

        enriched.append({**inst, **reason_data})
    return enriched


def _template_reason(bp: dict, inst: dict) -> dict:
    """没有LLM时的模板化降级方案，保证报告字段完整可用。"""
    matched = "、".join(inst.get("matched_sectors", [])) or "赛道信息待人工核对"
    return {
        "match_reason": (
            f"{inst['name']} 在{matched}赛道有布局，投资阶段覆盖{'/'.join(inst.get('stages', []))}，"
            f"单笔规模区间{inst.get('check_size_min_wan')}万-{inst.get('check_size_max_wan')}万元，"
            f"与本项目融资需求综合匹配度较高。"
        ),
        "talking_points": [f"强调项目在{matched}赛道的差异化优势，对齐机构历史投资偏好"],
        "caution": "此为模板化生成（未配置LLM API Key），建议人工顾问复核后再对外沟通。",
    }


def export_markdown(bp: dict, enriched_matches: list) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# 睿链AI · 融资匹配报告",
        f"生成时间：{now}",
        "",
        "## 一、项目概览",
        f"- **公司名称**：{bp.get('company_name', '未提供')}",
        f"- **所属赛道**：{'、'.join(bp.get('sectors', []))}",
        f"- **融资阶段**：{bp.get('stage', '未提供')}",
        f"- **本轮融资金额**：{bp.get('funding_ask_wan', 0)} 万元",
        f"- **估值**：{bp.get('valuation_wan', 0)} 万元" if bp.get("valuation_wan") else "- **估值**：未提供",
        f"- **商业模式概括**：{bp.get('business_summary', '未提供')}",
        f"- **核心亮点**：{'；'.join(bp.get('highlights', [])) or '未提供'}",
        f"- **需人工核对项**：{'；'.join(bp.get('risks_or_gaps', [])) or '无'}",
        "",
        f"## 二、匹配机构清单（Top {len(enriched_matches)}）",
        "",
    ]

    for i, m in enumerate(enriched_matches, 1):
        lines += [
            f"### {i}. {m['name']}  ·  综合匹配度 {m['match_score']}分",
            f"- **类型**：{m.get('type', '')}　**代表案例**：{m.get('notable', '')}",
            f"- **赛道覆盖**：{'、'.join(m.get('sectors', []))}",
            f"- **投资阶段**：{'、'.join(m.get('stages', []))}",
            f"- **单笔规模**：{m.get('check_size_min_wan')}万 - {m.get('check_size_max_wan')}万元",
            f"- **打分明细**：赛道{m['score_breakdown']['赛道匹配']} / 阶段{m['score_breakdown']['阶段匹配']} "
            f"/ 规模{m['score_breakdown']['规模匹配']} / 其他{m['score_breakdown']['其他信号']}",
            f"- **匹配理由**：{m.get('match_reason', '')}",
            f"- **沟通建议**：{'；'.join(m.get('talking_points', []))}",
            f"- **注意事项**：{m.get('caution', '')}",
            "",
        ]

    lines.append("---")
    lines.append("*本报告由睿链AI自动生成，匹配结果仅供参考，最终决策建议结合人工顾问复核意见。*")
    return "\n".join(lines)
