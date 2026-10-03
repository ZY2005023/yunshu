"""Alembic 环境。

连接串来自环境变量（DB_URL / DB_USERNAME / DB_PASSWORD），
与运行时共用同一套配置，避免"迁移用的库和跑的库不是一个"。
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 让 `import app` 可用
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import build_sqlalchemy_url  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", build_sqlalchemy_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """生成 SQL 脚本而不连库（--sql 模式）。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
