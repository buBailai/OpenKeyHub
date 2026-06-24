"""SQLite 访问层。低并发、单文件、零运维。

约定：quota_total<=0 表示不限额；rate_per_min<=0 表示不限速。
真实厂家 Key 存库但绝不经 API 回显（前端只拿到掩码）。
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any, Optional

from . import config, crypto

_SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  pwd_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS providers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  preset TEXT DEFAULT '',
  base_url TEXT NOT NULL,
  api_key TEXT DEFAULT '',
  enabled INTEGER DEFAULT 1,
  note TEXT DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS models (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  public_name TEXT UNIQUE NOT NULL,
  provider_id INTEGER NOT NULL,
  upstream_model TEXT NOT NULL,
  enabled INTEGER DEFAULT 1,
  note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  display_name TEXT NOT NULL,
  phone TEXT DEFAULT '',
  note TEXT DEFAULT '',
  key_hash TEXT UNIQUE NOT NULL,
  key_prefix TEXT NOT NULL,
  api_key TEXT DEFAULT '',
  login_pwd_hash TEXT DEFAULT '',
  must_change_pwd INTEGER DEFAULT 1,
  enabled INTEGER DEFAULT 1,
  quota_total INTEGER DEFAULT 0,
  quota_used INTEGER DEFAULT 0,
  rate_per_min INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  last_used_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS call_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER,
  model TEXT,
  provider_id INTEGER,
  status TEXT,
  http_code INTEGER,
  prompt_tokens INTEGER DEFAULT 0,
  completion_tokens INTEGER DEFAULT 0,
  latency_ms INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_account ON call_logs(account_id);
CREATE INDEX IF NOT EXISTS idx_logs_created ON call_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_models_provider ON models(provider_id);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init() -> None:
    with _conn() as c:
        c.executescript(_SCHEMA)
    _migrate()


def _migrate() -> None:
    """给老库补新列（升级时不丢数据），并把历史明文 Key 就地加密。"""
    with _conn() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(accounts)")}
        for name, ddl in (
            ("phone", "TEXT DEFAULT ''"),
            ("api_key", "TEXT DEFAULT ''"),
            ("login_pwd_hash", "TEXT DEFAULT ''"),
            ("must_change_pwd", "INTEGER DEFAULT 1"),
        ):
            if name not in cols:
                c.execute(f"ALTER TABLE accounts ADD COLUMN {name} {ddl}")
        # 明文 → 密文（仅处理还没加密的）
        for tbl in ("providers", "accounts"):
            for r in c.execute(f"SELECT id, api_key FROM {tbl} WHERE api_key!=''"):
                if not crypto.is_encrypted(r["api_key"]):
                    c.execute(f"UPDATE {tbl} SET api_key=? WHERE id=?",
                              (crypto.encrypt(r["api_key"]), r["id"]))


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


# ---------- admins ----------
def admin_count() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]


def create_admin(username: str, pwd_hash: str) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO admins(username, pwd_hash, created_at) VALUES(?,?,?)",
            (username, pwd_hash, _now()),
        )
        return cur.lastrowid


def get_admin(username: str) -> Optional[dict]:
    with _conn() as c:
        r = c.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        return dict(r) if r else None


# ---------- providers ----------
def _dec_key(d: dict) -> dict:
    if d and d.get("api_key"):
        d["api_key"] = crypto.decrypt(d["api_key"])
    return d


def list_providers() -> list[dict]:
    with _conn() as c:
        return [_dec_key(r) for r in _rows(c.execute("SELECT * FROM providers ORDER BY id"))]


def get_provider(pid: int) -> Optional[dict]:
    with _conn() as c:
        r = c.execute("SELECT * FROM providers WHERE id=?", (pid,)).fetchone()
        return _dec_key(dict(r)) if r else None


def create_provider(name, preset, base_url, api_key, note) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO providers(name,preset,base_url,api_key,enabled,note,created_at)"
            " VALUES(?,?,?,?,1,?,?)",
            (name, preset, base_url, crypto.encrypt(api_key), note, _now()),
        )
        return cur.lastrowid


def update_provider(pid, **fields) -> None:
    if not fields:
        return
    if "api_key" in fields:
        fields["api_key"] = crypto.encrypt(fields["api_key"])
    cols = ", ".join(f"{k}=?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE providers SET {cols} WHERE id=?", (*fields.values(), pid))


def delete_provider(pid: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM models WHERE provider_id=?", (pid,))
        c.execute("DELETE FROM providers WHERE id=?", (pid,))


# ---------- models（路由表） ----------
def list_models() -> list[dict]:
    with _conn() as c:
        return _rows(c.execute(
            "SELECT m.*, p.name provider_name, p.enabled provider_enabled "
            "FROM models m JOIN providers p ON p.id=m.provider_id ORDER BY m.public_name"))


def add_model(public_name, provider_id, upstream_model, note="") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO models(public_name,provider_id,upstream_model,enabled,note)"
            " VALUES(?,?,?,1,?)",
            (public_name, provider_id, upstream_model or public_name, note),
        )
        return cur.lastrowid


def update_model(mid, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE models SET {cols} WHERE id=?", (*fields.values(), mid))


def delete_model(mid: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM models WHERE id=?", (mid,))


def route_for(public_name: str) -> Optional[dict]:
    """路由：对外模型名 → 启用的厂家 + 上游模型 + 真实 Key。"""
    with _conn() as c:
        r = c.execute(
            "SELECT m.upstream_model, p.id provider_id, p.name provider_name, "
            "p.base_url, p.api_key, p.enabled provider_enabled, m.enabled model_enabled "
            "FROM models m JOIN providers p ON p.id=m.provider_id "
            "WHERE m.public_name=?", (public_name,)).fetchone()
        return _dec_key(dict(r)) if r else None


def enabled_model_names() -> list[str]:
    with _conn() as c:
        return [r["public_name"] for r in c.execute(
            "SELECT m.public_name FROM models m JOIN providers p ON p.id=m.provider_id "
            "WHERE m.enabled=1 AND p.enabled=1 ORDER BY m.public_name")]


# ---------- accounts ----------
def list_accounts() -> list[dict]:
    with _conn() as c:
        return _rows(c.execute("SELECT * FROM accounts ORDER BY id DESC"))


def create_account(display_name, key_hash, key_prefix, api_key, note="", phone="",
                   login_pwd_hash="", quota_total=0, rate_per_min=0) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO accounts(display_name,phone,note,key_hash,key_prefix,api_key,"
            "login_pwd_hash,must_change_pwd,enabled,quota_total,quota_used,rate_per_min,created_at)"
            " VALUES(?,?,?,?,?,?,?,1,1,?,0,?,?)",
            (display_name, phone, note, key_hash, key_prefix, crypto.encrypt(api_key),
             login_pwd_hash, quota_total, rate_per_min, _now()),
        )
        return cur.lastrowid


def account_by_id(aid: int) -> Optional[dict]:
    with _conn() as c:
        r = c.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
        return _dec_key(dict(r)) if r else None


def account_by_phone(phone: str) -> Optional[dict]:
    with _conn() as c:
        r = c.execute("SELECT * FROM accounts WHERE phone=? AND phone!=''", (phone,)).fetchone()
        return _dec_key(dict(r)) if r else None


def set_login_password(aid: int, pwd_hash: str, must_change: int) -> None:
    with _conn() as c:
        c.execute("UPDATE accounts SET login_pwd_hash=?, must_change_pwd=? WHERE id=?",
                  (pwd_hash, must_change, aid))


def update_account(aid, **fields) -> None:
    if not fields:
        return
    if "api_key" in fields:
        fields["api_key"] = crypto.encrypt(fields["api_key"])
    cols = ", ".join(f"{k}=?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE accounts SET {cols} WHERE id=?", (*fields.values(), aid))


def delete_account(aid: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM accounts WHERE id=?", (aid,))


def account_by_key_hash(key_hash: str) -> Optional[dict]:
    with _conn() as c:
        r = c.execute("SELECT * FROM accounts WHERE key_hash=?", (key_hash,)).fetchone()
        return dict(r) if r else None


def bump_account_usage(aid: int) -> None:
    with _conn() as c:
        c.execute("UPDATE accounts SET quota_used=quota_used+1, last_used_at=? WHERE id=?",
                  (_now(), aid))


# ---------- call_logs ----------
def log_call(account_id, model, provider_id, status, http_code,
             prompt_tokens, completion_tokens, latency_ms) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO call_logs(account_id,model,provider_id,status,http_code,"
            "prompt_tokens,completion_tokens,latency_ms,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (account_id, model, provider_id, status, http_code,
             prompt_tokens, completion_tokens, latency_ms, _now()),
        )


def calls_in_last_minute(account_id: int) -> int:
    cutoff = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 60))
    with _conn() as c:
        return c.execute(
            "SELECT COUNT(*) n FROM call_logs WHERE account_id=? AND created_at>=?",
            (account_id, cutoff)).fetchone()["n"]


def recent_logs(limit=200, account_id: Optional[int] = None) -> list[dict]:
    with _conn() as c:
        if account_id:
            cur = c.execute(
                "SELECT l.*, a.display_name FROM call_logs l "
                "LEFT JOIN accounts a ON a.id=l.account_id WHERE l.account_id=? "
                "ORDER BY l.id DESC LIMIT ?", (account_id, limit))
        else:
            cur = c.execute(
                "SELECT l.*, a.display_name FROM call_logs l "
                "LEFT JOIN accounts a ON a.id=l.account_id ORDER BY l.id DESC LIMIT ?", (limit,))
        return _rows(cur)


def stats_overview() -> dict[str, Any]:
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) n FROM call_logs").fetchone()["n"]
        ok = c.execute("SELECT COUNT(*) n FROM call_logs WHERE status='ok'").fetchone()["n"]
        tokens = c.execute(
            "SELECT COALESCE(SUM(prompt_tokens+completion_tokens),0) t FROM call_logs"
        ).fetchone()["t"]
        per_acct = _rows(c.execute(
            "SELECT a.id, a.display_name, a.key_prefix, a.enabled, a.last_used_at, "
            "COUNT(l.id) calls, "
            "SUM(CASE WHEN l.status='ok' THEN 1 ELSE 0 END) ok_calls, "
            "COALESCE(SUM(l.prompt_tokens+l.completion_tokens),0) tokens "
            "FROM accounts a LEFT JOIN call_logs l ON l.account_id=a.id "
            "GROUP BY a.id ORDER BY calls DESC"))
        per_model = _rows(c.execute(
            "SELECT model, COUNT(*) calls, "
            "COALESCE(SUM(prompt_tokens+completion_tokens),0) tokens "
            "FROM call_logs GROUP BY model ORDER BY calls DESC"))
    return {"total_calls": total, "ok_calls": ok, "total_tokens": tokens,
            "per_account": per_acct, "per_model": per_model}
