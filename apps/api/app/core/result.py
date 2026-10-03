"""统一响应包装 Result。

对应 Java 版 `common/Result`，三个字段：code / msg / data。

⚠️ 最关键的一点：**code 是字符串，不是整数**。
Java 版签名是 `private String code`，序列化出来是 `"200"` / `"A0301"`。
Python 版若返回 int，前端 `res.code === '200'` 的判定会全线失效。

另一个易错点：字段名是 `msg`，不是 `message`。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import ErrorCode, SUCCESS

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    """与前端约定的统一响应体。

    `data` 允许任意类型：对象、数组、标量、null 都行。
    """

    model_config = ConfigDict(populate_by_name=True)

    code: str = Field(default=SUCCESS.code, description="业务码，字符串类型")
    msg: str = Field(default=SUCCESS.msg, description="提示信息")
    data: T | None = Field(default=None, description="业务数据")

    @classmethod
    def ok(cls, data: Any = None, msg: str | None = None) -> "Result[Any]":
        """成功响应。不传 data 时为 null。"""
        return cls(code=SUCCESS.code, msg=msg or SUCCESS.msg, data=data)

    @classmethod
    def fail(cls, error: ErrorCode, detail: str | None = None, data: Any = None) -> "Result[Any]":
        """失败响应。detail 用于覆盖默认文案，同时保留原错误码。"""
        return cls(code=error.code, msg=detail or error.msg, data=data)

    @classmethod
    def error(cls, code: str, message: str, data: Any = None) -> "Result[Any]":
        """直接给定码与消息的失败响应（对应 Java 的 Result.error(code, msg, data)）。"""
        return cls(code=code, msg=message, data=data)


__all__ = ["Result"]
