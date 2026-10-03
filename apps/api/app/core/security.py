"""JWT 签发与校验 —— 与 Java 版 `util/JwtTokenUtil`（java-jwt）严格对齐。

这里用标准库实现 HS256，不引入 PyJWT，目的有两个：
1. 立刻可写单元测试，不需要先装任何包；
2. HS256 的实现面很小，自己写反而便于逐字节对照 Java 版行为。

将来若要换成 PyJWT，只要保证下面这些常量不变，签名结果就是一致的。

────────────────────────────────────────────────────────────
对齐要点（改动任何一条都会导致 Java 版签发的 token 失效）
────────────────────────────────────────────────────────────
· 算法      HMAC-SHA256（HS256）
· 签发者    iss = "mental-health-assistant"
· 自定义声明 userId / username / roleType / typ
· typ 取值  "access" 或 "refresh"
· exp / iat **秒级** Unix 时间戳
            注意：application.yml 里配的 jwt.expiration 是毫秒（1800000），
            但 java-jwt 的 withExpiresAt(Date) 落进 payload 时是秒（JWT 标准
            NumericDate）。这里的 _ms_to_seconds 就是做这个转换，别漏。
· 密钥      HMAC256 要求 secret ≥ 32 字节
· jti       **本项目在 Java 版基础上新增**（RFC 7519 标准声明，随机 hex）。
            原因见 create_token 里的注释：不加的话，同一秒内签发的 token
            完全相同，「登出后立刻重新登录」会拿回已吊销的那个。
            额外的标准声明不影响双向验签（两边都只校验签名与各自用到的声明）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

ISSUER = "mental-health-assistant"
ALGORITHM = "HS256"

CLAIM_TOKEN_TYPE = "typ"
TYPE_ACCESS = "access"
TYPE_REFRESH = "refresh"

CLAIM_USER_ID = "userId"
CLAIM_USERNAME = "username"
CLAIM_ROLE_TYPE = "roleType"

MIN_SECRET_LENGTH = 32


# ===========================================================================
# 异常
# ===========================================================================


class JwtError(Exception):
    """JWT 相关异常的基类。"""


class JwtMalformedError(JwtError):
    """令牌结构不合法（不是三段、头部或载荷不是合法 JSON）。"""


class JwtSignatureError(JwtError):
    """签名校验失败。"""


class JwtExpiredError(JwtError):
    """令牌已过期。"""


class JwtIssuerError(JwtError):
    """签发者不匹配。"""


# ===========================================================================
# base64url
# ===========================================================================


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _serialize(part: dict[str, Any]) -> str:
    """紧凑 JSON。java-jwt 输出不带多余空格，这里保持一致。"""
    return _b64url_encode(json.dumps(part, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


# ===========================================================================
# 签发
# ===========================================================================


def _check_secret(secret: str) -> None:
    if not secret or len(secret) < MIN_SECRET_LENGTH:
        raise ValueError(
            f"jwt.secret 未配置或长度不足 {MIN_SECRET_LENGTH} 位，"
            "请通过环境变量 JWT_SECRET 注入强密钥"
        )


def _ms_to_seconds(ms: int) -> int:
    """毫秒 TTL → 秒。不做 round，向下取整，与 java-jwt 的 Date 截断行为一致。"""
    return ms // 1000


def build_token(
    *,
    user_id: int,
    username: str,
    role_type: int,
    token_type: str,
    ttl_ms: int,
    secret: str,
    issued_at_ms: int | None = None,
) -> str:
    """签发一个令牌。

    Args:
        user_id: 用户主键（JWT 里是整数）
        username: 用户名
        role_type: 1 = 普通用户，2 = 管理员
        token_type: TYPE_ACCESS 或 TYPE_REFRESH
        ttl_ms: 有效期，**毫秒**（与 Java 侧配置单位一致）
        secret: JWT 密钥
        issued_at_ms: 指定签发时刻，便于测试；不传则取当前时间
    """
    _check_secret(secret)

    ttl_ms = ttl_ms if ttl_ms > 0 else 1_800_000
    now_ms = issued_at_ms if issued_at_ms is not None else int(time.time() * 1000)
    now_s = now_ms // 1000
    exp_s = now_s + _ms_to_seconds(ttl_ms)

    header = {"alg": ALGORITHM, "typ": "JWT"}
    payload = {
        CLAIM_USER_ID: user_id,
        CLAIM_USERNAME: username,
        CLAIM_ROLE_TYPE: role_type,
        CLAIM_TOKEN_TYPE: token_type,
        "iat": now_s,
        "exp": exp_s,
        "iss": ISSUER,
        # jti（JWT ID，RFC 7519 标准声明）：本次签发的唯一标识。
        #
        # 不能省。JWT 是**确定性签名**：header/payload 完全一致时签出的字符串也完全一致。
        # 而同一次登录在**同一秒**内签发时，iat/exp 相同、其余声明也相同，
        # 于是签出来的是**同一个 token**。
        # 后果：用户「登出 → 立刻重新登录」拿回的是刚被吊销的那个 token，
        # 一用就 401（A0230 "token已加入黑名单"），隔一秒再试又正常 —— 很难排查。
        # 加上随机的 jti 后，每次签发的 token 都不同，问题不再存在。
        "jti": uuid.uuid4().hex,
    }

    signing_input = f"{_serialize(header)}.{_serialize(payload)}"
    signature = _sign(signing_input, secret)
    return f"{signing_input}.{signature}"


def _sign(signing_input: str, secret: str) -> str:
    raw = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(raw)


def create_access_token(
    *,
    user_id: int,
    username: str,
    role_type: int,
    secret: str,
    expiration_ms: int = 1_800_000,
    issued_at_ms: int | None = None,
) -> str:
    return build_token(
        user_id=user_id,
        username=username,
        role_type=role_type,
        token_type=TYPE_ACCESS,
        ttl_ms=expiration_ms,
        secret=secret,
        issued_at_ms=issued_at_ms,
    )


def create_refresh_token(
    *,
    user_id: int,
    username: str,
    role_type: int,
    secret: str,
    expiration_ms: int = 604_800_000,
    issued_at_ms: int | None = None,
) -> str:
    return build_token(
        user_id=user_id,
        username=username,
        role_type=role_type,
        token_type=TYPE_REFRESH,
        ttl_ms=expiration_ms,
        secret=secret,
        issued_at_ms=issued_at_ms,
    )


# ===========================================================================
# 校验
# ===========================================================================


@dataclass(frozen=True)
class TokenVerificationResult:
    """对应 Java 版 `JwtTokenUtil.TokenVerificationResult`。"""

    user_id: int
    username: str
    role_type: int
    issued_at: int  # 毫秒，用于比对用户的"全量吊销"时间点
    valid: bool


def verify(token: str, secret: str) -> dict[str, Any]:
    """校验签名、签发者与有效期，返回 payload。失败抛异常。

    注意：**只做令牌本身的校验**，不区分 access / refresh 类型，
    也不管黑名单 —— 那些是上层业务的事，与 Java 版职责划分一致。
    """
    if not token or not token.strip():
        raise JwtMalformedError("Token不能为空")

    parts = token.split(".")
    if len(parts) != 3:
        raise JwtMalformedError("Token格式不正确")

    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}"

    expected = _sign(signing_input, secret)
    if not hmac.compare_digest(expected, signature_b64):
        raise JwtSignatureError("Token签名校验失败")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:  # noqa: BLE001
        raise JwtMalformedError("Token载荷无法解析") from exc

    issuer = payload.get("iss")
    if issuer != ISSUER:
        raise JwtIssuerError(f"签发者不匹配: {issuer!r}")

    exp = payload.get("exp")
    if exp is None or int(time.time()) >= int(exp):
        raise JwtExpiredError("Token已过期")

    return payload


def validate_access_token(token: str, secret: str) -> TokenVerificationResult | None:
    """校验访问令牌。对应 Java 版 `validateToken`。

    返回 None 表示"应当按未登录处理"，包括：
    · 令牌是 refresh 类型（刷新令牌不得直接访问业务接口）
    · userId / username / roleType 任一缺失
    · 签名或有效期校验失败
    """
    try:
        payload = verify(token, secret)
    except JwtError:
        return None

    if payload.get(CLAIM_TOKEN_TYPE) == TYPE_REFRESH:
        return None

    user_id = payload.get(CLAIM_USER_ID)
    username = payload.get(CLAIM_USERNAME)
    role_type = payload.get(CLAIM_ROLE_TYPE)
    if user_id is None or not username or role_type is None:
        return None

    issued_at_s = int(payload.get("iat") or 0)
    return TokenVerificationResult(
        user_id=int(user_id),
        username=str(username),
        role_type=int(role_type),
        issued_at=issued_at_s * 1000,
        valid=True,
    )


def read_token_type(token: str, secret: str) -> str | None:
    """读取令牌类型。

    只负责取出 typ 声明，不叠加任何业务规则，
    类型是否合法由调用方决定（Java 版也是这么切的）。
    """
    try:
        payload = verify(token, secret)
    except JwtError:
        return None
    return payload.get(CLAIM_TOKEN_TYPE)


def expires_at(token: str, secret: str) -> int:
    """取过期时间戳（毫秒）。解析失败返回 0，与 Java 版 `expiresAt` 一致。"""
    try:
        payload = verify(token, secret)
    except JwtError:
        return 0
    return int(payload.get("exp", 0)) * 1000
