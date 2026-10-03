"""运行时配置覆盖层 —— 让「页面上改配置」成为可能。

为什么需要这一层：AI 的 base_url / api_key / model 原来只能写在 .env 里，
改一次要重启服务。有了 sys_config 表 + 这层覆盖，
管理端「API 管理」页保存后**即时生效**（所有读取都走 settings.ai 的 property，
每次都取最新值 —— 这是 config.py 刻意用 property 而非类属性的既有设计）。

线程安全：覆盖字典的读写都在锁内；单 worker 部署下并发压力极小，
锁是为了 pytest 与多线程调用点（notifier 守护线程等）不踩坑。

多实例部署注意：与令牌黑名单 / 对话记忆同样属于进程内状态 ——
要横向扩容时，这三个一起外置到 Redis（或改成读库 + 短缓存）。
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_overrides: dict[str, str] = {}


def set_many(values: dict[str, str]) -> None:
    """整体替换覆盖集（全量语义：没出现在 values 里的键即被清除，
    与「数据库行被删掉就回退环境变量」的回退规则一致）。"""
    with _lock:
        _overrides.clear()
        _overrides.update({k: v for k, v in values.items() if v is not None})


def get(key: str, default: str | None = None) -> str | None:
    with _lock:
        return _overrides.get(key, default)


def snapshot() -> dict[str, str]:
    with _lock:
        return dict(_overrides)


def clear() -> None:
    with _lock:
        _overrides.clear()
