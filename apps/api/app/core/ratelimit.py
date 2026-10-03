"""进程内滑动窗口限流器 —— 上线前必须补的最后一道闸。

为什么必须有：此前登录接口可无限爆破、AI 接口可被脚本刷
（README 第六节 D 项明确的缺口）。单 worker 部署下进程内计数器
没有一致性问题；**横向扩容时与令牌黑名单 / 对话记忆 / 运行时配置
一起外置到 Redis**，不要在多 worker 下假装它有效。

用 法（三处收口，见各 router）：
    login_limiter.check(f"{ip}|{username}")     # 防爆破
    login_ip_limiter.check(ip)                  # 防同 IP 撞库
    ai_limiter.check(f"user:{user_id}")         # 防刷 AI 额度

配置（环境变量，读取发生在每次 check 时 —— 改 .env 重启生效，测试可 monkeypatch）：
    RATE_LIMIT_LOGIN_PER_MIN   默认 5   设 0 关闭
    RATE_LIMIT_LOGIN_IP_PER_MIN 默认 30 设 0 关闭
    RATE_LIMIT_AI_PER_MIN      默认 10  设 0 关闭
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from app.core.exceptions import BusinessError


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class SlidingWindowLimiter:
    """滑动窗口计数器。超限抛业务异常（HTTP 200 + code 6000，与全站错误形态一致）。"""

    def __init__(self, env_var: str, default_max: int, window_seconds: float, msg: str) -> None:
        self._env_var = env_var
        self._default_max = default_max
        self._window = window_seconds
        self._msg = msg
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = 0.0

    def _limit(self) -> int:
        return _int_env(self._env_var, self._default_max)

    def check(self, key: str) -> None:
        limit = self._limit()
        if limit <= 0:  # 显式关闭
            return
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self._window:
                hits.popleft()
            if len(hits) >= limit:
                raise BusinessError(self._msg)
            hits.append(now)
            # 惰性清扫：key（IP/账号组合）无限增长会把内存吃掉
            if len(self._hits) > 10_000 or now - self._last_sweep > 600:
                self._sweep(now)

    def _sweep(self, now: float) -> None:
        expired = [k for k, q in self._hits.items() if not q or now - q[-1] > self._window]
        for k in expired:
            del self._hits[k]
        self._last_sweep = now

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# ---- 全局实例（限流器必须有状态，注册进 _ALL 供测试重置）----

login_limiter = SlidingWindowLimiter(
    "RATE_LIMIT_LOGIN_PER_MIN", 5, 60.0, "登录尝试过于频繁，请一分钟后再试"
)
login_ip_limiter = SlidingWindowLimiter(
    "RATE_LIMIT_LOGIN_IP_PER_MIN", 30, 60.0, "该网络登录请求过于频繁，请稍后再试"
)
ai_limiter = SlidingWindowLimiter(
    "RATE_LIMIT_AI_PER_MIN", 10, 60.0, "请求过于频繁，请稍后再试"
)

_ALL = (login_limiter, login_ip_limiter, ai_limiter)


def reset_all() -> None:
    """测试隔离用：清空所有限流计数。"""
    for limiter in _ALL:
        limiter.reset()
