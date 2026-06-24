"""OpenKeyHub 入口：挂网关 + 后台 + 静态前端。"""
from __future__ import annotations

import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, admin, config, gateway, portal, store


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init()
    yield


app = FastAPI(title="OpenKeyHub", version=__version__, lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True, "service": "openkeyhub", "version": __version__}


app.include_router(gateway.router)
app.include_router(admin.router)
app.include_router(portal.router)


@app.get("/")
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")


@app.get("/portal")
def portal_page():
    return FileResponse(config.FRONTEND_DIR / "portal.html")


# 静态资源（CSS/JS/图标）
app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def run():
    import uvicorn
    ip = _lan_ip()
    print("\n  OpenKeyHub 已启动")
    print(f"  管理后台:   http://127.0.0.1:{config.PORT}/")
    print(f"  局域网:     http://{ip}:{config.PORT}/")
    print(f"  老师登录页:  http://{ip}:{config.PORT}/portal   （手机号登录，自助查 Key）")
    print(f"  客户端填:   http://{ip}:{config.PORT}/v1   + 各自的 Key\n")
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    run()
