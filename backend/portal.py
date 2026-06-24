"""老师端：用手机号 + 密码登录，自助查看自己的 API Key。

默认密码 openkeyhub，首次登录强制改密后才能看 Key。管理员可重置回默认。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from . import auth, config, store

router = APIRouter(prefix="/api/portal", tags=["portal"])


def _current(request: Request) -> dict | None:
    tid = auth.read_session(request.cookies.get(auth.TEACHER_COOKIE), role="teacher")
    if not tid:
        return None
    return store.account_by_id(tid)


def _set_session(response: Response, aid: int):
    response.set_cookie(auth.TEACHER_COOKIE, auth.make_session(aid, role="teacher"),
                        httponly=True, samesite="lax", max_age=7 * 24 * 3600)


@router.get("/state")
def state(request: Request):
    a = _current(request)
    if not a:
        return {"logged_in": False}
    return {"logged_in": True, "display_name": a["display_name"],
            "must_change_pwd": bool(a["must_change_pwd"]), "enabled": bool(a["enabled"])}


class LoginIn(BaseModel):
    phone: str
    password: str


@router.post("/login")
def login(body: LoginIn, response: Response):
    a = store.account_by_phone(body.phone.strip())
    if not a or not a.get("login_pwd_hash"):
        raise HTTPException(status_code=401, detail="手机号或密码错误")
    if not auth.verify_password(body.password, a["login_pwd_hash"]):
        raise HTTPException(status_code=401, detail="手机号或密码错误")
    if not a["enabled"]:
        raise HTTPException(status_code=403, detail="账号已被停用，请联系管理员")
    _set_session(response, a["id"])
    return {"ok": True, "must_change_pwd": bool(a["must_change_pwd"])}


class ChangePwdIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
def change_password(body: ChangePwdIn, request: Request):
    a = _current(request)
    if not a:
        raise HTTPException(status_code=401, detail="未登录")
    if not auth.verify_password(body.old_password, a["login_pwd_hash"]):
        raise HTTPException(status_code=400, detail="原密码不正确")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    if body.new_password == config.DEFAULT_TEACHER_PWD:
        raise HTTPException(status_code=400, detail="新密码不能与默认密码相同")
    store.set_login_password(a["id"], auth.hash_password(body.new_password), 0)
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(auth.TEACHER_COOKIE)
    return {"ok": True}


@router.get("/key")
def get_key(request: Request):
    a = _current(request)
    if not a:
        raise HTTPException(status_code=401, detail="未登录")
    if a["must_change_pwd"]:
        raise HTTPException(status_code=403, detail="请先修改初始密码")
    base = str(request.base_url).rstrip("/") + "/v1"
    return {"display_name": a["display_name"], "phone": a["phone"],
            "api_key": a["api_key"], "base_url": base,
            "models": store.enabled_model_names(),
            "enabled": bool(a["enabled"])}
