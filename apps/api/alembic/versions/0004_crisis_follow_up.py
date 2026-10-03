"""危机工单：新增「采取措施」字段与「跟进记录」表

对应《危机预警与咨询记录-改版方案》第六节。

两处改动放同一个迁移里，因为它们服务同一件事：**让处置从"一次性备注"变成可跟进的过程**。

- `crisis_event.measures`：处置时勾选的结构化措施（逗号分隔编码）
- `crisis_follow_up`：一条工单可以有多条跟进记录

原来的 `handle_note` 是一次性文本，处置完就锁死，记不了「3 天后复查怎么样」。
而危机的处置天然是多轮的：联系 → 观察 → 复查 → 转介 → 关闭。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "crisis_event",
        sa.Column("measures", sa.String(length=200), nullable=True),
    )

    op.create_table(
        "crisis_follow_up",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column("operator_id", sa.BigInteger(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        # ⚠️ 必须显式写 COLLATE —— 只写 charset 会拿到 MySQL 8 的表级默认
        #    utf8mb4_0900_ai_ci，与 0001 转过的 utf8mb4_unicode_ci 不一致，
        #    JOIN crisis_event / user 时会报 "Illegal mix of collations"。
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_crisis_follow_up_event_id", "crisis_follow_up", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_crisis_follow_up_event_id", table_name="crisis_follow_up")
    op.drop_table("crisis_follow_up")
    op.drop_column("crisis_event", "measures")
