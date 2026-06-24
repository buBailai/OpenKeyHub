"""敏感字段静态加密（厂家真实 Key、老师 api_key）。

零外部依赖：基于 HMAC-SHA256 的流加密 + encrypt-then-MAC（认证加密）。
密钥由 config.server_secret() 经 HKDF 派生，随服务持久化（data/secret.key）。
注意：secret.key 丢失则已加密数据不可恢复——请连同 db 一起备份。

兼容旧明文：解密时若无 `enc1:` 前缀，原样返回（便于平滑迁移）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from . import config

_PREFIX = "enc1:"
_keys: tuple[bytes, bytes] | None = None


def _hkdf(secret: bytes, info: bytes, length: int) -> bytes:
    salt = b"openkeyhub.kdf.v1"
    prk = hmac.new(salt, secret, hashlib.sha256).digest()
    okm, t, i = b"", b"", 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
        i += 1
    return okm[:length]


def _derive() -> tuple[bytes, bytes]:
    global _keys
    if _keys is None:
        sec = config.server_secret().encode()
        _keys = (_hkdf(sec, b"enc", 32), _hkdf(sec, b"mac", 32))
    return _keys


def _keystream(key: bytes, nonce: bytes, n: int) -> bytes:
    out, c = b"", 0
    while len(out) < n:
        out += hmac.new(key, nonce + c.to_bytes(4, "big"), hashlib.sha256).digest()
        c += 1
    return out[:n]


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def encrypt(plain: str) -> str:
    if not plain:
        return ""
    enc_key, mac_key = _derive()
    nonce = secrets.token_bytes(16)
    data = plain.encode("utf-8")
    ct = _xor(data, _keystream(enc_key, nonce, len(data)))
    tag = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()[:16]
    return _PREFIX + base64.urlsafe_b64encode(nonce + ct + tag).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    if not token.startswith(_PREFIX):
        return token                      # 旧明文，原样返回
    enc_key, mac_key = _derive()
    try:
        raw = base64.urlsafe_b64decode(token[len(_PREFIX):])
        nonce, body, tag = raw[:16], raw[16:-16], raw[-16:]
        expect = hmac.new(mac_key, nonce + body, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(tag, expect):
            return ""
        return _xor(body, _keystream(enc_key, nonce, len(body))).decode("utf-8")
    except Exception:
        return ""


def is_encrypted(token: str) -> bool:
    return bool(token) and token.startswith(_PREFIX)
