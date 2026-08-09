"""
匹配打分引擎。
维度与权重（v0.1，后续可根据真实成交反馈数据调整权重，甚至换成学习到的打分模型）：
  - 赛道匹配   40%
  - 阶段匹配   30%
  - 单笔规模匹配 20%
  - 机构类型/其他信号 10%
"""
import json


def load_institutions(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _sector_score(bp_sectors: list, inst_sectors: list) -> float:
    if not bp_sectors:
        return 0.0
    overlap = set(bp_sectors) & set(inst_sectors)
    return len(overlap) / len(bp_sectors)


def _stage_score(bp_stage: str, inst_stages: list) -> float:
    if bp_stage in inst_stages:
        return 1.0
    # 阶段相邻给部分分（比如BP是A轮，机构写的是天使轮+B轮，说明覆盖范围较广，给个折中分）
    stage_order = ["天使轮", "Pre-A轮", "A轮", "B轮", "C轮+"]
    if bp_stage not in stage_order:
        return 0.3
    bp_idx = stage_order.index(bp_stage)
    for s in inst_stages:
        if s in stage_order and abs(stage_order.index(s) - bp_idx) == 1:
            return 0.5
    return 0.0


def _size_score(funding_ask_wan: float, min_wan: float, max_wan: float) -> float:
    if not funding_ask_wan or funding_ask_wan <= 0:
        return 0.5  # 金额未知，给中性分，不因为缺信息而拉低太多
    if min_wan <= funding_ask_wan <= max_wan:
        return 1.0
    # 超出区间，按偏离程度线性衰减
    if funding_ask_wan < min_wan:
        ratio = funding_ask_wan / min_wan if min_wan else 0
    else:
        ratio = max_wan / funding_ask_wan if funding_ask_wan else 0
    return max(0.0, min(ratio, 1.0)) * 0.6  # 超区间最多给0.6分的部分匹配


def _other_score(bp: dict, inst: dict) -> float:
    """其他信号：目前用『赛道数量覆盖广度』和『是否国资/CVC与硬科技/半导体强相关』做一点点加权，
    后续可以接入真实历史成交数据、机构响应速度等信号。"""
    score = 0.0
    if inst.get("type", "").find("国资") >= 0 and any(
        s in bp.get("sectors", []) for s in ["硬科技", "半导体", "新能源", "机器人/智能制造"]
    ):
        score += 0.5
    if len(inst.get("sectors", [])) <= 3:
        score += 0.5  # 赛道越聚焦，专业度信号越强
    return min(score, 1.0)


def match_institutions(bp: dict, institutions: list, top_n: int = 12) -> list:
    """返回按综合得分排序的匹配清单，每条附带各维度得分和命中理由，供报告生成使用。"""
    results = []
    for inst in institutions:
        sector_s = _sector_score(bp.get("sectors", []), inst.get("sectors", []))
        stage_s = _stage_score(bp.get("stage", ""), inst.get("stages", []))
        size_s = _size_score(
            bp.get("funding_ask_wan", 0),
            inst.get("check_size_min_wan", 0),
            inst.get("check_size_max_wan", 0),
        )
        other_s = _other_score(bp, inst)

        total = sector_s * 0.4 + stage_s * 0.3 + size_s * 0.2 + other_s * 0.1

        matched_sectors = list(set(bp.get("sectors", [])) & set(inst.get("sectors", [])))

        results.append({
            **inst,
            "match_score": round(total * 100, 1),
            "score_breakdown": {
                "赛道匹配": round(sector_s * 100, 1),
                "阶段匹配": round(stage_s * 100, 1),
                "规模匹配": round(size_s * 100, 1),
                "其他信号": round(other_s * 100, 1),
            },
            "matched_sectors": matched_sectors,
        })

    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results[:top_n]
