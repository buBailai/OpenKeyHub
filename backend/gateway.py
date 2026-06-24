"""OpenAI 兼容转发网关：鉴权 → 路由 → 透传（含流式）→ 记日志。

老师端只认 `{服务地址}/v1` + 个人 Key，与直连厂家无异。
"""
from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import auth, config, store, usage

router = APIRouter(prefix="/v1", tags=["gateway"])


def _err(msg: str, code: int, etype: str = "invalid_request_error"):
    """OpenAI 风格错误体，方便各类客户端（含自愈类客户端）识别。"""
    return JSONResponse(status_code=code,
                        content={"error": {"message": msg, "type": etype, "code": code}})


def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return None


def _auth_account(request: Request):
    """返回 (account_dict, error_response)。"""
    key = _bearer(request)
    if not key:
        return None, _err("缺少 API Key（Authorization: Bearer ...）", 401, "authentication_error")
    acct = store.account_by_key_hash(auth.hash_key(key))
    if not acct:
        return None, _err("无效的 API Key", 401, "authentication_error")
    if not acct["enabled"]:
        return None, _err("该账号已被停用，请联系管理员", 403, "permission_error")
    if acct["quota_total"] and acct["quota_used"] >= acct["quota_total"]:
        return None, _err("调用次数已达上限，请联系管理员", 429, "rate_limit_error")
    if acct["rate_per_min"] and store.calls_in_last_minute(acct["id"]) >= acct["rate_per_min"]:
        return None, _err("请求过于频繁，请稍后再试", 429, "rate_limit_error")
    return acct, None


@router.get("/models")
async def list_models(request: Request):
    """返回本网关开放的模型清单（OpenAI /v1/models 格式）。"""
    acct, err = _auth_account(request)
    if err:
        return err
    names = await asyncio.to_thread(store.enabled_model_names)
    return {"object": "list",
            "data": [{"id": n, "object": "model", "owned_by": "openkeyhub"} for n in names]}


@router.post("/chat/completions")
async def chat_completions(request: Request):
    acct, err = _auth_account(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        return _err("请求体不是合法 JSON", 400)
    if not isinstance(body, dict) or not body.get("model"):
        return _err("缺少 model 字段", 400)

    public_model = body["model"]
    route = await asyncio.to_thread(store.route_for, public_model)
    if not route:
        return _err(f"模型 '{public_model}' 未在本网关开放，请联系管理员", 404, "model_not_found")
    if not route["provider_enabled"] or not route["model_enabled"]:
        return _err(f"模型 '{public_model}' 当前已停用", 403, "model_not_found")
    if not route["base_url"]:
        return _err("该厂家未配置 Base URL", 502)

    # 改写：上游真实模型名 + 真实 Key + 真实地址
    body["model"] = route["upstream_model"]
    stream = bool(body.get("stream"))
    if stream:
        # 尽力拿 token 用量（多数国内厂家支持；不支持的会忽略该字段）
        opts = body.get("stream_options")
        if not isinstance(opts, dict):
            opts = {}
        opts.setdefault("include_usage", True)
        body["stream_options"] = opts

    url = route["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {route['api_key']}", "Content-Type": "application/json"}
    timeout = httpx.Timeout(connect=config.UPSTREAM_CONNECT_TIMEOUT,
                            read=config.UPSTREAM_READ_TIMEOUT, write=60.0, pool=20.0)
    t0 = time.time()

    async def _record(status, http_code, pt, ct):
        await asyncio.to_thread(store.bump_account_usage, acct["id"])
        await asyncio.to_thread(
            store.log_call, acct["id"], public_model, route["provider_id"],
            status, http_code, pt, ct, int((time.time() - t0) * 1000))

    if not stream:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, json=body, headers=headers)
        except Exception as e:
            await _record("error", 502, 0, 0)
            return _err(f"上游调用失败：{e}", 502, "upstream_error")
        pt = ct = 0
        try:
            data = r.json()
            pt, ct = usage.from_json(data)
        except Exception:
            data = None
        await _record("ok" if r.status_code < 400 else "error", r.status_code, pt, ct)
        if data is not None:
            return JSONResponse(status_code=r.status_code, content=data)
        return JSONResponse(status_code=r.status_code,
                            content={"raw": r.text[:2000]})

    # ---------- 流式透传 ----------
    async def streamer():
        pt = ct = 0
        http_code = 200
        status = "ok"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=body, headers=headers) as r:
                    http_code = r.status_code
                    if r.status_code >= 400:
                        status = "error"
                        text = (await r.aread()).decode("utf-8", "ignore")
                        yield ("data: " + _err_chunk(text) + "\n\n").encode()
                        yield b"data: [DONE]\n\n"
                        return
                    async for raw in r.aiter_lines():
                        if raw:
                            got = usage.from_sse_line(raw)
                            if got:
                                pt, ct = got
                        # aiter_lines 去掉了换行，补回 SSE 帧分隔
                        yield (raw + "\n").encode("utf-8")
        except Exception as e:
            status = "error"
            http_code = 502
            yield ("data: " + _err_chunk(f"上游调用失败：{e}") + "\n\n").encode()
            yield b"data: [DONE]\n\n"
        finally:
            await _record(status, http_code, pt, ct)

    return StreamingResponse(streamer(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _err_chunk(msg: str) -> str:
    import json
    return json.dumps({"error": {"message": msg[:500], "type": "upstream_error"}})
