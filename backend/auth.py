"""鉴权：老师 Key 生成/校验、管理员密码、会话签名。零外部依赖（全 stdlib）。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from . import config

_PBKDF_ROUNDS = 120_000


# ---------- 老师 API Key ----------
def new_api_key() -> str:
    """生成对外 Key：sk- 前缀 + URL-safe 随机串。"""
    return "sk-" + secrets.token_urlsafe(30)


def hash_key(key: str) -> str:
    """Key 只存哈希（带服务密钥的 HMAC，避免彩虹表）。"""
    return hmac.new(config.server_secret().encode(), key.encode(), hashlib.sha256).hexdigest()


def key_prefix(key: str) -> str:
    """展示用前缀，便于后台识别（如 sk-AbCd…）。"""
    return key[:7] + "…" if len(key) > 8 else key


# ---------- 管理员密码 ----------
def hash_password(pwd: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt, _PBKDF_ROUNDS)
    return f"pbkdf2${_PBKDF_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(pwd: str, stored: str) -> bool:
    try:
        _algo, rounds, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ---------- 会话（签名 cookie；按角色分 cookie，互不干扰） ----------
SESSION_COOKIE = "okh_session"      # 管理员
TEACHER_COOKIE = "okh_teacher"      # 老师端
_SESSION_TTL = 7 * 24 * 3600


def make_session(sub_id: int, role: str = "admin") -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": sub_id, "role": role, "exp": int(time.time()) + _SESSION_TTL}).encode()
    ).decode()
    sig = hmac.new(config.server_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def read_session(token: str | None, role: str = "admin") -> int | None:
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expect = hmac.new(config.server_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except Exception:
        return None
    if data.get("exp", 0) < int(time.time()):
        return None
    if data.get("role") != role:
        return None
    return data.get("sub")
