"""数据库备份。

用法：
    python scripts/backup_db.py                 # 备份一次
    python scripts/backup_db.py --list          # 列出现有备份
    python scripts/backup_db.py --keep 30       # 备份后只保留最近 30 份
    python scripts/backup_db.py --dry-run       # 只打印将要执行的命令，不真的跑

为什么单独做这个脚本：
    学生在这里写的是心理状况，数据丢了既没法向家长交代、也没法向监管交代。
    而"有备份脚本"不等于"能恢复" —— 所以脚本每次都会打印**对应的恢复命令**，
    请至少在上线前真实演练一次恢复（恢复到另一个库名，别覆盖生产库）。

密码处理：
    不在命令行里传 -p 密码（会被 ps / 任务管理器看到），改走 MYSQL_PWD 环境变量。
"""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

BACKUP_DIR = ROOT / "backups"


def _load_env() -> tuple[str, str, int, str, str, str]:
    """返回 (host, user, port, dbname, password)。复用后端配置，避免两处写连接信息。"""
    from app.core.config import settings  # noqa: PLC0415

    raw = settings.DB_URL
    if raw.startswith("jdbc:mysql://"):
        raw = "mysql+pymysql://" + raw[len("jdbc:mysql://") :]
    parsed = urlparse(raw)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 3306
    dbname = (parsed.path or "/").lstrip("/") or "mental_health_py"
    return host, settings.DB_USERNAME, port, dbname, settings.DB_PASSWORD


def find_mysqldump() -> str:
    """定位 mysqldump：环境变量 → PATH → Windows 常见安装位置。"""
    env = os.getenv("MYSQLDUMP")
    if env:
        return env

    found = shutil.which("mysqldump")
    if found:
        return found

    if sys.platform == "win32":
        for base in (r"C:\ruanjian\MySQL\server80\bin", r"C:\Program Files\MySQL"):
            exe = Path(base) / "mysqldump.exe"
            if exe.is_file():
                return str(exe)

    raise SystemExit(
        "找不到 mysqldump。请设置环境变量 MYSQLDUMP 指向它，例如：\n"
        "  set MYSQLDUMP=C:\\ruanjian\\MySQL\\server80\\bin\\mysqldump.exe"
    )


def do_backup(keep: int, dry_run: bool) -> Path | None:
    host, user, port, dbname, password = _load_env()
    mysqldump = find_mysqldump()

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"{dbname}_{stamp}.sql.gz"

    cmd = [
        mysqldump,
        f"--host={host}",
        f"--port={port}",
        f"--user={user}",
        "--single-transaction",   # InnoDB 一致性快照，不锁表
        "--routines",
        "--default-character-set=utf8mb4",
        dbname,
    ]

    print(f"源库    : {dbname} @ {host}:{port}")
    print(f"目标    : {target}")
    if dry_run:
        print("（--dry-run，未真正执行）")
        print("命令    : " + " ".join(cmd))
        return None

    env = dict(os.environ)
    env["MYSQL_PWD"] = password  # 不走命令行，避免密码出现在进程列表

    proc = subprocess.run(cmd, capture_output=True, env=env)
    if proc.returncode != 0:
        raise SystemExit(
            "备份失败：\n" + (proc.stderr.decode("utf-8", "replace") or "(无 stderr)")
        )

    with gzip.open(target, "wb") as fh:
        fh.write(proc.stdout)

    size_kb = target.stat().st_size / 1024
    print(f"完成    : {size_kb:.1f} KB")

    # ★ 每次都把恢复命令打出来 —— 备份的价值在于能恢复
    print("\n对应的恢复命令（先恢复到临时库验证，确认无误再动生产库）：")
    if sys.platform == "win32":
        print(f'  gzip -dc "{target}" | mysql -u {user} -p --default-character-set=utf8mb4 {dbname}_restore_test')
    else:
        print(f"  gzip -dc '{target}' | mysql -u {user} -p --default-character-set=utf8mb4 {dbname}_restore_test")

    if keep > 0:
        _prune(keep)

    return target


def _prune(keep: int) -> None:
    files = sorted(BACKUP_DIR.glob("*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for old in files[keep:]:
        old.unlink()
        removed += 1
    if removed:
        print(f"清理    : 删除 {removed} 份旧备份（保留最近 {keep} 份）")


def do_list() -> None:
    if not BACKUP_DIR.is_dir():
        print("还没有任何备份")
        return
    files = sorted(BACKUP_DIR.glob("*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print("还没有任何备份")
        return
    print(f"共 {len(files)} 份：")
    for f in files:
        mt = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {mt}  {f.stat().st_size / 1024:8.1f} KB  {f.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description="数据库备份")
    ap.add_argument("--list", action="store_true", help="列出现有备份")
    ap.add_argument("--keep", type=int, default=30, help="保留最近 N 份，默认 30")
    ap.add_argument("--dry-run", action="store_true", help="只打印命令")
    args = ap.parse_args()

    if args.list:
        do_list()
    else:
        do_backup(args.keep, args.dry_run)


if __name__ == "__main__":
    main()
