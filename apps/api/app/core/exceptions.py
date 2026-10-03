"""业务异常。

两种构造方式，对应 Java 侧 `BusinessException` 的两个重载：
    BusinessError("用户名或密码错误")            → code = -1（默认业务失败）
    BusinessError(ACCOUNT_SAME, "用户名已存在")  → code = 指定错误码，message 可覆盖
"""

from __future__ import annotations

from app.core.errors import BUSINESS_ERROR, ErrorCode


class BusinessError(Exception):
    def __init__(self, message: str | ErrorCode, detail: str | None = None) -> None:
        if isinstance(message, ErrorCode):
            self.code: str = message.code
            self.msg: str = detail or message.msg
        else:
            self.code = BUSINESS_ERROR.code
            self.msg = str(message)
        super().__init__(self.msg)


class ForbiddenError(BusinessError):
    """无权访问资源（不是本人也不是管理员）。"""

    def __init__(self, message: str = "无权访问该资源") -> None:
        super().__init__(message)
