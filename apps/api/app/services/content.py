"""知识库业务：文章 + 分类。

对齐 Java 版 `KnowledgeArticleService` / `KnowledgeCategoryService`。

关键点：
· 文章主键是 **UUID 字符串**
· 列表按 `created_at` **倒序**
· 详情接口有副作用：**访问即阅读数 +1**
· 入库前 content / summary 过 HTML 白名单清洗
· `statusText` 文章是「已发布/草稿」，分类是「启用/禁用」——两套文案别混
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.core.sanitizer import sanitize
from app.models import KnowledgeArticle, KnowledgeCategory, User, uuid_str
from app.schemas import ArticleIn, ArticleQuery, ArticleRow, CategoryRow


def _dt(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _row(
    a: KnowledgeArticle,
    category_name: str | None,
    author_name: str | None,
    favorited: bool = False,
) -> ArticleRow:
    return ArticleRow(
        id=a.id,
        category_id=a.category_id,
        category_name=category_name,
        title=a.title,
        summary=a.summary,
        content=a.content,
        cover_image=a.cover_image,
        tags=a.tags,
        author_name=author_name,
        read_count=a.read_count,
        status=a.status,
        status_text="已发布" if a.status == 1 else "草稿",
        is_favorited=favorited,
        favorite_count=0,  # 原版恒为 0（收藏功能未实现）
        published_at=_dt(a.published_at),
        created_at=_dt(a.created_at),
        updated_at=_dt(a.updated_at),
    )


def _category_names(db: Session, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = db.scalars(select(KnowledgeCategory).where(KnowledgeCategory.id.in_(ids))).all()
    return {c.id: c.category_name or "" for c in rows}


def _author_names(db: Session, ids: list[int]) -> dict[int, str | None]:
    if not ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(ids))).all()
    return {u.id: u.nickname for u in rows}


# ===========================================================================
# 文章
# ===========================================================================


def page(db: Session, query: ArticleQuery) -> dict[str, Any]:
    conditions = []
    if query.category_id is not None:
        conditions.append(KnowledgeArticle.category_id == query.category_id)
    if query.status is not None:
        conditions.append(KnowledgeArticle.status == query.status)
    if query.keyword and query.keyword.strip():
        conditions.append(KnowledgeArticle.title.like(f"%{query.keyword}%"))

    total = db.scalar(select(func.count()).select_from(KnowledgeArticle).where(*conditions)) or 0

    offset = (query.current_page - 1) * query.size
    records = list(
        db.scalars(
            select(KnowledgeArticle)
            .where(*conditions)
            .order_by(KnowledgeArticle.created_at.desc())
            .offset(offset)
            .limit(query.size)
        ).all()
    )

    cat_ids = list({a.category_id for a in records if a.category_id})
    author_ids = list({a.author_id for a in records if a.author_id})
    cat_map = _category_names(db, cat_ids)
    author_map = _author_names(db, author_ids)

    return {
        "records": [
            _row(a, cat_map.get(a.category_id or 0), author_map.get(a.author_id or 0)) for a in records
        ],
        "total": total,
    }


def detail(db: Session, article_id: str) -> ArticleRow | None:
    """文章详情。**访问即阅读数 +1**（原版行为，别不当回事）。"""
    a = db.get(KnowledgeArticle, article_id)
    if a is None:
        return None

    # 原子自增：读-改-写在并发阅读时会互相覆盖丢计数
    # （用别名 sa_update —— 本模块自己的 update() 函数不能被遮蔽）
    db.execute(
        sa_update(KnowledgeArticle)
        .where(KnowledgeArticle.id == article_id)
        .values(read_count=func.coalesce(KnowledgeArticle.read_count, 0) + 1)
    )
    db.commit()
    db.refresh(a)

    category_name = str(a.category_id) if a.category_id is not None else None
    if a.category_id is not None:
        c = db.get(KnowledgeCategory, a.category_id)
        if c is not None:
            category_name = c.category_name

    author_name = None
    if a.author_id is not None:
        author = db.get(User, a.author_id)
        author_name = author.nickname if author else None

    return _row(a, category_name, author_name)


def create(db: Session, author_id: int, payload: ArticleIn) -> KnowledgeArticle:
    now = datetime.now()
    status = payload.status if payload.status is not None else 1
    a = KnowledgeArticle(
        id=uuid_str(),
        category_id=payload.category_id,
        title=payload.title,
        # 入库前做 HTML 白名单清洗（纵深防御第二道）
        summary=sanitize(payload.summary),
        content=sanitize(payload.content),
        cover_image=payload.cover_image,
        tags=payload.tags,
        author_id=author_id,
        read_count=0,
        status=status,
        published_at=now if status == 1 else None,
        created_at=now,
        updated_at=now,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def update(db: Session, article_id: str, payload: ArticleIn) -> KnowledgeArticle | None:
    a = db.get(KnowledgeArticle, article_id)
    if a is None:
        return None

    a.category_id = payload.category_id
    a.title = payload.title
    a.summary = sanitize(payload.summary)
    a.content = sanitize(payload.content)
    a.cover_image = payload.cover_image
    a.tags = payload.tags
    if payload.status is not None:
        # 从草稿转已发布时补发布时间
        if payload.status == 1 and a.status != 1:
            a.published_at = datetime.now()
        a.status = payload.status
    a.updated_at = datetime.now()
    db.commit()
    db.refresh(a)
    return a


def delete(db: Session, article_id: str) -> bool:
    a = db.get(KnowledgeArticle, article_id)
    if a is None:
        return False
    db.delete(a)
    db.commit()
    return True


def update_status(db: Session, article_id: str, status: int) -> bool:
    a = db.get(KnowledgeArticle, article_id)
    if a is None:
        return False
    if status == 1 and a.status != 1:
        a.published_at = datetime.now()
    a.status = status
    a.updated_at = datetime.now()
    db.commit()
    return True


# ===========================================================================
# 分类
# ===========================================================================


def category_tree(db: Session) -> list[CategoryRow]:
    """分类列表（含每分类文章数，按 sort_order 升序）。"""
    categories = list(
        db.scalars(select(KnowledgeCategory).order_by(KnowledgeCategory.sort_order.asc())).all()
    )
    counts = dict(
        db.execute(
            select(KnowledgeArticle.category_id, func.count())
            .where(KnowledgeArticle.category_id.is_not(None))
            .group_by(KnowledgeArticle.category_id)
        ).all()
    )

    return [
        CategoryRow(
            id=c.id,
            category_name=c.category_name,
            description=c.description,
            sort_order=c.sort_order,
            status=c.status,
            status_text="启用" if c.status == 1 else "禁用",
            article_count=counts.get(c.id, 0),
            created_at=_dt(c.created_at),
            updated_at=_dt(c.updated_at),
        )
        for c in categories
    ]
