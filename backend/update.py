"""在线更新：检查更新源 → 下载校验 → 解压待命 → updater 脚本换目录并重启。

设计对齐信息科技平台的自更新，但适配 OpenKeyHub 的**扁平**免安装包目录：

    包根/ (OKH_ROOT)
      启动OpenKeyHub.bat        ← 启动器，永不更新
      使用说明.txt              ← 永不更新
      python/                   ← 内置运行时，仅大版本换整包，不在线更新
      data/                     ← 运行数据（db / secret.key），**必须保留**
      .env                      ← 用户配置，**必须保留**
      backend/  frontend/  CHANGELOG.md   ← 程序本体，在线更新只换这几项

刻意**按白名单选择性覆盖**（只动 backend/ frontend/ CHANGELOG.md），不做整目录 swap，
以免误伤 data/ python/ .env 等用户资产。

更新源是一个静态目录 URL，内含 version.json：
    {"version":"1.1.0","zip":"OpenKeyHub-update-1.1.0.zip","sha256":"…","size":123,"notes":"…"}
zip 顶层 = backend/、frontend/、CHANGELOG.md（可选 requirements.txt）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import urllib.request
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from . import admin, config, store

router = APIRouter(prefix="/api/admin/update", tags=["update"])

# 只更新这几项（白名单）；其余（python/ data/ .env / 启动器 / 使用说明）一律保留。
APP_ENTRIES = ["backend", "frontend", "CHANGELOG.md"]

# 下载/解压进度（单机部署，模块级状态足够）
STATE: dict = {"state": "idle", "pct": 0, "msg": "", "info": None}


class SourceIn(BaseModel):
    update_url: str = ""


def _update_url() -> str:
    return (store.get_setting("update_url") or config.DEFAULT_UPDATE_URL or "").rstrip("/")


def _ver_tuple(v: str):
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0,)


def _root() -> Path | None:
    return Path(config.PACKAGE_ROOT) if config.PORTABLE else None


def _new_dir() -> Path:
    """app_new 位置：便携包放包根；开发模式放数据目录（仅演练不应用）。"""
    root = _root()
    return (root / "app_new") if root else (config.DATA_DIR / "updates" / "app_new")


def _read_pkg_version(new_dir: Path) -> str:
    f = new_dir / "backend" / "__init__.py"
    try:
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read_text(encoding="utf-8"))
        return m.group(1) if m else "?"
    except OSError:
        return "?"


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "okh-updater"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


@router.get("/status")
def status(_: int = Depends(admin.require_admin)):
    return {"version": config.APP_VERSION, "portable": config.PORTABLE,
            "update_url": _update_url(),
            "pending": (_new_dir() / "backend" / "main.py").exists(),
            **{k: STATE[k] for k in ("state", "pct", "msg")}}


@router.post("/source")
def save_source(body: SourceIn, _: int = Depends(admin.require_admin)):
    store.set_setting("update_url", body.update_url.strip().rstrip("/"))
    return {"ok": True, "update_url": _update_url()}


@router.post("/check")
def check(_: int = Depends(admin.require_admin)):
    base = _update_url()
    if not base or "__UPDATE_SOURCE_PLACEHOLDER__" in base:
        return {"ok": False, "msg": "尚未配置更新源地址"}
    try:
        info = _fetch_json(base + "/version.json")
    except Exception as e:
        return {"ok": False, "msg": f"无法连接更新源：{str(e)[:120]}"}
    latest = str(info.get("version", ""))
    newer = _ver_tuple(latest) > _ver_tuple(config.APP_VERSION)
    STATE["info"] = info if newer else None
    return {"ok": True, "newer": newer, "current": config.APP_VERSION,
            "latest": latest, "notes": info.get("notes", ""),
            "size": info.get("size", 0)}


def _download_job(base: str, info: dict):
    try:
        STATE.update(state="downloading", pct=0, msg="正在下载更新包…", info=info)
        zip_name = info["zip"]
        url = zip_name if zip_name.startswith("http") else f"{base}/{zip_name}"
        tmp_dir = config.DATA_DIR / "updates"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_zip = tmp_dir / "pending.zip"
        req = urllib.request.Request(url, headers={"User-Agent": "okh-updater"})
        h = hashlib.sha256()
        with urllib.request.urlopen(req, timeout=30) as r, open(tmp_zip, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.get("size") or 0)
            done = 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if total:
                    STATE["pct"] = int(done * 90 / total)
        want = str(info.get("sha256", "")).lower()
        if want and h.hexdigest().lower() != want:
            raise RuntimeError("更新包校验失败（sha256 不符），已放弃")
        STATE.update(pct=92, msg="正在解压…")
        new_dir = _new_dir()
        if new_dir.exists():
            shutil.rmtree(new_dir)
        new_dir.mkdir(parents=True)
        with zipfile.ZipFile(tmp_zip) as z:
            for n in z.namelist():          # 防路径穿越
                if n.startswith("/") or ".." in Path(n).parts:
                    raise RuntimeError(f"更新包含非法路径：{n}")
            z.extractall(new_dir)
        # 有些打包工具会把内容套一层同名顶层夹，自动拆一层
        if not (new_dir / "backend" / "main.py").exists():
            subs = [p for p in new_dir.iterdir() if p.is_dir()]
            if len(subs) == 1 and (subs[0] / "backend" / "main.py").exists():
                inner = subs[0]
                for item in inner.iterdir():
                    shutil.move(str(item), str(new_dir / item.name))
                inner.rmdir()
        if not (new_dir / "backend" / "main.py").exists():
            raise RuntimeError("更新包结构不对（缺 backend/main.py）")
        got_ver = _read_pkg_version(new_dir)
        tmp_zip.unlink(missing_ok=True)
        STATE.update(state="ready", pct=100,
                     msg=f"新版 {got_ver} 已就绪，点击「重启完成升级」")
    except Exception as e:
        STATE.update(state="error", msg=str(e)[:200])


@router.post("/download")
def download(_: int = Depends(admin.require_admin)):
    if STATE["state"] == "downloading":
        return {"ok": True}
    info = STATE.get("info")
    if not info:
        return {"ok": False, "msg": "请先检查更新"}
    threading.Thread(target=_download_job, args=(_update_url(), info),
                     daemon=True).start()
    return {"ok": True}


# ---------------- 应用更新：写 updater 脚本 → 退出主程序 ----------------
# 只按白名单换 backend/ frontend/ CHANGELOG.md：先把旧的挪进 _bak/，再把 app_new 里的挪进来。
# 保留 python/ data/ .env / 启动器 / 使用说明。升级失败时 _bak/ 里有上一版可手动回滚。

_BAT = """@echo off
cd /d "%~dp0"
timeout /t 2 /nobreak >nul
rd /s /q _bak >nul 2>&1
mkdir _bak >nul 2>&1
{swaps}
rd /s /q app_new >nul 2>&1
start "" "启动OpenKeyHub.bat"
(goto) 2>nul & del "%~f0"
"""

_BAT_SWAP = (
    'if exist "{name}" move "{name}" "_bak\\{name}" >nul 2>&1\n'
    'move "app_new\\{name}" "{name}" >nul 2>&1'
)

_SH = """#!/bin/sh
cd "$(dirname "$0")"
sleep 2
rm -rf _bak && mkdir -p _bak
{swaps}
rm -rf app_new
nohup sh 启动OpenKeyHub.sh >/dev/null 2>&1 &
rm -f "$0"
"""

_SH_SWAP = (
    '[ -e "{name}" ] && mv "{name}" "_bak/{name}"\n'
    'mv "app_new/{name}" "{name}"'
)


@router.post("/apply")
def apply(request: Request, _: int = Depends(admin.require_admin)):
    root = _root()
    if not root:
        return {"ok": False,
                "msg": "开发模式下更新包已下载到数据目录 updates/app_new，不执行目录切换（仅免安装包模式支持一键重启升级）"}
    new_dir = _new_dir()
    if not (new_dir / "backend" / "main.py").exists():
        return {"ok": False, "msg": "没有待应用的新版，请先下载"}
    is_win = os.name == "nt"
    entries = [e for e in APP_ENTRIES if (new_dir / e).exists()]
    if is_win:
        swaps = "\n".join(_BAT_SWAP.format(name=e) for e in entries)
        script = root / "updater.bat"
        # bat 必须 GBK + CRLF：cmd 解析器遇到 UTF-8 中文/LF 换行会出各种诡异问题
        script.write_bytes(_BAT.format(swaps=swaps).replace("\n", "\r\n").encode("gbk"))
        subprocess.Popen(["cmd", "/c", str(script)], cwd=str(root),
                         creationflags=0x00000008 | 0x00000200)  # DETACHED|NEW_GROUP
    else:
        swaps = "\n".join(_SH_SWAP.format(name=e) for e in entries)
        script = root / "updater.sh"
        script.write_text(_SH.format(swaps=swaps), encoding="utf-8")
        script.chmod(0o755)
        subprocess.Popen(["/bin/sh", str(script)], cwd=str(root),
                         start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    threading.Timer(0.8, lambda: os._exit(0)).start()
    return {"ok": True, "msg": "正在重启升级，约 10 秒后刷新页面"}
