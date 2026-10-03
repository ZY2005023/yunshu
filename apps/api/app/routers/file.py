"""文件上传路由 —— 1 个接口。

`/api/file/upload` **不在白名单里**，需要有效 token；
userId 从 token 取，不从表单传（原版也是这么做的）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.result import Result
from app.deps import CurrentUser, get_current_user, get_db
from app.schemas import FileOut
from app.services import file as file_service

router = APIRouter(prefix="/api/file", tags=["文件"])


@router.post("/upload", response_model=Result[FileOut], summary="文件上传")
async def upload(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
    # ⚠️ 必须显式给 alias：FastAPI 的 Form() 默认用**参数名**当表单字段名，
    #    不加 alias 就会去找 business_type，而前端传的是 businessType ——
    #    结果是所有上传都静默落到 common 目录。
    business_type: Annotated[str | None, Form(alias="businessType")] = None,
    business_id: Annotated[str | None, Form(alias="businessId")] = None,
    business_field: Annotated[str | None, Form(alias="businessField")] = None,
) -> Result[FileOut]:
    """multipart 表单：file + 可选的 businessType / businessId / businessField。"""
    data = await file_service.upload(
        db, file, business_type, business_id, business_field, user.user_id
    )
    return Result.ok(FileOut(**data))
