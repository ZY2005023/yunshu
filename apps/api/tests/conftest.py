"""pytest 夹具。

用 SQLite 内存库替换 MySQL，让测试**完全不依赖真实数据库** ——
这也是能安全验证"行为有没有变"的前提。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.blacklist import token_blacklist
from app.db import Base, get_db
from app.main import app
from app.models import User


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 同一内存库在多个连接间共享
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db_engine) -> Iterator[TestClient]:
    TestingSession = sessionmaker(bind=db_engine, class_=Session, expire_on_commit=False)

    def _override_get_db() -> Iterator[Session]:
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db

    # 黑名单是进程级单例，用例之间必须清空，否则互相串味
    token_blacklist._revoked_tokens.clear()
    token_blacklist._user_revoked_before.clear()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def registered_user(client: TestClient) -> dict:
    """一个已注册的普通用户，返回其基本凭据。"""
    payload = {
        "username": "alice",
        "email": "alice@example.com",
        "nickname": "爱丽丝",
        "password": "secret123",
        "confirmPassword": "secret123",
    }
    resp = client.post("/api/user/add", json=payload)
    assert resp.status_code == 200
    return payload


@pytest.fixture
def auth_headers(client: TestClient, registered_user: dict) -> dict:
    resp = client.post(
        "/api/user/login",
        json={"username": registered_user["username"], "password": registered_user["password"]},
    )
    token = resp.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(client: TestClient, db_engine, registered_user: dict) -> dict:
    """把 registered_user 提成管理员后重新登录。

    注意必须在改完 user_type **之后**登录 —— roleType 是签发 token 时写进 claim 的，
    用旧 token 拿不到管理员身份。
    """
    Session_ = sessionmaker(bind=db_engine, class_=Session, expire_on_commit=False)
    with Session_() as db:
        user = db.query(User).filter(User.username == registered_user["username"]).one()
        user.user_type = 2
        db.commit()

    resp = client.post(
        "/api/user/login",
        json={"username": registered_user["username"], "password": registered_user["password"]},
    )
    token = resp.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, class_=Session, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _no_real_ai_calls(monkeypatch):
    """测试默认切断真实 AI 调用。

    为什么必须这么做：不隔离的话，一旦 `.env` 里配了真的 AI_API_KEY，
    所有跟日记相关的用例都会真的去调 DeepSeek —— 既烧 token，
    又让断言不稳定（模型每次返回的内容都不一样）。

    之前这些用例能过，纯粹是因为当时没配 key，属于**对外部环境的隐式依赖**。
    需要验证真实 AI 行为的用例，自己 monkeypatch `analyze_emotion` 即可。
    """
    monkeypatch.setenv("AI_API_KEY", "")


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """限流器是进程级单例，用例之间必须清空 —— 否则先跑的用例把计数打满，
    后面的登录/对话用例会被 6000「过于频繁」误伤。"""
    from app.core.ratelimit import reset_all

    reset_all()
    yield
    reset_all()
