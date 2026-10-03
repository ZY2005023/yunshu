"""数据库会话与基类。

对应 Java 侧的 HikariCP + MyBatis-Plus 配置：
· maximum-pool-size  → pool_size
· minimum-idle 2     → 这里用 SQLAlchemy 的 pool_pre_ping 兜底，语义略有差异但目的一致
· connection-timeout 10000ms
"""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def build_sqlalchemy_url() -> str:
    """把 Java 风格的 jdbc url 转成 SQLAlchemy 能用的形式。

    支持两种输入：
    · `jdbc:mysql://host:3306/db?params` （复用 Java 版 .env 的 DB_URL）
    · `mysql+pymysql://host:3306/db`     （标准 SQLAlchemy url）
    """
    raw = settings.DB_URL
    if raw.startswith("jdbc:mysql://"):
        raw = "mysql+pymysql://" + raw[len("jdbc:mysql://") :]
    raw = raw.removeprefix("jdbc:")

    parsed = urlparse(raw)
    query = parse_qs(parsed.query)
    # Java url 里的这些参数 SQLAlchemy 不认，丢掉避免报错
    for key in ("useSSL", "serverTimezone", "useUnicode", "characterEncoding",
                "allowPublicKeyRetrieval", "rewriteBatchedStatements"):
        query.pop(key, None)
    from urllib.parse import urlencode

    new_query = urlencode({k: v[0] for k, v in query.items()})
    netloc = parsed.netloc
    if "@" not in netloc:
        netloc = f"{settings.DB_USERNAME}:{settings.DB_PASSWORD}@{parsed.netloc.lstrip('/')}"
    return f"{parsed.scheme}://{netloc}{parsed.path}" + (f"?{new_query}" if new_query else "")


engine = create_engine(
    build_sqlalchemy_url(),
    pool_size=max(1, settings.DB_POOL_SIZE),
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个会话，结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
