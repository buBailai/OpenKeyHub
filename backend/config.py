"""运行配置 / 路径 / 服务密钥。

刻意零外部依赖：.env 手工解析，密钥本地持久化，开箱即用。
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent          # 项目根
FRONTEND_DIR = APP_DIR / "frontend"
# 数据目录可用 OKH_DATA_DIR 覆盖（便于迁移备份 / 隔离测试，避免误删生产数据）
DATA_DIR = Path(os.environ["OKH_DATA_DIR"]).expanduser() if os.environ.get("OKH_DATA_DIR") else APP_DIR / "data"
DB_PATH = DATA_DIR / "openkeyhub.db"
SECRET_PATH = DATA_DIR / "secret.key"

DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_dotenv() -> None:
    """把 .env 里的 KEY=VALUE 灌进 os.environ（不覆盖已存在的）。"""
    f = APP_DIR / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

HOST = os.environ.get("OKH_HOST", "0.0.0.0")
PORT = int(os.environ.get("OKH_PORT", "8011"))

# 老师端默认登录密码（首次登录强制修改）
DEFAULT_TEACHER_PWD = os.environ.get("OKH_DEFAULT_PWD", "openkeyhub")

# 转发上游时的超时（秒）：连接短、读取长（大模型可能慢，别替客户端提前掐断）
UPSTREAM_CONNECT_TIMEOUT = float(os.environ.get("OKH_CONNECT_TIMEOUT", "20"))
UPSTREAM_READ_TIMEOUT = float(os.environ.get("OKH_READ_TIMEOUT", "300"))


def server_secret() -> str:
    """会话签名密钥：优先 env，否则本地持久化一份随机值。"""
    env = os.environ.get("OKH_SECRET")
    if env:
        return env
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text(encoding="utf-8").strip()
    s = secrets.token_hex(32)
    SECRET_PATH.write_text(s, encoding="utf-8")
    try:
        SECRET_PATH.chmod(0o600)
    except Exception:
        pass
    return s
