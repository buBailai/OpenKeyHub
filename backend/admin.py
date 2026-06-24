"""管理后台 API：登录、厂家、模型路由、账号、统计。"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from . import auth, config, providers, store

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------- 鉴权 ----------
def require_admin(request: Request) -> int:
    aid = auth.read_session(request.cookies.get(auth.SESSION_COOKIE))
    if not aid:
        raise HTTPException(status_code=401, detail="未登录")
    return aid


class SetupIn(BaseModel):
    username: str
    password: str


@router.get("/state")
def state(request: Request):
    has_admin = store.admin_count() > 0
    logged_in = bool(auth.read_session(request.cookies.get(auth.SESSION_COOKIE)))
    return {"setup_required": not has_admin, "logged_in": logged_in}


@router.post("/setup")
def setup(body: SetupIn, response: Response):
    if store.admin_count() > 0:
        raise HTTPException(status_code=400, detail="管理员已存在")
    if len(body.username) < 2 or len(body.password) < 6:
        raise HTTPException(status_code=400, detail="用户名≥2位、密码≥6位")
    aid = store.create_admin(body.username, auth.hash_password(body.password))
    _set_session(response, aid)
    return {"ok": True}


@router.post("/login")
def login(body: SetupIn, response: Response):
    admin = store.get_admin(body.username)
    if not admin or not auth.verify_password(body.password, admin["pwd_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    _set_session(response, admin["id"])
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(auth.SESSION_COOKIE)
    return {"ok": True}


def _set_session(response: Response, aid: int):
    response.set_cookie(auth.SESSION_COOKIE, auth.make_session(aid),
                        httponly=True, samesite="lax", max_age=7 * 24 * 3600)


# ---------- 预设 ----------
@router.get("/presets")
def get_presets(_: int = Depends(require_admin)):
    return providers.public_list()


# ---------- 厂家 ----------
def _mask(p: dict) -> dict:
    d = dict(p)
    k = d.pop("api_key", "") or ""
    d["has_key"] = bool(k)
    d["key_mask"] = (k[:3] + "…" + k[-2:]) if len(k) > 6 else ("已配置" if k else "")
    return d


class ProviderIn(BaseModel):
    name: str
    preset: str = ""
    base_url: str
    api_key: str = ""
    note: str = ""
    models: list[str] = []


@router.get("/providers")
def get_providers(_: int = Depends(require_admin)):
    return [_mask(p) for p in store.list_providers()]


@router.post("/providers")
def add_provider(body: ProviderIn, _: int = Depends(require_admin)):
    pid = store.create_provider(body.name, body.preset, body.base_url.strip(),
                                body.api_key.strip(), body.note)
    for m in body.models:
        m = m.strip()
        if m and not store.route_for(m):
            store.add_model(m, pid, m)
    return {"id": pid}


class ProviderPatch(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None       # 空字符串=不改；显式传值才覆盖
    enabled: bool | None = None
    note: str | None = None


@router.put("/providers/{pid}")
def edit_provider(pid: int, body: ProviderPatch, _: int = Depends(require_admin)):
    fields = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.base_url is not None:
        fields["base_url"] = body.base_url.strip()
    if body.api_key:                      # 仅在传了非空值时更新 Key
        fields["api_key"] = body.api_key.strip()
    if body.enabled is not None:
        fields["enabled"] = int(body.enabled)
    if body.note is not None:
        fields["note"] = body.note
    store.update_provider(pid, **fields)
    return {"ok": True}


@router.delete("/providers/{pid}")
def remove_provider(pid: int, _: int = Depends(require_admin)):
    store.delete_provider(pid)
    return {"ok": True}


# ---------- 模型路由 ----------
class ModelIn(BaseModel):
    public_name: str
    provider_id: int
    upstream_model: str = ""
    note: str = ""


@router.get("/models")
def get_models(_: int = Depends(require_admin)):
    return store.list_models()


@router.post("/models")
def add_model(body: ModelIn, _: int = Depends(require_admin)):
    if store.route_for(body.public_name):
        raise HTTPException(status_code=400, detail=f"模型名 '{body.public_name}' 已存在")
    mid = store.add_model(body.public_name.strip(), body.provider_id,
                          body.upstream_model.strip() or body.public_name.strip(), body.note)
    return {"id": mid}


class ModelPatch(BaseModel):
    upstream_model: str | None = None
    enabled: bool | None = None
    note: str | None = None


@router.put("/models/{mid}")
def edit_model(mid: int, body: ModelPatch, _: int = Depends(require_admin)):
    fields = {}
    if body.upstream_model is not None:
        fields["upstream_model"] = body.upstream_model.strip()
    if body.enabled is not None:
        fields["enabled"] = int(body.enabled)
    if body.note is not None:
        fields["note"] = body.note
    store.update_model(mid, **fields)
    return {"ok": True}


@router.delete("/models/{mid}")
def remove_model(mid: int, _: int = Depends(require_admin)):
    store.delete_model(mid)
    return {"ok": True}


# ---------- 账号 ----------
class AccountIn(BaseModel):
    display_name: str
    phone: str = ""
    note: str = ""
    quota_total: int = 0
    rate_per_min: int = 0


def _default_login_hash() -> str:
    return auth.hash_password(config.DEFAULT_TEACHER_PWD)


def _new_account(display_name, phone="", note="", quota_total=0, rate_per_min=0):
    phone = (phone or "").strip()
    if phone and store.account_by_phone(phone):
        raise HTTPException(status_code=400, detail=f"手机号 {phone} 已存在")
    key = auth.new_api_key()
    # 有手机号才开通老师端登录（默认密码、首登强制改）
    login_hash = _default_login_hash() if phone else ""
    aid = store.create_account(display_name, auth.hash_key(key), auth.key_prefix(key), key,
                               note=note, phone=phone, login_pwd_hash=login_hash,
                               quota_total=quota_total, rate_per_min=rate_per_min)
    return aid, key


def _mask_account(a: dict) -> dict:
    d = dict(a)
    for k in ("api_key", "login_pwd_hash", "key_hash"):
        d.pop(k, None)
    d["has_login"] = bool(a.get("phone"))
    return d


@router.get("/accounts")
def get_accounts(_: int = Depends(require_admin)):
    return [_mask_account(a) for a in store.list_accounts()]


@router.post("/accounts")
def add_account(body: AccountIn, _: int = Depends(require_admin)):
    if not body.display_name.strip():
        raise HTTPException(status_code=400, detail="姓名不能为空")
    aid, key = _new_account(body.display_name.strip(), body.phone, body.note,
                            max(0, body.quota_total), max(0, body.rate_per_min))
    return {"id": aid, "api_key": key}      # 全 Key 只此一次返回


class ImportIn(BaseModel):
    text: str                                # CSV / 每行：姓名,手机号[,备注]
    quota_total: int = 0
    rate_per_min: int = 0


@router.post("/accounts/import")
def import_accounts(body: ImportIn, _: int = Depends(require_admin)):
    created, skipped = [], []
    reader = csv.reader(io.StringIO(body.text.strip()))
    for row in reader:
        if not row:
            continue
        name = (row[0] or "").strip()
        if not name or name in ("姓名", "name"):
            continue
        phone = (row[1].strip() if len(row) > 1 else "")
        note = (row[2].strip() if len(row) > 2 else "")
        try:
            aid, key = _new_account(name, phone, note,
                                    max(0, body.quota_total), max(0, body.rate_per_min))
            created.append({"id": aid, "display_name": name, "phone": phone, "note": note, "api_key": key})
        except HTTPException as e:
            skipped.append({"display_name": name, "phone": phone, "reason": e.detail})
    return {"count": len(created), "accounts": created, "skipped": skipped}


class AccountPatch(BaseModel):
    display_name: str | None = None
    phone: str | None = None
    note: str | None = None
    enabled: bool | None = None
    quota_total: int | None = None
    rate_per_min: int | None = None


@router.put("/accounts/{aid}")
def edit_account(aid: int, body: AccountPatch, _: int = Depends(require_admin)):
    fields = {}
    if body.display_name is not None:
        fields["display_name"] = body.display_name.strip()
    if body.phone is not None:
        phone = body.phone.strip()
        cur = store.account_by_id(aid)
        if phone and phone != (cur or {}).get("phone"):
            other = store.account_by_phone(phone)
            if other and other["id"] != aid:
                raise HTTPException(status_code=400, detail=f"手机号 {phone} 已被占用")
        fields["phone"] = phone
        # 新填手机号且原来没有登录密码 → 开通默认登录
        if phone and not (cur or {}).get("login_pwd_hash"):
            store.set_login_password(aid, _default_login_hash(), 1)
    if body.note is not None:
        fields["note"] = body.note
    if body.enabled is not None:
        fields["enabled"] = int(body.enabled)
    if body.quota_total is not None:
        fields["quota_total"] = max(0, body.quota_total)
    if body.rate_per_min is not None:
        fields["rate_per_min"] = max(0, body.rate_per_min)
    store.update_account(aid, **fields)
    return {"ok": True}


@router.post("/accounts/{aid}/reset-key")
def reset_key(aid: int, _: int = Depends(require_admin)):
    key = auth.new_api_key()
    store.update_account(aid, key_hash=auth.hash_key(key),
                         key_prefix=auth.key_prefix(key), api_key=key)
    return {"api_key": key}


@router.post("/accounts/{aid}/reset-login")
def reset_login(aid: int, _: int = Depends(require_admin)):
    a = store.account_by_id(aid)
    if not a or not a.get("phone"):
        raise HTTPException(status_code=400, detail="该账号未设置手机号，无法登录老师端")
    store.set_login_password(aid, _default_login_hash(), 1)
    return {"ok": True, "default_password": config.DEFAULT_TEACHER_PWD}


@router.post("/accounts/{aid}/reset-quota")
def reset_quota(aid: int, _: int = Depends(require_admin)):
    store.update_account(aid, quota_used=0)
    return {"ok": True}


@router.delete("/accounts/{aid}")
def remove_account(aid: int, _: int = Depends(require_admin)):
    store.delete_account(aid)
    return {"ok": True}


# ---------- 统计 ----------
@router.get("/stats")
def stats(_: int = Depends(require_admin)):
    return store.stats_overview()


@router.get("/logs")
def logs(account_id: int | None = None, limit: int = 200, _: int = Depends(require_admin)):
    return store.recent_logs(min(limit, 1000), account_id)
