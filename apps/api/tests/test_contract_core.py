"""契约层单元测试 —— 验证 Python 实现与 Java 版约定的行为一致。

这里每一个断言，都对应契约清单里的一条硬约束。
任何一条挂掉，就意味着前端会出问题。
"""

from __future__ import annotations

import base64
import json
import time

import pytest

from app.core.errors import (
    ACCESS_UNAUTHORIZED,
    SUCCESS,
    SYSTEM_ERROR,
    TOKEN_BLOCKED,
    TOKEN_EXPIRED,
    TOKEN_INVALID,
)
from app.core.result import Result
from app.core.security import (
    ISSUER,
    MIN_SECRET_LENGTH,
    TYPE_ACCESS,
    TYPE_REFRESH,
    JwtError,
    JwtExpiredError,
    JwtIssuerError,
    JwtSignatureError,
    create_access_token,
    create_refresh_token,
    expires_at,
    read_token_type,
    validate_access_token,
    verify,
)

# ===========================================================================
# Result：统一响应包装
# ===========================================================================

SECRET = "dev-placeholder-secret-change-me-in-production-0123456789"


class TestResult:
    def test_code_is_string_not_int(self):
        """契约清单 1.1：code 必须是字符串，返回整数会让全站判定失效。"""
        r = Result.ok()
        assert r.code == "200"
        assert isinstance(r.code, str), "code 必须是 str"

    def test_field_names_are_code_msg_data(self):
        """不是 message，是 msg。"""
        r = Result.ok({"a": 1})
        dumped = r.model_dump()
        assert set(dumped.keys()) == {"code", "msg", "data"}

    def test_ok_without_data_is_null(self):
        assert Result.ok().data is None

    def test_ok_message(self):
        assert Result.ok().msg == "操作成功"

    def test_fail_uses_error_code(self):
        r = Result.fail(SYSTEM_ERROR)
        assert r.code == "500"
        assert r.msg == "系统错误"

    def test_fail_can_override_message_but_keep_code(self):
        r = Result.fail(SYSTEM_ERROR, detail="AI 服务暂时不可用，请稍后再试")
        assert r.code == "500"
        assert r.msg == "AI 服务暂时不可用，请稍后再试"

    def test_error_bare_code(self):
        r = Result.error("500", "会话ID格式错误，请新建会话后重试", None)
        assert r.model_dump() == {
            "code": "500",
            "msg": "会话ID格式错误，请新建会话后重试",
            "data": None,
        }


# ===========================================================================
# ResultCode：错误码取值
# ===========================================================================


class TestErrorCodes:
    def test_success_code(self):
        assert SUCCESS.code == "200"

    def test_unauthorized(self):
        assert ACCESS_UNAUTHORIZED.code == "A0301"

    @pytest.mark.parametrize(
        "code_obj",
        [TOKEN_INVALID, TOKEN_EXPIRED, TOKEN_BLOCKED],
    )
    def test_three_token_errors_share_one_code(self, code_obj):
        """契约清单 1.2：这三个共用 A0230，别拆成三个不同的码。"""
        assert code_obj.code == "A0230"


# ===========================================================================
# JWT
# ===========================================================================


def _decode_payload(token: str) -> dict:
    part = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


class TestJwtStructure:
    def test_three_segments(self):
        token = create_access_token(user_id=1, username="alice", role_type=1, secret=SECRET)
        assert len(token.split(".")) == 3

    def test_header_alg_is_hs256(self):
        token = create_access_token(user_id=1, username="alice", role_type=1, secret=SECRET)
        header_raw = token.split(".")[0]
        header = json.loads(base64.urlsafe_b64decode(header_raw + "=" * (-len(header_raw) % 4)))
        assert header["alg"] == "HS256"
        assert header["typ"] == "JWT"

    def test_issuer(self):
        token = create_access_token(user_id=1, username="alice", role_type=1, secret=SECRET)
        assert _decode_payload(token)["iss"] == ISSUER
        assert ISSUER == "mental-health-assistant"

    def test_custom_claims(self):
        token = create_access_token(user_id=42, username="alice", role_type=2, secret=SECRET)
        payload = _decode_payload(token)
        assert payload["userId"] == 42
        assert payload["username"] == "alice"
        assert payload["roleType"] == 2
        assert payload["typ"] == TYPE_ACCESS

    def test_role_type_is_int_in_claim(self):
        """注意：roleType 在 claim 里是整数，在登录响应 JSON 里却是字符串。两种类型不一致是原版行为。"""
        token = create_access_token(user_id=1, username="alice", role_type=2, secret=SECRET)
        assert isinstance(_decode_payload(token)["roleType"], int)

    def test_refresh_token_has_its_own_type(self):
        token = create_refresh_token(user_id=1, username="alice", role_type=1, secret=SECRET)
        assert _decode_payload(token)["typ"] == TYPE_REFRESH


class TestJwtExpiry:
    def test_exp_is_seconds_not_milliseconds(self):
        """契约清单 1.4 补充：exp / iat 是秒级 Unix 时间戳，不是毫秒。

        Java 侧配置给的是毫秒（1800000），但 java-jwt 落进 payload 时是秒。
        """
        now_ms = int(time.time() * 1000)
        token = create_access_token(
            user_id=1, username="alice", role_type=1, secret=SECRET, issued_at_ms=now_ms
        )
        payload = _decode_payload(token)
        now_s = now_ms // 1000
        assert payload["exp"] == now_s + 1800, "exp 必须是秒级"
        assert payload["iat"] == now_s

    def test_default_access_ttl_is_30_minutes(self):
        now_ms = int(time.time() * 1000)
        token = create_access_token(
            user_id=1, username="alice", role_type=1, secret=SECRET, issued_at_ms=now_ms
        )
        payload = _decode_payload(token)
        assert payload["exp"] - payload["iat"] == 1800

    def test_default_refresh_ttl_is_7_days(self):
        now_ms = int(time.time() * 1000)
        token = create_refresh_token(
            user_id=1, username="alice", role_type=1, secret=SECRET, issued_at_ms=now_ms
        )
        payload = _decode_payload(token)
        assert payload["exp"] - payload["iat"] == 604800


class TestJwtVerify:
    def test_roundtrip(self):
        token = create_access_token(user_id=7, username="bob", role_type=1, secret=SECRET)
        payload = verify(token, SECRET)
        assert payload["userId"] == 7

    def test_wrong_secret_rejected(self):
        token = create_access_token(user_id=1, username="alice", role_type=1, secret=SECRET)
        with pytest.raises(JwtSignatureError):
            verify(token, "another-secret-that-is-long-enough-0123456789")

    def test_tampered_payload_rejected(self):
        token = create_access_token(user_id=1, username="alice", role_type=1, secret=SECRET)
        head, payload_b64, sig = token.split(".")
        fake = {"userId": 999, "username": "hacker", "roleType": 2, "typ": "access"}
        fake_b64 = (
            base64.urlsafe_b64encode(json.dumps(fake, separators=(",", ":")).encode())
            .rstrip(b"=")
            .decode()
        )
        with pytest.raises(JwtSignatureError):
            verify(f"{head}.{fake_b64}.{sig}", SECRET)

    def test_expired_token_rejected(self):
        past = int(time.time() * 1000) - 3_600_000
        token = create_access_token(
            user_id=1, username="alice", role_type=1, secret=SECRET,
            issued_at_ms=past, expiration_ms=1000,
        )
        with pytest.raises(JwtExpiredError):
            verify(token, SECRET)

    def test_wrong_issuer_rejected(self):
        """用别的密钥体系签的同结构 token，签发者对不上要拒绝。"""
        import hashlib
        import hmac as _hmac

        def b64(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
        payload = b64(
            json.dumps(
                {"userId": 1, "username": "x", "roleType": 1, "typ": "access",
                 "iat": int(time.time()), "exp": int(time.time()) + 600, "iss": "someone-else"},
                separators=(",", ":"),
            ).encode()
        )
        signing_input = f"{header}.{payload}"
        sig = b64(_hmac.new(SECRET.encode(), signing_input.encode(), hashlib.sha256).digest())
        with pytest.raises(JwtIssuerError):
            verify(f"{signing_input}.{sig}", SECRET)


class TestValidateAccessToken:
    def test_valid_access_token(self):
        token = create_access_token(user_id=3, username="carol", role_type=2, secret=SECRET)
        result = validate_access_token(token, SECRET)
        assert result is not None
        assert result.user_id == 3
        assert result.username == "carol"
        assert result.role_type == 2
        assert result.valid is True
        assert result.issued_at > 0

    def test_refresh_token_cannot_access_business_api(self):
        """契约清单 1.4 规则 1：typ == refresh 不能用于业务接口。"""
        token = create_refresh_token(user_id=1, username="alice", role_type=1, secret=SECRET)
        assert validate_access_token(token, SECRET) is None

    def test_missing_claim_returns_none(self):
        now = int(time.time() * 1000)
        token = create_access_token(
            user_id=0, username="", role_type=1, secret=SECRET, issued_at_ms=now
        )
        # username 为空时应判为无效
        assert validate_access_token(token, SECRET) is None

    def test_expired_returns_none(self):
        past = int(time.time() * 1000) - 7_200_000
        token = create_access_token(
            user_id=1, username="alice", role_type=1, secret=SECRET,
            issued_at_ms=past, expiration_ms=1000,
        )
        assert validate_access_token(token, SECRET) is None


class TestSecretStrength:
    def test_short_secret_rejected(self):
        with pytest.raises(ValueError, match="长度不足"):
            create_access_token(user_id=1, username="a", role_type=1, secret="short")

    def test_min_length_constant(self):
        assert MIN_SECRET_LENGTH == 32


class TestTokenHelpers:
    def test_read_token_type(self):
        access = create_access_token(user_id=1, username="a", role_type=1, secret=SECRET)
        refresh = create_refresh_token(user_id=1, username="a", role_type=1, secret=SECRET)
        assert read_token_type(access, SECRET) == TYPE_ACCESS
        assert read_token_type(refresh, SECRET) == TYPE_REFRESH

    def test_expires_at_is_milliseconds(self):
        """工具方法对外统一返回毫秒，方便与 Java 侧的 Date.getTime() 对齐。"""
        token = create_access_token(user_id=1, username="a", role_type=1, secret=SECRET)
        assert expires_at(token, SECRET) > time.time() * 1000 - 1000

    def test_expires_at_zero_on_failure(self):
        assert expires_at("not-a-token", SECRET) == 0

    def test_empty_token_raises(self):
        with pytest.raises(JwtError):
            verify("", SECRET)
