"""
路演联系人匹配模块。

真实场景：路演/活动上加了一堆人，回头看着长长的联系人列表，不知道谁是真投资人、
跟自己赛道对不对得上。这个模块把"信息不足就该问，而不是瞎猜"这个Agent设计理念，
从BP解析场景复用到这个新场景：

1. parse_contact_list: 把用户随手记的联系人信息（格式不规整）解析成结构化数据
2. score_contacts: 结合企业自己的BP信息 + 机构种子库，给每个联系人算相关度，
   信息不够的不硬打分，标记"待确认"并说明还缺什么信息
"""

import re
from modules.bp_parser import SECTOR_KEYWORDS  # 复用BP解析里已有的赛道关键词库，不重复维护

CONTACT_PARSE_SYSTEM_PROMPT = """你是一名FA顾问Agent，正在帮用户整理路演/活动上加到的联系人信息。
输入是用户随手记录的联系人信息，一行（或一段）一个联系人，格式很不规范——
可能只有姓名，也可能有机构、职位、简单交流内容片段。

请尽量提取结构化信息，返回JSON，格式：
{
  "contacts": [
    {
      "raw": "原始这一条输入内容，原样保留",
      "name": "姓名，没有就填'未知'",
      "org": "机构/公司名称，没有就填''",
      "title": "职位，没有就填''",
      "is_likely_investor": true/false/null,
      "sector_hint": "从只言片语里能看出的赛道倾向，没有就填''",
      "missing_info": "如果 is_likely_investor 是 null，说明还缺什么信息才能判断，比如'不知道对方机构名称'"
    }
  ]
}
is_likely_investor 判断规则：能看出明确是投资机构/基金相关（名字带"资本""创投""基金""VC""PE"等，
或职位是投资经理/合伙人/投资总监等）填true；能看出明显不是投资人（比如同行创业者、媒体、服务商）填false；
信息不够（只有姓名，没机构没职位没交流内容）填null，不要瞎猜。
只返回JSON，不要多余文字。
"""


def _rule_based_parse(raw_text: str) -> list:
    """没有LLM时的降级方案：把每行拆成 姓名/机构/职位，再判断投资人身份和赛道线索。
    尽量靠"分隔符切分+关键词库"把信息榨干净，减少直接扔进'待确认'的比例。"""
    investor_kw = [
        "资本", "创投", "创业投资", "基金", "投资", "VC", "PE", "CVC",
        "Capital", "Ventures", "Partners", "产投", "母基金", "资产管理",
        "合伙人", "投资经理", "投资总监", "投资director", "MD", "董事总经理",
        "生态合伙人", "基金经理", "FA", "财务顾问",
    ]
    non_investor_kw = [
        "创始人", "CEO", "COO", "CTO", "总经理", "记者", "媒体", "编辑",
        "服务商", "律师", "会计", "顾问", "BD", "市场", "HR", "猎头",
    ]
    separators = [" - ", " – ", "-", "，", ",", "、", "：", ":"]

    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    contacts = []
    for line in lines:
        # 尝试用常见分隔符把"姓名 / 机构+职位"拆开，拆不出来就整行当姓名处理
        parts = None
        for sep in separators:
            if sep in line:
                candidate = [p.strip() for p in line.split(sep) if p.strip()]
                if len(candidate) >= 2:
                    parts = candidate
                    break

        if parts:
            name_raw = parts[0]
            org_title_text = " ".join(parts[1:])
        else:
            name_raw = line
            org_title_text = ""

        name_match = re.match(r"^([\u4e00-\u9fa5A-Za-z]{2,10})", name_raw)
        name = name_match.group(1) if name_match else (name_raw[:10] if name_raw else "未知")

        search_scope = org_title_text or line  # 没拆出机构职位部分时，退化到整行搜关键词

        is_investor = None
        if any(kw in search_scope for kw in investor_kw):
            is_investor = True
        elif any(kw in search_scope for kw in non_investor_kw):
            is_investor = False

        # 机构名：优先用拆分出来的 org_title_text（去掉常见职位后缀词），拆不出来就留空
        org_guess = org_title_text
        for title_kw in ["投资经理", "投资总监", "合伙人", "董事总经理", "创始人", "CEO", "总经理", "生态合伙人", "基金经理"]:
            org_guess = org_guess.replace(title_kw, "").strip()

        # 赛道线索：在整行文本里找SECTOR_KEYWORDS命中的赛道，命中就填上，不硬编造
        sector_hint = ""
        for sector, kws in SECTOR_KEYWORDS.items():
            if any(kw in line for kw in kws):
                sector_hint = sector
                break

        missing = "" if is_investor is not None else "信息太少（只有姓名/寒暄），不知道对方机构和职位，无法判断是否是投资人"

        contacts.append({
            "raw": line,
            "name": name,
            "org": org_guess,
            "title": "",
            "is_likely_investor": is_investor,
            "sector_hint": sector_hint,
            "missing_info": missing,
        })
    return contacts


def parse_contact_list(raw_text: str, llm_client) -> list:
    if llm_client.available:
        try:
            result = llm_client.chat_json(CONTACT_PARSE_SYSTEM_PROMPT, raw_text[:8000])
            contacts = result.get("contacts", [])
            if contacts:
                return contacts
            return _rule_based_parse(raw_text)
        except Exception:
            return _rule_based_parse(raw_text)
    else:
        return _rule_based_parse(raw_text)


def _fuzzy_match_institution(org_name: str, raw_text: str, institutions: list):
    """先按解析出的机构名匹配；机构名为空或匹配不到时，退而对原始文本做子串匹配兜底
    （规则降级模式下机构名抽取不一定准，这样能兜住"陈总监 - IDG资本"这种格式）。"""
    candidates = [n for n in [org_name, raw_text] if n]
    for name in candidates:
        for inst in institutions:
            if inst["name"] in name or (name and name in inst["name"]):
                return inst
    return None


def score_contacts(bp: dict, contacts: list, institutions: list) -> dict:
    """
    返回三组：high（高相关，建议优先跟进）、pending（信息不足待确认）、low（低相关/非投资人）
    每条都带上判断理由，方便用户一眼看懂"为什么这么分类"。
    """
    high, pending, low = [], [], []
    bp_sectors = set(bp.get("sectors", []))
    bp_stage = bp.get("stage", "")

    for c in contacts:
        if c.get("is_likely_investor") is None:
            c["reason"] = f"⚠️ {c.get('missing_info', '信息不足，无法判断')}，建议见面/私信时补充确认对方机构和职位"
            pending.append(c)
            continue

        if c.get("is_likely_investor") is False:
            c["reason"] = "看起来不是投资人（可能是同行创业者/媒体/服务商），优先级降低，但如果对方有相关人脉资源也可以保留联系"
            low.append(c)
            continue

        # 是投资人，尝试匹配到机构库算相关度
        matched_inst = _fuzzy_match_institution(c.get("org", ""), c.get("raw", ""), institutions)
        if matched_inst:
            overlap = bp_sectors & set(matched_inst.get("sectors", []))
            stage_match = bp_stage in matched_inst.get("stages", [])
            if overlap and stage_match:
                c["reason"] = f"✅ 机构库匹配到「{matched_inst['name']}」，赛道（{', '.join(overlap)}）和阶段都对得上，建议优先跟进"
                high.append(c)
            elif overlap:
                c["reason"] = f"🔶 机构库匹配到「{matched_inst['name']}」，赛道对得上（{', '.join(overlap)}）但阶段可能不完全匹配，可以聊聊但不是最优先"
                high.append(c)
            else:
                c["reason"] = f"机构库匹配到「{matched_inst['name']}」，但赛道覆盖里没看到和你们重合的方向，优先级降低"
                low.append(c)
        elif c.get("sector_hint") and c["sector_hint"] in bp_sectors:
            c["reason"] = f"✅ 交流内容里提到的方向（{c['sector_hint']}）和你们赛道吻合，机构库里暂时没有这家的详细数据，建议直接确认"
            high.append(c)
        elif c.get("sector_hint"):
            c["reason"] = f"对方看起来主投「{c['sector_hint']}」方向，跟你们赛道不太重合，优先级可以往后放放"
            low.append(c)
        else:
            c["reason"] = "⚠️ 确认是投资人，但机构库里没有这家的数据，也看不出明确赛道倾向，建议直接问一句对方主投什么方向再判断"
            pending.append(c)

    return {"high": high, "pending": pending, "low": low}
