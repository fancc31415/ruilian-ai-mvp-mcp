"""
投资人话术演练模块。

BP解析和匹配只解决了"该找谁"，这里往前一步解决"见面聊什么、怎么答"——
用对话式模拟，Agent扮演投资人追问，帮创业者练习临场表达，练完给具体反馈，
不是"讲得不错"这种空话，要指出具体哪句话、哪个数据站不住脚。
"""

INVESTOR_STYLES = {
    "犀利型": "问题直接尖锐，喜欢连续追问数据和逻辑漏洞，不太给面子",
    "亲和型": "语气温和，但会不动声色地追问关键细节，容易让人放松警惕后说漏嘴",
    "行业专家型": "对赛道细节非常懂，会用专业术语和具体案例来考验你的专业度",
}

ROLEPLAY_SYSTEM_PROMPT_TEMPLATE = """你正在扮演一位投资人，跟创业者进行一场路演模拟对话，帮TA练习临场问答。

创业者的项目信息：{bp}

你的角色设定：{style_desc}

扮演规则：
- 每次只问一个问题，不要一次抛出多个问题
- 问题要基于对方刚才的回答自然往下追问，像真实对话一样，不要跳来跳去
- 聚焦BP里信息模糊、没讲清楚的地方：市场规模依据、竞争壁垒、商业模式可持续性、团队执行力、财务假设
- 对方回答含糊时直接追问细节，不要轻易放过；但同一件事不要连续追问超过2轮，问完就换角度
- 全程口语化，像真实对话，不要写成书面报告，也不要每次都用"很好的问题"这种客套开场
- 目前已经聊了{turn_count}轮，超过6轮的话，可以在问题里自然引导对话收尾

现在请提出这场对话的下一个问题（如果是第一轮，就直接给开场问题，不用铺垫）。
只返回问题本身，不要有其他说明文字。
"""

FEEDBACK_SYSTEM_PROMPT = """你是一名资深创业导师，看完了创业者和投资人角色扮演的完整对话记录。
给出具体、可执行的反馈，不要空话套话，每一条都要能让人明确知道"具体是哪句话/哪个说法需要改"。

返回JSON：
{
  "strengths": ["表达得好的具体点，最多3条，要引用或复述对话里的具体内容"],
  "improvements": ["需要改进的具体点，最多3条，要指出问题出在哪句话/哪个数据，并给出改进方向"],
  "overall_comment": "1-2句总体评价"
}
只返回JSON。
"""

FALLBACK_QUESTIONS = [
    "先用一句话说清楚，你们到底解决了用户的什么问题？",
    "这个市场规模的数字是怎么算出来的，有没有可信的数据来源？",
    "如果有大厂或者竞品也在做类似的事，你们的核心壁垒是什么？",
    "现在的收入/付费用户情况怎么样，商业模式验证到什么阶段了？",
    "团队里谁负责什么，核心成员之前有没有相关领域的经验？",
    "这轮融资的钱具体打算怎么花，能撑多久、达到什么里程碑？",
]


def get_next_question(bp: dict, style: str, history: list, llm_client) -> str:
    """history: [{"role": "investor"/"founder", "content": "..."}]"""
    turn_count = len([h for h in history if h["role"] == "investor"])

    if llm_client.available:
        try:
            style_desc = INVESTOR_STYLES.get(style, "")
            system_prompt = ROLEPLAY_SYSTEM_PROMPT_TEMPLATE.format(
                bp=bp, style_desc=style_desc, turn_count=turn_count
            )
            conv_text = "\n".join(
                f"{'投资人' if h['role'] == 'investor' else '创业者'}：{h['content']}" for h in history
            )
            return llm_client.chat(
                system_prompt, conv_text or "（对话还未开始，请提出第一个问题）", temperature=0.7
            ).strip()
        except Exception:
            pass

    idx = turn_count % len(FALLBACK_QUESTIONS)
    return FALLBACK_QUESTIONS[idx]


def generate_feedback(history: list, llm_client) -> dict:
    if llm_client.available:
        try:
            conv_text = "\n".join(
                f"{'投资人' if h['role'] == 'investor' else '创业者'}：{h['content']}" for h in history
            )
            return llm_client.chat_json(FEEDBACK_SYSTEM_PROMPT, conv_text)
        except Exception:
            pass
    return {
        "strengths": ["（降级模式）未配置LLM Key，无法基于对话内容生成针对性反馈"],
        "improvements": ["建议配置LLM Key后重新演练一遍，才能拿到指出具体问题的反馈"],
        "overall_comment": "当前为关键词规则降级模式，反馈是通用提示，不是真正分析了你的回答内容。",
    }
