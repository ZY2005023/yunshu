"""P2-6 标准量表：新增量表记录表

对应《系统改造方案》第三期 P2 第 6 项「标准量表与报告」的持久化部分。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "scale_record",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("scale_code", sa.String(length=20), nullable=True),
        sa.Column("scale_name", sa.String(length=50), nullable=True),
        sa.Column("answers", sa.String(length=200), nullable=True),
        sa.Column("total_score", sa.SmallInteger(), nullable=True),
        sa.Column("level", sa.String(length=20), nullable=True),
        sa.Column("self_harm_score", sa.SmallInteger(), nullable=True),
        sa.Column("self_harm_risk", sa.SmallInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        # ⚠️ 必须显式写 COLLATE。只指定 charset 的话，MySQL 8 会用表级默认
        #    utf8mb4_0900_ai_ci，而 0001 里其余表被 CONVERT 成了 utf8mb4_unicode_ci ——
        #    两者做 JOIN 会报 "Illegal mix of collations"。
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_scale_record_user_id", "scale_record", ["user_id"])
    op.create_index("ix_scale_record_scale_code", "scale_record", ["scale_code"])


def downgrade() -> None:
    op.drop_index("ix_scale_record_scale_code", table_name="scale_record")
    op.drop_index("ix_scale_record_user_id", table_name="scale_record")
    op.drop_table("scale_record")
