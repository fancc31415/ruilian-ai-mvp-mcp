"""
LLM 调用抽象层。
默认对接 DeepSeek（OpenAI 兼容协议），把 base_url / model / api_key 都抽出来，
后面要换成其他模型（Kimi / 通义 / Claude API 等）只需要改这里，不用动业务代码。

用法：
    from modules.llm_client import LLMClient
    llm = LLMClient()
    text = llm.chat("你是一个投融资分析师...", "请分析这份BP")
"""
import os
import json
import requests
from openai import OpenAI


class LLMClient:
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        # 优先用传入参数，其次环境变量，最后给默认值（DeepSeek 官方 endpoint）
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        self.model = model or os.getenv("LLM_MODEL", "deepseek-chat")
        self.available = bool(self.api_key)

        if self.available:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            self.client = None

        # 联网搜索目前只对接了智谱BigModel的Web Search API，跟对话用的Key可以是两把不同的——
        # 比如主力对话换成了别的更强的模型（大赛统一发的临时Key），但还想保留联网核实功能，
        # 就单独配一个 ZHIPU_SEARCH_API_KEY 环境变量，两边互不影响。
        self.search_api_key = os.getenv("ZHIPU_SEARCH_API_KEY") or (
            self.api_key if "bigmodel.cn" in self.base_url else None
        )
        self.search_available = bool(self.search_api_key)

    def chat(self, system_prompt: str, user_prompt: str, json_mode: bool = False,
              temperature: float = 0.3) -> str:
        """
        调一次对话。json_mode=True 时会要求模型只返回 JSON（用于结构化抽取）。
        没有配置 API Key 时抛 RuntimeError，上层需要有 fallback 逻辑（见 bp_parser.py / report_generator.py）。
        """
        if not self.available:
            raise RuntimeError(
                "未配置 LLM API Key。请设置环境变量 DEEPSEEK_API_KEY，"
                "或在 .env 文件中填写后重启应用。"
            )

        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> dict:
        """封装：要求模型返回 JSON，并做好解析容错（去除 markdown 代码块围栏等）。"""
        raw = self.chat(system_prompt, user_prompt, json_mode=True, temperature=temperature)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        return json.loads(cleaned.strip())

    def web_search(self, query: str, count: int = 5) -> list:
        """联网搜索，返回搜索结果列表（每条含 title/content/link/publish_date）。
        只支持智谱BigModel的Web Search API，用的是 search_api_key（可以跟主对话Key不是同一把）。
        不可用时直接返回空列表，不假装搜过——上层要老实展示"未联网核实"，而不是编造一个核实结果。"""
        if not self.search_available:
            return []
        try:
            resp = requests.post(
                "https://open.bigmodel.cn/api/paas/v4/web_search",
                headers={"Authorization": f"Bearer {self.search_api_key}", "Content-Type": "application/json"},
                json={"search_query": query, "search_engine": "search_std", "count": count},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("search_result", [])
        except Exception:
            return []
