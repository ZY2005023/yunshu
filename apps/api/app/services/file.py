"""文件上传业务（本地存储）—— 对齐 Java 版 `SysFileInfoService`。

五道防护（P0-5 加固，缺一道都是洞）：
  1. 扩展名白名单        —— html / svg / js / jsp 一律不可上传
  2. 文件头魔数校验      —— 挡住改后缀的伪装文件
  3. 大小上限            —— 来自环境变量 FILE_MAX_SIZE（默认 5MB）
  4. 文件名 UUID         —— 不可预测、不可枚举
  5. 路径穿越防护        —— businessType 白名单 + 规范化后必须在根目录内

返回的 `filePath` / `url` 形如 `/files/{businessType}/{uuid}.{ext}`，
与 WebConfig 的 `/files/**` 静态映射对应。
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    FILE_CONTENT_INVALID,
    FILE_NAME_INVALID,
    FILE_SAVE_FAILED,
    FILE_SIZE_EXCEEDED,
    FILE_TYPE_NOT_SUPPORTED,
    FILE_UPLOAD_FAILED,
)
from app.core.exceptions import BusinessError
from app.models import SysFileInfo

ALLOWED_BUSINESS_TYPES: frozenset[str] = frozenset(
    {"article", "avatar", "diary", "consultation", "common"}
)

# 各扩展名对应的文件头。未列出的类型（txt/mp3/wav/mp4/webp）跳过内容校验，
# 由扩展名白名单把关。
MAGIC_NUMBERS: dict[str, bytes] = {
    "jpg": b"\xff\xd8\xff",
    "jpeg": b"\xff\xd8\xff",
    "png": b"\x89PNG",
    "gif": b"GIF8",
    "bmp": b"BM",
    "pdf": b"%PDF",
    "docx": b"PK\x03\x04",  # 本质是 zip
    "xlsx": b"PK\x03\x04",
    "doc": b"\xd0\xcf\x11\xe0",  # OLE2 复合文档
    "xls": b"\xd0\xcf\x11\xe0",
}

_EXT_SANITIZE = re.compile(r"[^a-z0-9]")
_BUSINESS_SANITIZE = re.compile(r"[^a-z0-9_-]")


def allowed_extensions() -> set[str]:
    return {
        s.strip().lower()
        for s in settings.file.allowed_exts.split(",")
        if s.strip()
    }


def extract_extension(original_name: str | None) -> str:
    """取扩展名：只保留字母数字，长度上限 10，杜绝 "jpg/" 之类畸形输入。"""
    if not original_name:
        return ""
    dot = original_name.rfind(".")
    if dot < 0 or dot == len(original_name) - 1:
        return ""
    ext = _EXT_SANITIZE.sub("", original_name[dot + 1 :].lower())
    return "" if len(ext) > 10 else ext


def resolve_file_type(ext: str) -> str:
    if ext in ("jpg", "jpeg", "png", "gif", "webp", "bmp"):
        return "IMG"
    if ext == "pdf":
        return "PDF"
    if ext == "txt":
        return "TXT"
    if ext in ("doc", "docx"):
        return "DOC"
    if ext in ("xls", "xlsx"):
        return "XLS"
    if ext == "mp4":
        return "VIDEO"
    if ext in ("mp3", "wav"):
        return "AUDIO"
    return "OTHER"


def sanitize_business_type(business_type: str | None) -> str:
    """业务类型归一化：只允许白名单值，其余一律归到 common。这本身就是防穿越的一环。"""
    if not business_type or not business_type.strip():
        return "common"
    normalized = _BUSINESS_SANITIZE.sub("", business_type.lower())
    return normalized if normalized in ALLOWED_BUSINESS_TYPES else "common"


def verify_magic_number(content: bytes, ext: str) -> None:
    """文件头与扩展名比对，挡住改后缀的伪装文件。"""
    expected = MAGIC_NUMBERS.get(ext)
    if expected is None:
        return  # 该类型无统一魔数，已在扩展名白名单中把关
    if len(content) < len(expected):
        raise BusinessError(FILE_CONTENT_INVALID, "文件内容不完整")
    if content[: len(expected)] != expected:
        raise BusinessError(FILE_CONTENT_INVALID, "文件内容与扩展名不符（可能被篡改）")


async def upload(
    db: Session,
    file: UploadFile | None,
    business_type: str | None,
    business_id: str | None,
    business_field: str | None,
    user_id: int,
) -> dict[str, Any]:
    if file is None or not file.filename:
        raise BusinessError(FILE_UPLOAD_FAILED, "上传文件不能为空")

    content = await file.read()
    if not content:
        raise BusinessError(FILE_UPLOAD_FAILED, "上传文件不能为空")

    max_size = settings.file.max_size
    if len(content) > max_size:
        raise BusinessError(FILE_SIZE_EXCEEDED, f"文件大小超过限制（最大 {max_size // 1024 // 1024}MB）")

    original_name = file.filename
    ext = extract_extension(original_name)
    if not ext or ext not in allowed_extensions():
        raise BusinessError(
            FILE_TYPE_NOT_SUPPORTED,
            f"不支持的文件类型：{ext if ext else '未知'}",
        )
    verify_magic_number(content, ext)

    sub_dir = sanitize_business_type(business_type)
    base_dir = Path(settings.file.upload_dir).resolve()
    target_dir = (base_dir / sub_dir).resolve()

    # 规范化后必须仍落在上传根目录内，防目录穿越
    if target_dir != base_dir and not str(target_dir).startswith(str(base_dir) + os.sep):
        raise BusinessError(FILE_NAME_INVALID, "非法的存储路径")

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BusinessError(FILE_SAVE_FAILED, "创建上传目录失败") from exc

    stored_name = uuid.uuid4().hex + "." + ext
    target = target_dir / stored_name
    try:
        target.write_bytes(content)
    except OSError as exc:
        raise BusinessError(FILE_SAVE_FAILED, "文件保存失败") from exc

    access_path = f"/files/{sub_dir}/{stored_name}"

    info = SysFileInfo(
        original_name=original_name,
        file_path=access_path,
        file_size=len(content),
        file_type=resolve_file_type(ext),
        business_type=sub_dir,
        business_id=business_id,
        business_field=business_field,
        upload_user_id=user_id,
        is_temp=0,
        status=1,
        create_time=datetime.now(),
    )
    db.add(info)
    db.commit()
    db.refresh(info)

    return {
        "fileId": info.id,
        "filePath": access_path,
        "url": access_path,
        "originalName": original_name,
        "fileType": info.file_type,
        "fileSize": len(content),
    }
