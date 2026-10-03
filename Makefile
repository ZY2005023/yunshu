# 宁渡课堂 · 统一任务入口
#
# Python 后端和 Vue 前端是两套包管理器（pip / npm），没法用一条命令统管，
# 所以这里放一个 task runner 层 —— 与 aihot 根目录 package.json 的 scripts 一个作用。

PY      := apps/api/.venv/Scripts/python.exe

# ⚠️ 托管 node 的版本目录会变（22.22.2-3 → 22.22.2-5 换过一次，
#    写死路径会让 make web/build 直接失败）。这里用通配自动取。
NODE    := $(firstword $(wildcard C:/Users/23540/.workbuddy/binaries/node/versions/*/node.exe))
VITE    := apps/web/node_modules/vite/bin/vite.js

.DEFAULT_GOAL := help

help:
	@echo ""
	@echo "  宁渡课堂 · 常用命令"
	@echo "  ----------------------------------------"
	@echo "  make setup     首次准备：建虚拟环境并装依赖"
	@echo "  make api       只起后端(1236)"
	@echo "  make web       只起前端(5173)"
	@echo "  make test      跑后端全部测试(SQLite 内存库)"
	@echo "  make e2e       端到端全功能测试(真实后端+MySQL)"
	@echo "  make api-docs  导出 Apifox 可直接导入的 OpenAPI"
	@echo "  make lint      ruff 静态检查"
	@echo "  make build     构建前端到 apps/web/dist"
	@echo "  make migrate   执行数据库迁移（需先起 MySQL）"
	@echo "  make revision m=说明   自动生成迁移脚本"
	@echo ""

setup:
	cd apps/api && python -m venv .venv && .venv/Scripts/python.exe -m pip install -q --upgrade pip
	cd apps/api && .venv/Scripts/python.exe -m pip install -q fastapi "uvicorn[standard]" sqlalchemy alembic pymysql cryptography pyjwt bcrypt python-multipart pydantic-settings email-validator openai ruff pytest pytest-asyncio httpx

api:
	cd apps/api && $(PY) -m uvicorn app.main:app --reload --port 1236

web:
	cd apps/web && $(NODE) $(VITE)

test:
	cd apps/api && $(PY) -m pytest -q

# 端到端：打真实后端 + 真实 MySQL，覆盖 39 个接口与权限边界。
# 与 make test 的分工：pytest 验证"逻辑对不对"（SQLite），e2e 验证"接口通不通、字段名对不对"（真库）。
# 前置：先 make api 把后端起起来。会真实调用 2 次 AI。
e2e:
	$(PY) scripts/e2e_full.py

# 导出 Apifox 可直接导入的 OpenAPI 文件到 docs/openapi-apifox.json。
# FastAPI 原生的 /openapi.json 能导入但极难用：没有 baseUrl、没有认证声明
# （39 个接口都要手工加 Authorization 头），SSE 还被写成 application/json。
# 本目标补齐这些，并跑一遍只读接口把真实响应体填成示例。
# 前置：先 make api。会真实调用 1 次 AI 抓 SSE 报文，加 --no-sse 可跳过。
api-docs:
	$(PY) scripts/export_openapi.py

lint:
	cd apps/api && $(PY) -m ruff check app tests

fmt:
	cd apps/api && $(PY) -m ruff check app tests --fix

build:
	cd apps/web && $(NODE) $(VITE) build

migrate:
	cd apps/api && $(PY) -m alembic upgrade head

revision:
	cd apps/api && $(PY) -m alembic revision --autogenerate -m "$(m)"

downgrade:
	cd apps/api && $(PY) -m alembic downgrade -1

webtest:
	cd apps/web && $(NODE) node_modules/vitest/vitest.mjs run
