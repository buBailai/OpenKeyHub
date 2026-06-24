"""从上游响应里尽力抽 token 用量（拿不到就 0，只计次数）。"""
from __future__ import annotations

import json
from typing import Tuple


def from_json(body: dict) -> Tuple[int, int]:
    """非流式响应：直接读 usage 字段。"""
    u = (body or {}).get("usage") or {}
    return int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)


def from_sse_line(line: str) -> Tuple[int, int] | None:
    """流式：解析一行 `data: {...}`，若含 usage 则返回，否则 None。

    需要客户端/我们注入 stream_options.include_usage=true，多数国内厂家支持。
    """
    line = line.strip()
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if payload == "[DONE]" or not payload:
        return None
    try:
        obj = json.loads(payload)
    except Exception:
        return None
    u = obj.get("usage")
    if not u:
        return None
    return int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
