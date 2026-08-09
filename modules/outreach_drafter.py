"""
下一步行动生成模块。

匹配/分类只是告诉你"该找谁"，停在这里对用户来说还是有个动作缺口——
很多人知道该联系谁，但还是会卡在"这条消息怎么开口"。这一步让Agent往前走一步，
直接把能复制去用的开场白草拟出来。

两种场景，语气刻意不一样：
1. draft_institution_outreach：对匹配出的机构，偏正式（邮件/微信都能用）
2. draft_contact_followup：对路演加的联系人，偏轻量口语（微信跟进语）
"""

INSTITUTION_OUTREACH_SYSTEM_PROMPT = """你是一名经验丰富的创业者，正在准备联系一家投资机构。
基于企业信息和目标机构信息，帮忙草拟一段简短、专业、不套路的初次联系消息（邮件或微信都能用）。

要求：
- 直接点出跟这家机构相关性最高的1-2个点（赛道、阶段或代表案例呼应），不要泛泛而谈
- 语气自信但不浮夸，避免"打扰了""百忙之中"这类过度客套的开场
- 控制在100-150字，方便直接复制使用
- 结尾给一个清晰的call to action（比如约15分钟电话，或者请对方看BP）
只返回消息正文文本，不要有任何其他说明文字或引号。
"""

CONTACT_FOLLOWUP_SYSTEM_PROMPT = """你是一名创业者，刚在路演/行业活动上加了一位投资人的微信，现在要发第一条跟进消息。
基于自己的企业信息和对这位联系人的了解（信息可能有限），草拟一段自然、不生硬的微信开场白。

要求：
- 提一句"活动上认识/交流"这种真实场景，不要显得像模板群发
- 简单带出自己在做的方向，勾起对方兴趣，但不要一上来就"求勾搭"
- 控制在60-100字，符合微信聊天的自然语气，不要用邮件那种正式格式
- 结尾可以问对方一个开放性问题，保持对话感，不要用生硬的销售话术
只返回消息正文文本，不要有任何其他说明文字或引号。
"""


def draft_institution_outreach(bp: dict, institution: dict, llm_client) -> str:
    if llm_client.available:
        try:
            user_prompt = f"企业信息：{bp}\n\n目标机构：{institution}"
            return llm_client.chat(INSTITUTION_OUTREACH_SYSTEM_PROMPT, user_prompt, temperature=0.5).strip()
        except Exception:
            pass
    return _template_institution_outreach(bp, institution)


def _template_institution_outreach(bp: dict, institution: dict) -> str:
    matched = "、".join(institution.get("matched_sectors", [])) or "相关赛道"
    return (
        f"您好，我们是{bp.get('company_name', '')}，目前专注于{matched}方向，"
        f"{bp.get('business_summary', '')}。了解到{institution.get('name', '贵机构')}在这个方向有布局，"
        f"想简单交流一下项目情况，方便的话可以约个15分钟电话，或者先发一版BP给您参考？"
    )


def draft_contact_followup(bp: dict, contact: dict, llm_client) -> str:
    if llm_client.available:
        try:
            user_prompt = f"企业信息：{bp}\n\n联系人信息：{contact}"
            return llm_client.chat(CONTACT_FOLLOWUP_SYSTEM_PROMPT, user_prompt, temperature=0.6).strip()
        except Exception:
            pass
    return _template_contact_followup(bp, contact)


def _template_contact_followup(bp: dict, contact: dict) -> str:
    business = bp.get("business_summary", "") or "早期项目"
    return (
        f"{contact.get('name', '')}您好，很高兴在活动上认识！我们在做{business}，"
        f"如果您那边也在关注这个方向，方便的话想约个时间简单聊聊，看看有没有合作的可能～"
    )
