"""系统配置：新增 sys_config 表（运行时可改的键值对）

第一组使用方是「API 管理」页（AI 服务的 base_url / api_key / model）：
这三项属于**运营期**参数 —— 换供应商、换模型、换密钥都应该在页面上
改完即生效，而不是改 .env 重启。数据库值优先于环境变量，
没有对应行时回退 .env，升级部署不会丢现有配置。

同构于 Java 生态（RuoYi 一系）的 sys_config：键值对 + 备注列，
后续其它运营参数可以继续放这张表，不必每项建一张表。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "sys_config",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("config_key", sa.String(length=100), nullable=False),
        sa.Column("config_value", sa.Text(), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("config_key", name="uk_sys_config_key"),
        # ⚠️ 显式 COLLATE，原因同 0004：与 0001 的 utf8mb4_unicode_ci 保持一致
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade() -> None:
    op.drop_table("sys_config")
