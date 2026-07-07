"""运行配置 / 路径 / 服务密钥。

刻意零外部依赖：.env 手工解析，密钥本地持久化，开箱即用。
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from . import __version__

APP_VERSION = __version__

APP_DIR = Path(__file__).resolve().parent.parent          # 项目根
FRONTEND_DIR = APP_DIR / "frontend"

# 免安装包（portable）模式：启动器把 OKH_ROOT 设为包根目录；
# 兜底：包根下有内置 python 运行时（python/python.exe 或 python/bin/python）也判定为便携包。
PACKAGE_ROOT = os.environ.get("OKH_ROOT", "").strip() or (
    str(APP_DIR) if (APP_DIR / "python" / "python.exe").exists()
    or (APP_DIR / "python" / "bin" / "python").exists() else "")
PORTABLE = bool(PACKAGE_ROOT)

# 在线更新源：一个静态目录 URL，内含 version.json（+ 更新 zip）。
# 开源版默认留空（自部署者不会误连到别人的更新源）；官方免安装包在打包时注入
# 官方地址（或由启动器 / .env 设 OKH_UPDATE_URL）；管理员也可在后台改（存库，随数据保留）。
DEFAULT_UPDATE_URL = os.environ.get("OKH_UPDATE_URL", "").rstrip("/")
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
