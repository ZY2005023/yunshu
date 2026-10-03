"""初始库结构 —— 对齐 Java 版 Flyway 的 V1 + V2

建 10 张表：
  · 8 张在用表（ORM 定义，来自 app/models.py）
  · crisis_event（V2 新增，已在 ORM 中）
  · ai_analysis_task / user_favorite —— Java 版**没有对应 entity**的历史表

关于后两张表：
  它们在原始库里存在（V1 迁移脚本带过来的），但 Java 代码从不读写，
  属于"功能没做完留下的壳"：
    · ai_analysis_task   AI 分析任务队列（异步分析没落地）
    · user_favorite      文章收藏（所以 isFavorited 恒 false、favoriteCount 恒 0）
  这里仍然建表，是为了保证库结构与现有库一致 —— 不建的话，
  从旧库切过来会缺表，将来若补功能也会踩坑。

种子数据（V1 里的 INSERT）**不进迁移**：那是演示数据不是结构，
且从已有库迁移时数据本来就在。需要新库灌演示数据的跑 database/seed.sql。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

# 两张历史表的 DDL（取自 database/V1__init_schema.sql，保证结构一致）
_LEGACY_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS `ai_analysis_task` (
      `id` bigint NOT NULL AUTO_INCREMENT COMMENT '任务ID',
      `diary_id` bigint NOT NULL COMMENT '日记ID',
      `user_id` bigint NOT NULL COMMENT '用户ID',
      `status` varchar(20) NOT NULL COMMENT '任务状态',
      `task_type` varchar(20) NOT NULL COMMENT '任务类型',
      `priority` int NOT NULL DEFAULT 2 COMMENT '优先级',
      `retry_count` int NOT NULL DEFAULT 0 COMMENT '重试次数',
      `max_retry_count` int NOT NULL DEFAULT 3 COMMENT '最大重试次数',
      `error_message` text NULL COMMENT '错误信息',
      `started_at` datetime NULL DEFAULT NULL,
      `completed_at` datetime NULL DEFAULT NULL,
      `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
      `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (`id`)
    ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS `user_favorite` (
      `id` bigint NOT NULL AUTO_INCREMENT COMMENT '收藏ID',
      `user_id` bigint NOT NULL COMMENT '用户ID',
      `article_id` varchar(36) NOT NULL COMMENT '文章ID',
      `created_at` datetime NULL DEFAULT CURRENT_TIMESTAMP COMMENT '收藏时间',
      PRIMARY KEY (`id`),
      UNIQUE KEY `user_article_unique` (`user_id`, `article_id`)
    ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
    """,
)


def upgrade() -> None:
    from app.models import Base

    bind = op.get_bind()

    # 1) 8 张在用表 + crisis_event：直接用 ORM 元数据建，保证与 models.py 完全一致。
    #    后续要加字段时，改 models 再用 `alembic revision --autogenerate` 即可。
    Base.metadata.create_all(bind)

    # 2) 补齐 MySQL 字符集（create_all 不指定表选项，这里统一转一次）
    for table_name in Base.metadata.tables:
        op.execute(
            sa.text(
                f"ALTER TABLE `{table_name}` "
                "CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )

    # 3) 两张历史表（无 ORM，走原始 DDL）
    for ddl in _LEGACY_DDL:
        op.execute(sa.text(ddl))


def downgrade() -> None:
    from app.models import Base

    bind = op.get_bind()
    op.execute(sa.text("DROP TABLE IF EXISTS `user_favorite`"))
    op.execute(sa.text("DROP TABLE IF EXISTS `ai_analysis_task`"))
    Base.metadata.drop_all(bind)
