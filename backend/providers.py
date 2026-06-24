"""国内厂家预设（移植自 Any2Manim，均 OpenAI 兼容）。

base_url 存到 /v1 级别（不含 /chat/completions），转发时统一拼 /chat/completions。
管理员在后台新建厂家时可一键选预设，只需粘真实 Key。
"""
from __future__ import annotations

PRESETS: dict[str, dict] = {
    "deepseek": {
        "label": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "hint": "便宜稳，代码/通用都行。"},
    "doubao": {
        "label": "豆包 / 火山方舟", "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": [],
        "hint": "模型名填方舟接入点 endpoint id 或官方模型名。"},
    "qwen": {
        "label": "阿里通义千问", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
        "hint": "DashScope OpenAI 兼容模式。"},
    "glm": {
        "label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4", "glm-4-plus", "glm-4-flash"],
        "hint": "智谱开放平台。"},
    "siliconflow": {
        "label": "硅基流动", "base_url": "https://api.siliconflow.cn/v1",
        "models": ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"],
        "hint": "聚合多家开源模型，模型名用完整路径。"},
    "moonshot": {
        "label": "月之暗面 Kimi", "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "hint": "Kimi 开放平台。"},
    "openai": {
        "label": "OpenAI", "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini"],
        "hint": "需可访问 openai.com。"},
    "ollama": {
        "label": "Ollama 本地", "base_url": "http://localhost:11434/v1",
        "models": ["qwen2.5-coder", "llama3.2"],
        "hint": "本地零成本，Key 随便填（如 ollama）。先 ollama pull 模型。"},
    "custom": {
        "label": "自定义 (OpenAI 兼容)", "base_url": "",
        "models": [],
        "hint": "任意 OpenAI 兼容端点，Base URL 填到 /v1 级别。"},
}


def public_list() -> list[dict]:
    return [{"key": k, **v} for k, v in PRESETS.items()]
