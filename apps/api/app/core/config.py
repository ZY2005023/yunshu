"""应用配置。

环境变量名与 Java 版 `application.yml` 完全对齐，默认值也照搬，
这样 `.env` 可以两边共用，不用改一处忘一处。

注意 `AI_API_KEY` 是变量名本身 —— 不是 DEEPSEEK_API_KEY。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

MIN_SECRET_LENGTH = 32

# 已知写过进源码/文档的占位密钥。生产启动时命中即拒绝 —— 它们的长度都够 32，
# 只靠长度校验发现不了，必须显式比对。
PLACEHOLDER_SECRETS = frozenset(
    {
        "dev-placeholder-secret-change-me-in-production-0123456789",
        "change-me",
        "secret",
        "your-secret-key",
    }
)

# ⚠️ Java 版靠 Spring 的 `spring.config.import` 自动读 backend/.env，
#    Python 侧没有这个机制 —— 不显式加载的话，改了 .env 也**完全不生效**。
#    这里按 apps/api/.env 定位，与工作目录无关（alembic 也要能读到）。
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_FILE, override=False)


def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class JwtSettings:
    secret: str
    expiration: int = 1_800_000  # access token：30 分钟
    refresh_expiration: int = 604_800_000  # refresh token：7 天
    header: str = "Authorization"
    token_prefix: str = "Bearer "  # 注意：前缀后面带一个空格


@dataclass(frozen=True)
class FileSettings:
    upload_dir: str = "uploads"
    allowed_exts: str = "jpg,jpeg,png,gif,webp,bmp,pdf,txt,doc,docx,xls,xlsx,mp4,mp3,wav"
    max_size: int = 5_242_880  # 5MB


@dataclass(frozen=True)
class AiSettings:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"


@dataclass(frozen=True)
class CrisisSettings:
    notify_contact: str = "学校心理健康教育中心"
    force_helpline_card: bool = True
    # 危机工单的主动触达。为空则只写日志（不静默丢事件，但也不会有人被通知）。
    # 兼容企业微信 / 钉钉 / 飞书群机器人的 webhook 格式。
    webhook_url: str = ""


class Settings:
    """懒加载式配置容器。每次读取都走 os.getenv，方便测试时用 monkeypatch 改环境变量。"""

    # ---- 数据库（Java 侧是 jdbc url，Python 侧用 SQLAlchemy URL）----
    DB_URL: str = _env_str(
        "DB_URL", "jdbc:mysql://localhost:3306/mental_health_assistant?useSSL=false&serverTimezone=UTC"
    )
    DB_USERNAME: str = _env_str("DB_USERNAME", "root")
    DB_PASSWORD: str = _env_str("DB_PASSWORD", "")
    DB_POOL_SIZE: int = _env_int("DB_POOL_SIZE", 10)

    SERVER_PORT: int = _env_int("SERVER_PORT", 1236)
    PAGE_MAX_LIMIT: int = _env_int("PAGE_MAX_LIMIT", 100)

    CRISIS_FORCE_CARD: bool = _env_str("CRISIS_FORCE_CARD", "true").lower() != "false"

    @property
    def jwt(self) -> JwtSettings:
        return JwtSettings(
            secret=_env_str("JWT_SECRET", "dev-placeholder-secret-change-me-in-production-0123456789"),
            expiration=_env_int("JWT_EXPIRATION", 1_800_000),
            refresh_expiration=_env_int("JWT_REFRESH_EXPIRATION", 604_800_000),
            header=_env_str("JWT_HEADER", "Authorization"),
            token_prefix=_env_str("JWT_TOKEN_PREFIX", "Bearer "),
        )

    @property
    def file(self) -> FileSettings:
        return FileSettings(
            upload_dir=_env_str("FILE_UPLOAD_DIR", "uploads"),
            allowed_exts=_env_str(
                "FILE_ALLOWED_EXTS",
                "jpg,jpeg,png,gif,webp,bmp,pdf,txt,doc,docx,xls,xlsx,mp4,mp3,wav",
            ),
            max_size=_env_int("FILE_MAX_SIZE", 5_242_880),
        )

    @property
    def ai(self) -> AiSettings:
        # 数据库里的运营期配置（管理端「API 管理」页可改）优先于环境变量，
        # 没有覆盖时回退 .env —— 见 core/runtime_config.py 的说明。
        # 刻意用 property 而非缓存：保存后**即时生效**，不需要重启。
        from app.core import runtime_config

        return AiSettings(
            api_key=runtime_config.get("ai.api_key", _env_str("AI_API_KEY", "")) or "",
            base_url=runtime_config.get("ai.base_url", _env_str("AI_BASE_URL", "https://api.deepseek.com"))
            or "https://api.deepseek.com",
            model=runtime_config.get("ai.model", _env_str("AI_MODEL", "deepseek-chat")) or "deepseek-chat",
        )

    @property
    def crisis(self) -> CrisisSettings:
        return CrisisSettings(
            notify_contact=_env_str("CRISIS_CONTACT", "学校心理健康教育中心"),
            force_helpline_card=self.CRISIS_FORCE_CARD,
            webhook_url=_env_str("CRISIS_WEBHOOK_URL", ""),
        )

    @property
    def uploads_absolute_path(self) -> str:
        """`/files/**` 静态目录挂载到哪（对齐 Java 版 WebConfig 的行为）。"""
        from os.path import abspath, join

        return join(abspath(self.file.upload_dir), "")

    # ---- 部署相关（用 property 而非类属性：这两个要能被运行时改动/测试覆写）----

    @property
    def app_env(self) -> str:
        """`development`（默认）或 `production`。只有生产模式才做启动自检。"""
        return _env_str("APP_ENV", "development").strip().lower()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins(self) -> list[str]:
        """允许跨域的源，逗号分隔。

        **空列表 = 不启用 CORS**。前后端同源部署（前端由后端托管静态资源）
        本来就不需要 CORS，留空是最安全的选择。
        只有前后端拆到不同域名时才配，且必须写具体域名 —— 不要写 `*`。
        """
        raw = _env_str("CORS_ORIGINS", "")
        return [item.strip() for item in raw.split(",") if item.strip()]

    def startup_problems(self) -> list[str]:
        """生产环境启动自检，返回问题清单（空列表 = 通过）。

        为什么要有这个：JWT 密钥的默认值写在源码里，长度 54 位能轻松通过
        「长度 ≥ 32」的校验 —— 于是**密钥泄露这件事不会报任何错**。
        同理 CORS 通配 + 凭据也是"能跑但危险"。这类问题只能靠显式拦。
        """
        if not self.is_production:
            return []

        problems: list[str] = []
        secret = self.jwt.secret
        if secret in PLACEHOLDER_SECRETS or secret.startswith("dev-placeholder"):
            problems.append(
                "JWT_SECRET 仍是源码里的占位值 —— 任何人都能伪造任意用户（含管理员）的令牌。"
                "请用 `python -c \"import secrets;print(secrets.token_urlsafe(48))\"` 生成后写入 .env"
            )
        elif len(secret) < MIN_SECRET_LENGTH:
            problems.append(f"JWT_SECRET 长度不足 {MIN_SECRET_LENGTH} 位")

        if "*" in self.cors_origins:
            problems.append(
                "CORS_ORIGINS 含通配符 * —— 与 allow_credentials=True 组合时，"
                "任意站点都能带凭据读取本站响应。请改成具体域名"
            )

        if not self.crisis.webhook_url:
            problems.append(
                "CRISIS_WEBHOOK_URL 未配置 —— 危机事件只会躺在后台列表里，"
                "不会有任何老师收到通知。这是危机预警能否起作用的关键"
            )

        if not self.ai.api_key:
            problems.append("AI_API_KEY 未配置 —— AI 对话会直接失败")

        return problems


settings = Settings()
