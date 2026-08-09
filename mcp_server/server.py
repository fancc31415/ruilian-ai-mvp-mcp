"""
睿链AI · MCP服务器

把"BP解析 + 机构匹配"这个核心能力包装成MCP协议的标准工具，
供外部AI平台（Coze/Dify/或任何支持自建MCP接口的平台）直接调用。

这是一个独立于Streamlit应用的服务，需要单独部署、单独拿一个公开地址。

本地测试：
    pip install -r mcp_server/requirements.txt
    python mcp_server/server.py
    # 默认监听 0.0.0.0:8000，MCP端点是 http://localhost:8000/mcp

部署到 Render.com（或类似平台）：
    Start Command: python mcp_server/server.py
    环境变量：PORT（平台通常自动注入）；LLM_API_KEY / LLM_BASE_URL / LLM_MODEL（复用同一套LLM配置，可选）
    部署完拿到的公开地址，在末尾加 /mcp，就是"自建MCP接口地址"要填的值
"""
import os
import sys

# server.py 在 mcp_server/ 子目录里，把项目根目录加进搜索路径，才能 import 到 modules 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.mcpserver import MCPServer

from modules.llm_client import LLMClient
from modules.bp_parser import parse_bp
from modules.matcher import load_institutions, match_institutions

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT_DIR, "data", "institutions.json")

mcp = MCPServer(name="睿链AI-BP匹配", version="1.0.0")
llm = LLMClient()
institutions = load_institutions(DATA_PATH)


@mcp.tool()
def match_bp(bp_text: str, top_n: int = 10) -> dict:
    """输入一段BP文本（企业介绍、赛道、融资阶段、金额等信息），自动解析关键信息并匹配最相关的投资机构。

    Args:
        bp_text: BP文本内容，越详细匹配越准，建议包含赛道、融资阶段、融资金额、商业模式概括
        top_n: 返回匹配机构数量，默认10家

    Returns:
        包含"解析出的企业信息"和"匹配机构"（含匹配度、匹配理由）的结构化结果
    """
    bp_data = parse_bp(bp_text, llm)
    matches = match_institutions(bp_data, institutions, top_n=top_n)

    simplified_matches = [
        {
            "机构名称": m["name"],
            "匹配度": m["match_score"],
            "机构类型": m.get("type", ""),
            "赛道覆盖": m.get("sectors", []),
            "投资阶段": m.get("stages", []),
            "单笔规模": f"{m.get('check_size_min_wan')}万-{m.get('check_size_max_wan')}万元",
            "匹配的赛道": m.get("matched_sectors", []),
        }
        for m in matches
    ]

    return {
        "解析出的企业信息": {
            "公司名称": bp_data.get("company_name"),
            "赛道": bp_data.get("sectors"),
            "融资阶段": bp_data.get("stage"),
            "融资金额_万元": bp_data.get("funding_ask_wan"),
            "商业模式概括": bp_data.get("business_summary"),
        },
        "匹配机构": simplified_matches,
        "数据来源说明": "机构库为公开信息拼接的种子库（当前64家），匹配结果仅供参考",
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
