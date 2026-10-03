"""应用入口。

职责：只做装配 —— 异常处理、路由注册、静态资源、SPA 兜底。

⚠️ 三种响应形态，别搞混：
  1. 业务异常 / 参数校验 / 未捕获异常 → **HTTP 200** + Result 包装
  2. 认证失败（认证依赖层）            → HTTP 401 / 400 + Result 包装
  3. SSE 流                           → text/event-stream，无 Result 外层（见 stream 接口）
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.exceptions import BusinessError
from app.core.result import Result
from app.routers import analytics as analytics_router
from app.routers import ai_config as ai_config_router
from app.routers import chat as chat_router
from app.routers import crisis as crisis_router
from app.routers import diary as diary_router
from app.routers import file as file_router
from app.routers import knowledge as knowledge_router
from app.routers import scale as scale_router
from app.routers import user as user_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时把 sys_config 的运营期配置（AI 服务等）灌进运行时覆盖层。

    加载失败（表不存在 / 库没起来）只警告不退出 —— 此时回退 .env，
    与该表引入前的行为一致，不能因为可选配置把服务挡在门外。
    """
    from app.db import SessionLocal
    from app.services import ai_config as ai_config_service

    try:
        with SessionLocal() as db:
            loaded = ai_config_service.load_overrides_from_db(db)
        if loaded:
            logging.getLogger("app").info("已从 sys_config 加载 %s 项运营期配置（AI 服务）", loaded)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("app").warning("sys_config 加载失败，AI 配置回退环境变量: %s", exc)
    yield


app = FastAPI(
    title="云舒 · 后端服务",
    version="0.1.0",
    description="云舒 · AI 心理健康助手 后端服务",
    lifespan=lifespan,
)

# ⚠️ 同源部署时（前端 dist 由本服务托管）**根本不需要 CORS**，
#    CORS_ORIGINS 留空即完全不启用 —— 这是最安全的状态。
#    只有前后端拆到不同域名时才配，且必须写具体域名：
#    写 "*" 又带 allow_credentials=True，等于允许任意站点带着用户登录态读响应
#    （Starlette 会回显请求 Origin 并发出 Allow-Credentials: true）。
#    生产模式下的这类配置会在文件末尾的启动自检里被拦住。
_origins = settings.cors_origins
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ===========================================================================
# 异常处理
# ===========================================================================


def _json(payload: Result, status_code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


@app.exception_handler(BusinessError)
async def handle_business_error(_: Request, exc: BusinessError) -> JSONResponse:
    """业务异常 → HTTP 200 + Result(code, msg, null)。"""
    return _json(Result.error(exc.code, exc.msg, None))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """参数校验失败 → HTTP 200 + Result("400", "参数错误", "提示拼接")。

    各字段的默认提示用 ", " 拼成**一串**放进 data（不是数组）——
    前端按字符串直接展示，改动形状会让提示变成 [object Object]。
    """
    messages = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path"))
        msg = err.get("msg", "")
        messages.append(f"{loc}: {msg}" if loc else msg)
    return _json(Result.error("400", "参数错误", ", ".join(messages)))


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """认证/权限失败已在 deps 里包装成 {code,msg,data}，这里原样透出并保留状态码。"""
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return _json(Result.error(str(exc.status_code), str(detail)), status_code=exc.status_code)


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    """兜底：不把堆栈暴露给前端，只写日志。"""
    logging.getLogger("app").exception("未捕获异常: %s", exc)
    return _json(Result.error("500", "系统错误", None))


# ===========================================================================
# 路由
# ===========================================================================

app.include_router(user_router.router)
app.include_router(ai_config_router.router)
app.include_router(knowledge_router.router)
app.include_router(diary_router.router)
app.include_router(crisis_router.router)
app.include_router(file_router.router)
app.include_router(chat_router.router)
app.include_router(scale_router.router)
app.include_router(analytics_router.router)


# ===========================================================================
# 静态资源
#
# `/files/**` 保持匿名可访问：<img> 标签带不了 Authorization 头。
# 防枚举依靠上传时的 UUID 文件名 + 扩展名白名单（见 file 服务）。
# 路径前缀固定为 `/files/**`（前端所有图片都按这个前缀拼 URL）。
# ===========================================================================

# ⚠️ 必须与 file 服务写入用的是同一个目录（settings.file.upload_dir）——
#    这里如果写死相对 "uploads"，配置了 FILE_UPLOAD_DIR 的部署会把文件写到
#    配置目录、却从 ./uploads 去找，所有已传文件全部 404（测试发现不了）。
_UPLOAD_DIR = Path(settings.file.upload_dir)
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=str(_UPLOAD_DIR)), name="files")

# 前端产物：存在才挂，方便后端单独调试
_DIST = Path("static")
if (_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")


@app.get("/", include_in_schema=False)
def index():
    index_file = _DIST / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return {"service": "云舒 · 后端服务", "docs": "/docs"}


@app.get("/actuator/health", include_in_schema=False)
def health():
    """匿名只拿得到 UP —— 不含数据库等组件明细，外部探测拿不到内部信息。"""
    return {"status": "UP"}


# ===========================================================================
# SPA 兜底路由
#
# 前端用 history 模式路由（createWebHistory），且生产形态由本服务托管 dist ——
# 没有兜底的话，用户在 /profile、/back/crisis 上按 F5 或直接粘贴链接，
# 拿到的是 JSON 404：**除首页外所有页面都不可直达**。
#
# 两条边界必须守住：
#   · API / 已挂载前缀（/api/**、/files/**、/assets/**）不进兜底 ——
#     未知的 API 路径仍然返回 JSON 404，前端请求层的错误处理才能依赖这个形状；
#   · 兜底前先做路径穿越校验，解析后必须仍落在 dist 目录内。
# ===========================================================================

@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    index_file = _DIST / "index.html"
    if not index_file.is_file():
        # dist 未构建（纯后端调试场景）：保持旧行为，返回 JSON 404
        raise StarletteHTTPException(status_code=404)

    if full_path.startswith(("api/", "files/", "assets/")):
        raise StarletteHTTPException(status_code=404)

    if full_path:
        candidate = (_DIST / full_path).resolve()
        if (
            str(candidate).startswith(str(_DIST.resolve()) + os.sep)
            and candidate.is_file()
        ):
            # dist 里的真实静态文件（favicon.ico 等）直接命中
            return FileResponse(candidate)

    return FileResponse(index_file)


# ===========================================================================
# 生产启动自检
#
# 只在 APP_ENV=production 时生效。为什么必须有这一段：
# JWT 占位密钥有 54 个字符，能轻松通过 security.py 的「长度 ≥ 32」校验；
# CORS 通配、webhook 为空同样都是"能正常启动、但带着它上线会出事"。
# 这类问题不报错也不告警 —— 只能显式拦。宁可起不来，也不能静默带着上线。
# ===========================================================================

_problems = settings.startup_problems()
if _problems:
    for _p in _problems:
        logging.error("启动自检未通过：%s", _p)
    raise SystemExit(
        f"拒绝在生产模式启动：存在 {len(_problems)} 项高风险配置（明细见上方 ERROR）。"
        "修好后重启；若只是本地调试，把 APP_ENV 改回 development 即可。"
    )
