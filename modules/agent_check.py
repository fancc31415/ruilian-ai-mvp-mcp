"""
Agent 自检 / 主动追问模块。

这是让整套流程从"AI工具"变成"Agent"的关键一步：
不是拿着解析出来的数据不管三七二十一往下匹配，而是先自己检查一遍——
"这几个字段缺了/含糊会不会影响匹配质量？缺了就该停下来问一句，而不是瞎猜"。

- check_missing_info_rule_based: 没有LLM时的规则版检查（固定字段+固定问法）
- check_missing_info: 有LLM时，让模型结合BP原文语境判断"缺口"和"为什么这个缺口重要"，
  问出来的问题更具体、更有针对性，而不是千篇一律的模板问句
"""

CRITICAL_FIELDS_RULES = {
    "funding_ask_wan": lambda bp: not bp.get("funding_ask_wan") or bp.get("funding_ask_wan") <= 0,
    "sectors": lambda bp: not bp.get("sectors"),
    "stage": lambda bp: bp.get("stage") not in ["天使轮", "Pre-A轮", "A轮", "B轮", "C轮+"],
    "business_summary": lambda bp: (
        not bp.get("business_summary")
        or bp.get("business_summary") in ["未提供", ""]
        or len(bp.get("business_summary", "")) < 6
    ),
}

DEFAULT_QUESTIONS = {
    "funding_ask_wan": {
        "question": "这一轮计划融资多少钱？（大概金额也可以，比如'300万左右'）",
        "why_it_matters": "融资金额是打分权重里的一环，缺了这个只能按中性分处理，匹配结果可能不够准。",
    },
    "sectors": {
        "question": "能否用一两个词说一下你们主要做哪个赛道/方向？",
        "why_it_matters": "赛道匹配占打分权重的40%，是最核心的维度，没有赛道信息基本没法做有效匹配。",
    },
    "stage": {
        "question": "现在具体是哪个融资阶段？（天使轮 / Pre-A / A轮 / B轮 / C轮+）",
        "why_it_matters": "机构的阶段偏好差异很大，阶段判断错了会推荐一批完全不看这个阶段的机构，白白浪费触达机会。",
    },
    "business_summary": {
        "question": "能否用一句话说清楚你们具体怎么赚钱/核心业务是什么？",
        "why_it_matters": "赛道相同但商业模式差很远的项目，适合的机构类型也不一样，这句话能帮助提升匹配精度。",
    },
}


def check_missing_info_rule_based(bp: dict) -> list:
    questions = []
    for field, is_missing_fn in CRITICAL_FIELDS_RULES.items():
        if is_missing_fn(bp):
            q = DEFAULT_QUESTIONS[field]
            questions.append({"field": field, **q})
    return questions


AGENT_CHECK_SYSTEM_PROMPT = """你是一名尽职的FA顾问Agent，正在审核一份刚从BP里解析出来的结构化数据，
判断里面有没有会实质性影响后续机构匹配质量的关键信息缺失或过于含糊。

只关注这4个字段：funding_ask_wan（融资金额）、sectors（赛道）、stage（融资阶段）、business_summary（商业模式概括）。
不要吹毛求疵，只有真的会影响匹配打分或者机构判断的缺口才提出来，能不问就不问。

返回JSON，格式：
{
  "has_gaps": true/false,
  "questions": [
    {
      "field": "字段名，必须是上面4个之一",
      "question": "具体的追问，要结合企业信息，不要用千篇一律的通用问法",
      "why_it_matters": "一句话说明这个信息为什么重要，讲清楚缺了会怎样影响匹配"
    }
  ]
}
如果都齐全，questions返回空数组。
"""


def check_missing_info(bp: dict, llm_client) -> list:
    """返回缺口问题列表；每项含 field / question / why_it_matters。"""
    if llm_client.available:
        try:
            user_prompt = f"BP结构化数据：{bp}"
            result = llm_client.chat_json(AGENT_CHECK_SYSTEM_PROMPT, user_prompt)
            if result.get("has_gaps") and result.get("questions"):
                return result["questions"]
            return []
        except Exception:
            return check_missing_info_rule_based(bp)
    else:
        return check_missing_info_rule_based(bp)
