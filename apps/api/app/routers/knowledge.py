"""知识库路由 —— 文章 7 个 + 分类 1 个 = 8 个接口。

权限分布（照搬原版，**不要"顺手统一"**）：
· `/api/knowledge/article/page` 虽然叫 page 且形似管理端，但**原版没有加 @PreAuthorize**，
  任何登录用户都能访问。保持原样。
· 4 个写操作（新增/更新/删除/改状态）需要 ADMIN。
· 分类树：登录即可。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.result import Result
from app.deps import CurrentUser, get_current_user, get_db, require_admin
from app.schemas import (
    ArticleIn,
    ArticleQuery,
    ArticleRow,
    ArticleStatusIn,
    CategoryRow,
    DocImportOut,
)
from app.services import content as content_service

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])


# ===========================================================================
# 文章
# ===========================================================================


@router.get("/article/page", response_model=Result[dict], summary="文章分页（管理端列表）")
def article_page(
    query: Annotated[ArticleQuery, Depends()],
    _user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[dict]:
    return Result.ok(content_service.page(db, query))


@router.get("/article", response_model=Result[dict], summary="文章分页（用户端列表）")
def article_list(
    query: Annotated[ArticleQuery, Depends()],
    _user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[dict]:
    return Result.ok(content_service.page(db, query))


@router.get("/article/{article_id}", response_model=Result[ArticleRow | None], summary="文章详情")
def article_detail(
    article_id: str,
    _user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[ArticleRow | None]:
    """文章不存在时返回 code=200 + data=null（**不是 404**，原版如此）。"""
    return Result.ok(content_service.detail(db, article_id))


@router.post("/article", response_model=Result[ArticleRow], summary="新增文章")
def article_create(
    payload: ArticleIn,
    user: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[ArticleRow]:
    from app.services import rag as rag_service

    article = content_service.create(db, user.user_id, payload)
    # 正文变了就要重建切片，否则 RAG 会检索到旧内容
    rag_service.reindex_article(db, article.id)
    return Result.ok(content_service._row(article, None, None))


@router.put("/article/{article_id}", response_model=Result[ArticleRow | None], summary="更新文章")
def article_update(
    article_id: str,
    payload: ArticleIn,
    _user: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[ArticleRow | None]:
    from app.services import rag as rag_service

    article = content_service.update(db, article_id, payload)
    if article is None:
        return Result.ok(None)
    rag_service.reindex_article(db, article.id)
    return Result.ok(content_service._row(article, None, None))


@router.delete("/article/{article_id}", response_model=Result[None], summary="删除文章")
def article_delete(
    article_id: str,
    _user: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[None]:
    import sqlalchemy as sa

    from app.models import KnowledgeChunk

    content_service.delete(db, article_id)
    # 文章没了，切片也要清掉，否则检索会命中已删除的内容
    for chunk in db.scalars(
        sa.select(KnowledgeChunk).where(KnowledgeChunk.article_id == article_id)
    ).all():
        db.delete(chunk)
    db.commit()
    return Result.ok()


@router.put("/article/{article_id}/status", response_model=Result[None], summary="修改发布状态")
def article_update_status(
    article_id: str,
    payload: ArticleStatusIn,
    _user: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[None]:
    content_service.update_status(db, article_id, payload.status)
    return Result.ok()


# ===========================================================================
# 分类
# ===========================================================================


@router.get("/category/tree", response_model=Result[list[CategoryRow]], summary="分类列表")
def category_tree(
    _user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[list[CategoryRow]]:
    return Result.ok(content_service.category_tree(db))


@router.post(
    "/admin/import-document",
    response_model=Result[DocImportOut],
    summary="导入文档为文章草稿（txt/md/docx/pdf）",
)
async def import_document(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    file: Annotated[UploadFile, File(...)],
) -> Result[DocImportOut]:
    """解析上传的文档并返回标题/正文（HTML），前端预填到编辑器供校对。

    **刻意不直接建文章**：解析有格式噪音，直接入库会污染 RAG 检索质量；
    心理类内容上线前也该人审一遍。保存仍走 POST /api/knowledge/article。
    """
    from app.services import doc_import

    raw = await file.read()
    return Result.ok(DocImportOut(**doc_import.parse_document(file.filename, raw)))


@router.post("/admin/reindex", response_model=Result[dict], summary="重建知识切片（RAG 索引）")
def reindex(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[dict]:
    """把已发布文章重新切片入库。

    正常不用手动跑 —— 文章的增删改会各自重建。这个接口用于：
    · 首次启用 RAG（历史文章还没有切片）
    · 批量导入文章之后
    · 怀疑索引不一致时手动修复
    """
    from app.services import rag as rag_service

    return Result.ok(rag_service.reindex_all(db))
