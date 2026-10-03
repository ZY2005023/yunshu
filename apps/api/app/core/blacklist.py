"""Token 吊销名单 —— 对齐 Java 版 `util/TokenBlacklistService`。

⚠️ 与 Java 版同样是**进程内内存实现**：只在单实例部署下有效，重启即清空。
多实例请换成 Redis（过期逻辑可以直接映射）：
    SETEX blacklist:{token} <剩余有效期> 1
    SET   user:revoked_before:{userId} <毫秒时间戳>
"""

from __future__ import annotations

import threading
import time

DEFAULT_TTL_MS = 86_400_000  # 24 小时


class TokenBlacklist:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._revoked_tokens: dict[str, int] = {}  # token -> 该 token 自身过期时间（毫秒）
        self._user_revoked_before: dict[int, int] = {}  # userId -> 该时刻之前签发的全部作废

    def revoke(self, token: str | None, expires_at_millis: int = 0) -> None:
        """注销单个 token。有效期未知时按 24 小时兜底。"""
        if not token or not token.strip():
            return
        exp = expires_at_millis if expires_at_millis > 0 else int(time.time() * 1000) + DEFAULT_TTL_MS
        with self._lock:
            self._revoked_tokens[token] = exp
            self._cleanup()

    def revoke_all_before(self, user_id: int | None) -> None:
        """使某用户在当前时刻之前签发的所有 token 失效（改密 / 禁用 / 强制下线）。"""
        if user_id is None:
            return
        with self._lock:
            self._prune_user_entries()
            self._user_revoked_before[user_id] = int(time.time() * 1000)

    def _prune_user_entries(self) -> None:
        """清理已经不可能再拦住任何 token 的全量吊销点。

        token 最长寿命是 refresh 的 TTL（默认 7 天）—— 比它更早的吊销点
        对应的 token 早就过了 verify() 的过期校验，条目留着只是缓慢泄漏。
        余量取 refresh TTL + 1 天，避免与配置改动打架。需在持锁状态下调用。
        """
        try:
            from app.core.config import settings

            ttl_ms = settings.jwt.refresh_expiration
        except Exception:  # noqa: BLE001 —— 测试或极端环境下拿不到配置就保守不清理
            return
        horizon = int(time.time() * 1000) - (ttl_ms + 86_400_000)
        self._user_revoked_before = {
            u: t for u, t in self._user_revoked_before.items() if t >= horizon
        }

    def is_revoked(self, token: str | None) -> bool:
        """该 token 是否已被单独吊销。过期记录会被惰性清理。"""
        if not token or not token.strip():
            return False
        with self._lock:
            exp = self._revoked_tokens.get(token)
            if exp is None:
                return False
            now = int(time.time() * 1000)
            if exp > now:
                return True
            del self._revoked_tokens[token]
            return False

    def is_issued_before_revoke(self, user_id: int | None, issued_at_millis: int) -> bool:
        """该 token 的签发时间是否早于用户的"全量吊销"时间点。

        ⚠️ 这里必须留精度容差，原因是两边精度不一致：
          - JWT 的 `iat` 是**秒级**标准字段，解码后乘 1000 得到的是「那一秒的起点」毫秒值，
            无法区分同一秒内不同时刻签发的两个 token；
          - `revoked_before` 记录的是**精确到毫秒**的当前时刻。

        若直接比较，**同一秒内**完成「吊销 + 重新签发」时，新 token 的毫秒化 iat
        必然小于吊销时刻，会被误判为"已被吊销"。用户看到的现象是：
        **改密/强制下线后立刻重新登录，拿到的新令牌一用就 401**
        （隔一秒再登录就正常，所以很难复现和排查）。

        因此给签发时刻加上 999ms 容差：只有整个「签发秒」都早于吊销时刻，才算已吊销。
        代价是吊销最多延迟 1 秒生效，对安全无实质影响。
        """
        if user_id is None or issued_at_millis <= 0:
            return False
        with self._lock:
            revoked_before = self._user_revoked_before.get(user_id)
        if revoked_before is None:
            return False
        return issued_at_millis + 999 < revoked_before

    def _cleanup(self) -> None:
        """惰性清理已过期的吊销记录，避免字典无限增长。需在持锁状态下调用。"""
        now = int(time.time() * 1000)
        expired = [k for k, v in self._revoked_tokens.items() if v < now]
        for k in expired:
            del self._revoked_tokens[k]


token_blacklist = TokenBlacklist()
