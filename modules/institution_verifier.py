"""
机构联网核实模块。

匹配结果目前完全依赖种子库里那份几个月前拍的静态数据——机构可能已经不投这个赛道了，
也可能基金已经封闭不再新投。这一步让Agent真去联网搜一下，核实候选机构最近是否还活跃，
而不是假装种子库数据永远正确。

诚实原则：搜不到 / 没配支持搜索的Key时，明确展示"未核实"，不编造结果。
"""

VERIFY_SYSTEM_PROMPT = """你是一名尽职的FA助理Agent，正在核实一家投资机构近期是否依然活跃、
是否还在关注用户提到的赛道方向。下面是搜索引擎针对该机构近期动态返回的真实结果片段。

请你只依据这些搜索片段判断，不要编造任何没有在片段中出现的信息：
- 如果片段里能看出机构近期确实有投资动作/活跃迹象，verified填true
- 如果片段里明显显示机构已经不活跃（比如基金已清算、团队解散等负面信号），verified填false
- 如果片段信息不够、看不出明确结论，verified填null，summary里如实说"公开资料不足，建议直接核实"

只返回JSON：
{
  "verified": true/false/null,
  "summary": "1-2句真实动态总结，或者信息不足的说明，不要超过60字",
  "source_titles": ["引用的信息来源标题，最多2个，没有就填空数组"]
}
"""


def verify_institution(inst_name: str, sector_hint: str, llm_client) -> dict:
    """核实单家机构。返回 verified(true/false/None) + summary + source_titles。"""
    if not llm_client.search_available:
        return {
            "verified": None,
            "summary": "未联网核实（当前配置的Key不支持联网搜索，仅支持智谱BigModel）",
            "source_titles": [],
        }

    query = f"{inst_name} 最新投资动态 {sector_hint}".strip()
    results = llm_client.web_search(query, count=5)

    if not results:
        return {"verified": None, "summary": "联网搜索没有找到相关结果，公开资料不足", "source_titles": []}

    search_context = "\n".join(
        f"- {r.get('title', '')}：{r.get('content', '')[:150]}" for r in results[:5]
    )

    try:
        result = llm_client.chat_json(VERIFY_SYSTEM_PROMPT, f"机构名称：{inst_name}\n\n搜索结果：\n{search_context}")
        result.setdefault("source_titles", [])
        return result
    except Exception:
        return {"verified": None, "summary": "核实过程出错，未能生成总结，建议人工核实", "source_titles": []}
