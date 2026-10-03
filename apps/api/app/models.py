"""ORM 模型 —— 8 张表，字段与 Java entity 一一对应。

命名约定：数据库列名是 snake_case，JSON 出参必须是 camelCase，
这个转换统一放在 schemas 的 alias_generator 里，模型层保持 DB 原生。

⚠️ 时间列统一用 `DateTime`，序列化时由 schema 转成字符串，
避免不同 psycopg/pymysql 驱动返回不同精度。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


# 主键类型：MySQL 下是 BIGINT AUTO_INCREMENT；
# 测试跑在 SQLite 上，而 SQLite 只对 INTEGER PRIMARY KEY 自增，
# 所以要 with_variant 降级，否则 create_all 出来的表插不进数据。
_PK_TYPE = BigInteger().with_variant(Integer, "sqlite")


# ===========================================================================
# 用户
# ===========================================================================


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    username: Mapped[str | None] = mapped_column(String(50), unique=True)
    email: Mapped[str | None] = mapped_column(String(100), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    password: Mapped[str | None] = mapped_column(String(100))
    nickname: Mapped[str | None] = mapped_column(String(50))
    avatar: Mapped[str | None] = mapped_column(String(255))
    gender: Mapped[int | None] = mapped_column(SmallInteger)
    birthday: Mapped[date | None] = mapped_column(Date)
    user_type: Mapped[int | None] = mapped_column("user_type", SmallInteger, default=1)
    status: Mapped[int | None] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    @property
    def is_active(self) -> bool:
        """对应 Java entity 的 `isActive()`：status == 1。"""
        return self.status == 1


# ===========================================================================
# 情绪日记
# ===========================================================================


class EmotionDiary(Base):
    __tablename__ = "emotion_diary"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    diary_date: Mapped[date | None] = mapped_column(Date)
    mood_score: Mapped[int | None] = mapped_column(SmallInteger)
    dominant_emotion: Mapped[str | None] = mapped_column(String(50))
    emotion_triggers: Mapped[str | None] = mapped_column(Text)
    diary_content: Mapped[str | None] = mapped_column(Text)
    sleep_quality: Mapped[int | None] = mapped_column(SmallInteger)
    stress_level: Mapped[int | None] = mapped_column(SmallInteger)
    ai_emotion_analysis: Mapped[str | None] = mapped_column(Text)
    ai_analysis_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# ===========================================================================
# 知识库
# ===========================================================================


class KnowledgeCategory(Base):
    __tablename__ = "knowledge_category"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, default=0)
    category_name: Mapped[str | None] = mapped_column(String(100))
    category_code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(500))
    sort_order: Mapped[int | None] = mapped_column(Integer, default=0)
    status: Mapped[int | None] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class KnowledgeArticle(Base):
    """文章主键是 **UUID 字符串**，不是自增整数 —— 迁移时别改成 int。"""

    __tablename__ = "knowledge_article"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    category_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str | None] = mapped_column(Text)
    cover_image: Mapped[str | None] = mapped_column(String(255))
    tags: Mapped[str | None] = mapped_column(String(255))
    author_id: Mapped[int | None] = mapped_column(BigInteger)
    read_count: Mapped[int | None] = mapped_column(Integer, default=0)
    status: Mapped[int | None] = mapped_column(SmallInteger, default=1)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# ===========================================================================
# 心理咨询
# ===========================================================================


class ConsultationSession(Base):
    __tablename__ = "consultation_session"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    session_title: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    last_emotion_analysis: Mapped[str | None] = mapped_column(Text)
    last_emotion_updated_at: Mapped[datetime | None] = mapped_column(DateTime)


class ConsultationMessage(Base):
    __tablename__ = "consultation_message"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("consultation_session.id"), index=True
    )
    sender_type: Mapped[int | None] = mapped_column(SmallInteger)  # 1=用户 2=AI
    message_type: Mapped[int | None] = mapped_column(SmallInteger, default=1)
    content: Mapped[str | None] = mapped_column(Text)
    emotion_tag: Mapped[str | None] = mapped_column(String(50))
    ai_model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    def sender_type_desc(self) -> str:
        return {1: "用户", 2: "AI助手"}.get(self.sender_type or 0, "未知")


# ===========================================================================
# 危机事件
# ===========================================================================


class CrisisEvent(Base):
    __tablename__ = "crisis_event"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    session_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    diary_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    source: Mapped[str | None] = mapped_column(String(20))  # CHAT / DIARY
    level: Mapped[int | None] = mapped_column(SmallInteger)  # 1=关注 2=预警 3=危机
    trigger_type: Mapped[str | None] = mapped_column(String(20))  # KEYWORD / LLM
    matched_terms: Mapped[str | None] = mapped_column(String(500))
    content_snippet: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(
        String(20), default="PENDING"
    )  # PENDING/HANDLING/RESOLVED/IGNORED
    handler_id: Mapped[int | None] = mapped_column(BigInteger)
    handle_note: Mapped[str | None] = mapped_column(Text)
    # 处置时勾选的「采取措施」，逗号分隔的编码（见 services/crisis.py 的 MEASURES）。
    # 拆成结构化字段而不是塞进 handle_note，是为了以后能统计
    # 「哪类措施最常用 / 哪些工单根本没采取实质措施」。
    measures: Mapped[str | None] = mapped_column(String(200))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CrisisFollowUp(Base):
    """工单的跟进记录 —— 一条工单可以有多条。

    为什么必须单独建表：原来的 `handle_note` 是一次性文本，处置完就锁死，
    **记不了"3 天后复查怎么样"**。而危机的处置天然是多轮的：
    联系 → 观察 → 复查 → 转介 → 关闭。只有一条备注等于没有跟进。
    """

    __tablename__ = "crisis_follow_up"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    operator_id: Mapped[int | None] = mapped_column(BigInteger)
    content: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


# ===========================================================================
# 文件
# ===========================================================================


class SysFileInfo(Base):
    __tablename__ = "sys_file_info"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    original_name: Mapped[str | None] = mapped_column(String(255))
    file_path: Mapped[str | None] = mapped_column(String(500))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_type: Mapped[str | None] = mapped_column(String(20))
    business_type: Mapped[str | None] = mapped_column(String(50))
    business_id: Mapped[str | None] = mapped_column(String(64))
    business_field: Mapped[str | None] = mapped_column(String(50))
    upload_user_id: Mapped[int | None] = mapped_column(BigInteger)
    is_temp: Mapped[int | None] = mapped_column(SmallInteger, default=0)
    status: Mapped[int | None] = mapped_column(SmallInteger, default=1)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    expire_time: Mapped[datetime | None] = mapped_column(DateTime)
    # ⚠️ 这张表**没有** created_at / updated_at，只有 create_time。
    #    别照着其他表的惯例补 —— 真库里没有这两列，查询会直接报
    #    "Unknown column 'sys_file_info.created_at' in 'field list'"。


# ===========================================================================
# 标准化量表记录（P2）
# ===========================================================================


class ScaleRecord(Base):
    """PHQ-9 / GAD-7 答题记录。

    存答案而不只存总分 —— 将来做趋势分析或回溯"到底是哪几题变严重"时，
    只有总分是不够的。
    """

    __tablename__ = "scale_record"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    scale_code: Mapped[str | None] = mapped_column(String(20), index=True)
    scale_name: Mapped[str | None] = mapped_column(String(50))
    answers: Mapped[str | None] = mapped_column(String(200))  # JSON 数组
    total_score: Mapped[int | None] = mapped_column(SmallInteger)
    level: Mapped[str | None] = mapped_column(String(20))
    # 仅 PHQ-9 有意义：第 9 题得分与是否触发自伤预警
    self_harm_score: Mapped[int | None] = mapped_column(SmallInteger, default=0)
    self_harm_risk: Mapped[int | None] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


# ===========================================================================
# 系统配置（运行时可改的键值对，如 AI 服务地址 / 模型 / 密钥）
# ===========================================================================


class SysConfig(Base):
    """通用系统配置表。

    为什么不用 .env：FILE_UPLOAD_DIR 这类部署期参数留在环境变量里，
    但 AI 的 base_url / api_key / model 属于**运营期**参数 —— 换供应商、
    换模型、换密钥都希望页面上改完即生效，而不是改 .env 重启。
    数据库值**优先于**环境变量（见 core/runtime_config.py + config.py），
    没有对应行时回退 .env —— 升级部署不会丢现有配置。
    """

    __tablename__ = "sys_config"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(100), unique=True)
    config_value: Mapped[str | None] = mapped_column(Text)
    remark: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# ===========================================================================
# 知识切片（RAG 检索用）
# ===========================================================================


class KnowledgeChunk(Base):
    """知识文章的切片。

    文章正文切段后落这张表，检索时只扫这里，不必每次去全文匹配 content。
    文章增删改时同步重建（见 services/rag.py）。
    """

    __tablename__ = "knowledge_chunk"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    article_id: Mapped[str | None] = mapped_column(String(36), index=True)
    chunk_index: Mapped[int | None] = mapped_column(Integer, default=0)
    content: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


__all__ = [
    "Base",
    "ConsultationMessage",
    "ConsultationSession",
    "CrisisEvent",
    "EmotionDiary",
    "KnowledgeArticle",
    "KnowledgeCategory",
    "KnowledgeChunk",
    "ScaleRecord",
    "SysFileInfo",
    "User",
    "uuid_str",
]
