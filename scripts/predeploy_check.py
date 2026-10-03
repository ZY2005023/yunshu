"""上线前自检。

用法：
    python scripts/predeploy_check.py

上线前跑一遍，全绿再部署。检查项分成两级：

    FAIL    阻断 —— 带着它上线会出事（密钥泄露、危机通知不生效、数据对不上）
    WARN    提醒 —— 不是阻断，但要心里有数（没备份、产物过期、没配告警）

为什么需要这个脚本：这类问题**没有一个会报错**。密钥是占位值时服务照常启动、
webhook 为空时危机事件照常入库（只是没人知道）、ORM 与真库缺字段要等到
用户点开那个页面才炸。它们只会被"部署后出事"暴露，不会在构建或测试阶段暴露。

只读：不写库、不改文件。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

FAIL = "FAIL"
WARN = "WARN"
OK = "PASS"

_results: list[tuple[str, str, str]] = []


def record(level: str, item: str, detail: str) -> None:
    _results.append((level, item, detail))


def check_secret() -> None:
    from app.core.config import PLACEHOLDER_SECRETS, settings

    s = settings.jwt.secret
    if s in PLACEHOLDER_SECRETS or s.startswith("dev-placeholder"):
        record(FAIL, "JWT 密钥", "仍是源码里的占位值 —— 任何人都能伪造任意用户令牌")
    elif len(s) < 32:
        record(FAIL, "JWT 密钥", f"长度 {len(s)} < 32")
    else:
        record(OK, "JWT 密钥", f"已配置（{len(s)} 位）")


def check_ai() -> None:
    from app.core.config import settings

    if not settings.ai.api_key:
        record(FAIL, "AI 密钥", "AI_API_KEY 为空 —— 对话接口会直接失败")
    else:
        record(OK, "AI 密钥", "已配置")


def check_webhook() -> None:
    from app.core.config import settings

    if not settings.crisis.webhook_url:
        record(
            FAIL,
            "危机通知",
            "CRISIS_WEBHOOK_URL 为空 —— 危机事件只会躺在后台列表，不会有老师收到通知",
        )
    else:
        record(OK, "危机通知", "已配置 webhook")


def check_cors() -> None:
    from app.core.config import settings

    origins = settings.cors_origins
    if "*" in origins:
        record(FAIL, "CORS", "含通配符 * —— 任意站点可带凭据读取响应")
    elif origins:
        record(OK, "CORS", f"白名单 {len(origins)} 个：{', '.join(origins)}")
    else:
        record(OK, "CORS", "未启用（同源部署，最安全）")


def check_env_mode() -> None:
    from app.core.config import settings

    if settings.is_production:
        record(OK, "运行模式", "APP_ENV=production（启动自检已开启）")
    else:
        record(
            WARN,
            "运行模式",
            "APP_ENV 不是 production —— 启动自检不会执行，配置问题不会被拦下",
        )


def check_db_and_migration() -> None:
    """数据库连通 + Alembic 版本是否与代码 head 一致。"""
    try:
        from app.db import engine
        from sqlalchemy import text
    except Exception as exc:  # noqa: BLE001
        record(FAIL, "数据库", f"导入失败：{exc}")
        return

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
            current = {r[0] for r in rows}
    except Exception as exc:  # noqa: BLE001
        record(FAIL, "数据库", f"连不上或读不到 alembic_version：{exc}")
        return

    record(OK, "数据库", "连接正常")

    if not current:
        record(FAIL, "数据库迁移", "库里没有 alembic_version —— 从未执行过迁移")
        return
    if len(current) > 1:
        record(FAIL, "数据库迁移", f"存在多个版本分支 {sorted(current)} —— 需先合并")
        return

    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(ROOT / "apps" / "api" / "alembic.ini"))
        # ⚠️ 必须改成绝对路径：alembic.ini 里的 script_location 是相对路径 `alembic`，
        #    而本脚本从项目根目录运行（不是 apps/api），不解成绝对就找不到脚本目录 ——
        #    结果是"读不到 head"被当成 WARN 放过，检查项静默失效。
        cfg.set_main_option("script_location", str(ROOT / "apps" / "api" / "alembic"))
        head = ScriptDirectory.from_config(cfg).get_current_head()
    except Exception as exc:  # noqa: BLE001
        record(WARN, "数据库迁移", f"读不到代码 head：{exc}")
        return

    db_ver = next(iter(current))
    if db_ver == head:
        record(OK, "数据库迁移", f"库中 {db_ver} = 代码 head {head}（无漂移）")
    else:
        record(FAIL, "数据库迁移", f"库中 {db_ver} ≠ 代码 head {head} —— 先跑 alembic upgrade head")


def check_orm_alignment() -> None:
    """ORM 字段 vs 真库字段。SQLite 测试发现不了这类问题。"""
    try:
        from app.db import engine
        from app.models import Base
        from sqlalchemy import text
    except Exception as exc:  # noqa: BLE001
        record(FAIL, "ORM 对齐", f"导入失败：{exc}")
        return

    missing: list[str] = []
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            if not conn.dialect.has_table(conn, table.name):
                missing.append(f"{table.name}（整表缺失）")
                continue
            db_cols = {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema=DATABASE() AND table_name=:t"
                    ),
                    {"t": table.name},
                )
            }
            for col in sorted({c.name for c in table.columns} - db_cols):
                missing.append(f"{table.name}.{col}")

    if missing:
        record(FAIL, "ORM 对齐", f"{len(missing)} 处缺失：" + "、".join(missing[:6]))
    else:
        record(OK, "ORM 对齐", "字段完全一致")


def check_frontend_build() -> None:
    dist = ROOT / "apps" / "web" / "dist" / "index.html"
    if not dist.is_file():
        record(FAIL, "前端产物", "没有 dist —— 部署后只有接口、没有页面（先 npm run build）")
        return

    newest_src = max(
        (p.stat().st_mtime for p in (ROOT / "apps" / "web" / "src").rglob("*") if p.is_file()),
        default=0,
    )
    if dist.stat().st_mtime < newest_src:
        record(WARN, "前端产物", "dist 比源码旧 —— 可能漏了最近一次改动，建议重新 build")
    else:
        record(OK, "前端产物", "已构建且新于源码")


def check_backup() -> None:
    import time

    bdir = ROOT / "backups"
    if not bdir.is_dir():
        record(WARN, "备份", "从未备份过 —— 上线前务必先跑 scripts/backup_db.py")
        return
    files = sorted(bdir.glob("*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        record(WARN, "备份", "备份目录为空")
        return
    age_h = (time.time() - files[0].stat().st_mtime) / 3600
    if age_h > 24:
        record(WARN, "备份", f"最近一份备份是 {age_h:.0f} 小时前，建议重新备份")
    else:
        record(OK, "备份", f"最近一份 {age_h:.1f} 小时前，共 {len(files)} 份")


def check_https() -> None:
    conf = ROOT / "deploy" / "nginx.conf"
    if not conf.is_file():
        record(WARN, "HTTPS", "找不到 deploy/nginx.conf")
        return
    text = conf.read_text(encoding="utf-8", errors="replace")
    if "listen 443 ssl" in text and "ssl_certificate " in text:
        record(OK, "HTTPS", "nginx 已配置 443")
    else:
        record(FAIL, "HTTPS", "nginx 未启用 HTTPS —— 心理数据明文传输过不了合规")


def main() -> None:
    for fn in (
        check_secret,
        check_ai,
        check_webhook,
        check_cors,
        check_env_mode,
        check_db_and_migration,
        check_orm_alignment,
        check_frontend_build,
        check_backup,
        check_https,
    ):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            record(WARN, fn.__name__, f"检查项自身出错：{exc}")

    width = max(len(item) for _, item, _ in _results)
    for level, item, detail in _results:
        print(f"[{level}] {item.ljust(width)}  {detail}")

    n_fail = sum(1 for lv, _, _ in _results if lv == FAIL)
    n_warn = sum(1 for lv, _, _ in _results if lv == WARN)
    print()
    print(f"阻断 {n_fail} 项，提醒 {n_warn} 项")

    if n_fail:
        print("\n结论：还不能上线。先把上面 FAIL 的项处理完。")
        sys.exit(1)
    if n_warn:
        print("\n结论：可以上线，但上面 WARN 的项建议尽快处理。")
    else:
        print("\n结论：全部通过，可以上线。")


if __name__ == "__main__":
    main()
