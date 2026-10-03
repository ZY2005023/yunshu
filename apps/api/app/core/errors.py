"""错误码常量。

值必须与 Java 版 `common/ResultCode` 逐字一致，尤其是 A0230 那种
"三个不同含义共用一个码"的地方 —— 看起来像 bug，但前端可能依赖它。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorCode:
    code: str
    msg: str


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------

SUCCESS = ErrorCode("200", "操作成功")

ERROR = ErrorCode("-1", "操作失败")

PARAM_ERROR = ErrorCode("400", "参数错误")

PARAM_IS_INVALID = PARAM_ERROR  # 兼容别名

PARAM_NOT_COMPLETE = ErrorCode("4001", "参数缺失")

PARAM_INVALID = ErrorCode("4002", "参数格式不正确")

PARAM_TYPE_ERROR = PARAM_INVALID  # 兼容别名

SYSTEM_ERROR = ErrorCode("500", "系统错误")

UNAUTHORIZED = ErrorCode("401", "暂未登录或token已经过期")

# ---------------------------------------------------------------------------
# 令牌
#
# ⚠️ 下面三个共用同一个 code "A0230"，是刻意保留的，不要拆成三个不同的码。
# ---------------------------------------------------------------------------

TOKEN_INVALID = ErrorCode("A0230", "token无效")

TOKEN_EXPIRED = ErrorCode("A0230", "token已过期")

TOKEN_BLOCKED = ErrorCode("A0230", "token已加入黑名单")

TOKEN_ACCESS_FORBIDDEN = ErrorCode("A0231", "token已被禁止访问")

AUTHORIZED_ERROR = ErrorCode("A0300", "访问权限异常")

ACCESS_UNAUTHORIZED = ErrorCode("A0301", "访问未授权")

# ---------------------------------------------------------------------------
# 文件
# ---------------------------------------------------------------------------

FILE_NOT_FOUND = ErrorCode("5001", "文件不存在")

FILE_UPLOAD_FAILED = ErrorCode("5002", "文件上传失败")

FILE_DELETE_FAILED = ErrorCode("5003", "文件删除失败")

FILE_SIZE_EXCEEDED = ErrorCode("5004", "文件大小超过限制")

FILE_TYPE_NOT_SUPPORTED = ErrorCode("5005", "不支持的文件类型")

FILE_NAME_INVALID = ErrorCode("5006", "文件名不合法")

FILE_CONTENT_INVALID = ErrorCode("5007", "文件内容不合法")

FILE_SAVE_FAILED = ErrorCode("5008", "文件保存失败")

# ---------------------------------------------------------------------------
# 业务
# ---------------------------------------------------------------------------

BUSINESS_ERROR = ErrorCode("6000", "业务处理失败")

ACCOUNT_SAME = ErrorCode("6001", "用户名已存在")

ACCOUNT_NOT_FOUND = ErrorCode("6002", "用户不存在")
