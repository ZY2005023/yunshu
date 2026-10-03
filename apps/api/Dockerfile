# 宁渡课堂 · FastAPI 后端
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 依赖单独一层，改代码时不用重装
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        fastapi "uvicorn[standard]" sqlalchemy alembic pymysql cryptography \
        pyjwt bcrypt python-multipart pydantic-settings email-validator openai \
        python-docx pypdf

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# 上传目录与前端产物（dist 由前端构建阶段拷进来）
RUN mkdir -p /app/uploads /app/static

EXPOSE 1236

# ⚠️ 必须单 worker。多 worker 会静默破坏两处功能 —— 它们都是**进程内内存**实现：
#
#   · app/core/blacklist.py 的 token 黑名单 → 令牌只被处理该请求的那个 worker 记住，
#     后续请求落到别的 worker 会照样放行 → **登出/改密可能不生效**（安全漏洞）
#   · app/services/ai.py 的对话记忆 _store → 同一会话的历史分散在不同 worker，
#     用户会发现「刚才说过的事它忘了」
#
# 要让 workers > 1，必须先把这两个状态外置到 Redis，否则不要动这个值。
# 注意：SSE 长连接会占住 worker，单 worker 下的并发上限就是 1 个在途请求 ——
# 这是已知取舍，扩容的前提同样是先外置状态。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "1236", "--workers", "1"]
