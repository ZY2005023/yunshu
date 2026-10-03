"""P2-3 RAG 知识增强：新增知识切片表

对应《系统改造方案》第三期 P2 第 3 项。切片规则见 app/core/retrieval.py。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_chunk",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("article_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        # ⚠️ 必须显式写 COLLATE —— 只写 charset 会拿到 MySQL 8 的表级默认
        #    utf8mb4_0900_ai_ci，与 0001 转过的 utf8mb4_unicode_ci 不一致，
        #    JOIN knowledge_article 时会报 "Illegal mix of collations"。
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_knowledge_chunk_article_id", "knowledge_chunk", ["article_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunk_article_id", table_name="knowledge_chunk")
    op.drop_table("knowledge_chunk")
