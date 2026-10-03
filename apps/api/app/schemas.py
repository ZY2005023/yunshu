"""Pydantic schema —— 全部接口的入参出参。

两条全局约定，改动会直接导致前端出错：

1. **出参是 camelCase，入参也是 camelCase**
   数据库/Python 内部是 snake_case，靠 `alias_generator` 统一转。
   缺了这一步，前端拿到的会是 `user_id` 而不是 `userId`。

2. **时间字段一律序列化成 ISO 字符串**
   Java 版在 Map 里走 `toString()`、在实体里走 Jackson 默认，两者其实不完全一致；
   Python 版统一用 ISO，差异已在契约清单第八章登记。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    field_validator,
)

T = TypeVar("T")


def to_camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(p.title() for p in rest)


class ApiModel(BaseModel):
    """所有对外 schema 的基类：snake_case 内部名 ↔ camelCase 外部名。

    `from_attributes=True` 让 `UserDetail.model_validate(orm_user)` 这种
    从 ORM 对象直接构造的写法可用 —— 这是替代 MapStruct 的关键一步，
    不需要手写任何转换代码。
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat() if v else None,
                       date: lambda v: v.isoformat() if v else None},
        extra="ignore",
    )


class ApiIn(ApiModel):
    """入参基类：允许用字段名或别名两种方式提交，避免前端改造。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="ignore",
    )


class PageOut(ApiModel, Generic[T]):
    """分页容器。注意 key 是 `records` 与 `total`，不是 list/count。"""

    records: list[T] = Field(default_factory=list)
    total: int = 0


# ===========================================================================
# 用户 / 认证
# ===========================================================================


class LoginIn(ApiIn):
    username: str = Field(max_length=100, description="用户名或邮箱")
    # ⚠️ max 必须与 PasswordChangeIn/AdminResetPasswordIn 的 64 一致：
    #    改密允许 64 位而登录只收 50 位的话，设了 51-64 位密码的用户会被
    #    参数校验永远拦在登录之外（HTTP 200 + code 400，看起来像密码错了）。
    password: str = Field(min_length=6, max_length=64)


class RegisterIn(ApiIn):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr = Field(max_length=100)
    nickname: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, pattern=r"^1[3-9]\d{9}$")
    password: str = Field(min_length=6, max_length=64)
    confirm_password: str = Field(min_length=6, max_length=64)
    gender: int | None = None
    user_type: int | None = Field(default=1)
    birthday: date | None = None


class TokenRefreshIn(ApiIn):
    refresh_token: str


class PasswordChangeIn(ApiIn):
    old_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=6, max_length=64)
    confirm_password: str = Field(min_length=6, max_length=64)


class UserDetail(ApiModel):
    id: int
    username: str | None = None
    email: str | None = None
    nickname: str | None = None
    avatar: str | None = None
    phone: str | None = None
    gender: int | None = None
    birthday: date | None = None
    user_type: int | None = None
    status: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # ---- 派生字段（原 MapStruct/@Expression 生成，规则与原版一致）----

    @computed_field
    @property
    def gender_display_name(self) -> str:
        """null → 未知；1 → 男；2 → 女；其他 → 未知"""
        return {1: "男", 2: "女"}.get(self.gender or 0, "未知")

    @computed_field
    @property
    def user_type_display_name(self) -> str:
        return {1: "普通用户", 2: "管理员"}.get(self.user_type or 0, "未知")

    @computed_field
    @property
    def status_display_name(self) -> str:
        return {0: "禁用", 1: "正常"}.get(self.status if self.status is not None else -1, "未知")

    @computed_field
    @property
    def display_name(self) -> str:
        """nickname trim 后非空取 nickname，否则取 username"""
        nick = (self.nickname or "").strip()
        return nick if nick else (self.username or "")


class LoginOut(ApiModel):
    token: str
    refresh_token: str
    role_type: str  # ⚠️ 字符串，不是整数（原版 userInfo.userType.toString()）
    user_info: UserDetail


class ProfileUpdateIn(ApiIn):
    """个人资料更新。**只允许改这几个字段** —— username / email / userType / status
    一律不接受，否则普通用户可自行提权或改状态（原版注册接口就吃过这个亏）。"""

    nickname: str | None = Field(default=None, max_length=50)
    avatar: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, pattern=r"^1[3-9]\d{9}$")
    gender: int | None = Field(default=None, ge=1, le=2)
    birthday: date | None = None


# ---- 管理端：用户管理 ------------------------------------------------------


class AdminUserRow(ApiModel):
    """管理端用户列表行。

    `password` 一律不出现 —— 连哈希都不外传。
    """

    id: int
    username: str | None = None
    email: str | None = None
    nickname: str | None = None
    phone: str | None = None
    user_type: int | None = None
    status: int | None = None
    created_at: datetime | None = None

    @computed_field
    @property
    def user_type_display_name(self) -> str:
        return {1: "普通用户", 2: "管理员"}.get(self.user_type or 0, "未知")

    @computed_field
    @property
    def status_display_name(self) -> str:
        return {0: "禁用", 1: "正常"}.get(self.status if self.status is not None else -1, "未知")


class UserStatusIn(ApiIn):
    """启用 / 禁用。0 = 禁用，1 = 正常（与 `user.status` 及 `is_active` 的约定一致）。"""

    status: int = Field(ge=0, le=1)


class AdminResetPasswordIn(ApiIn):
    """管理员重置他⼈密码。不需要原密码 —— 这正是「忘记密码」缺的那个出口。"""

    new_password: str = Field(min_length=6, max_length=64)


# ---- 管理端：API 管理（AI 服务配置）----------------------------------------


class AiConfigUpdateIn(ApiIn):
    """部分更新语义：没传 / 传空的字段保持原值。

    api_key 空 = 不修改（页面上是「留空则保持现有 Key」）——
    这样管理员只想换个模型名时不必重新粘贴密钥。
    """

    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=100)
    api_key: str | None = Field(default=None, max_length=200)


class AiConfigOut(ApiModel):
    """当前生效配置。**apiKey 只给掩码**（尾 4 位），原文永远不出接口。"""

    base_url: str
    model: str
    api_key_masked: str
    api_key_set: bool
    configured: bool
    sources: dict[str, str] = Field(default_factory=dict)


class AiConfigTestOut(ApiModel):
    ok: bool
    latency_ms: int
    model: str | None = None
    reply: str | None = None
    error: str | None = None


# ===========================================================================
# 情绪日记
# ===========================================================================


class DiaryIn(ApiIn):
    diary_date: date
    mood_score: int = Field(ge=1, le=10)
    dominant_emotion: str | None = None
    emotion_triggers: str | None = None
    diary_content: str | None = None
    sleep_quality: int | None = Field(default=None, ge=1, le=5)
    stress_level: int | None = Field(default=None, ge=1, le=5)


class DiaryOut(ApiModel):
    id: int
    user_id: int | None = None
    diary_date: date | None = None
    mood_score: int | None = None
    dominant_emotion: str | None = None
    emotion_triggers: str | None = None
    diary_content: str | None = None
    sleep_quality: int | None = None
    stress_level: int | None = None
    ai_emotion_analysis: Any | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # 2026-10-03 新增（加字段不破坏既有消费方）：**规则层**危机检测的命中等级
    # （0=未命中，1~3 同 core/crisis.py）。对话有 SSE crisis 卡片、量表有红色
    # 求助 alert，唯独日记此前没有任何用户侧危机反馈 —— 用户写出高危内容，
    # 后端记了工单、老师会收到通知，当事人自己却什么都看不到。
    # 前端凭这个字段展示与另外两个入口一致的求助卡，不依赖 AI 是否配置。
    crisis_level: int = 0


class DiaryQuery(ApiIn):
    current_page: int = Field(default=1, ge=1)
    size: int = Field(default=10, ge=1, le=100)
    keyword: str | None = None


class DiaryRow(ApiModel):
    """/my 与管理端列表的行结构（动态 Map，字段名必须逐个对齐）。"""
    id: int
    diary_date: str | None = None
    mood_score: int | None = None
    dominant_emotion: str | None = None
    emotion_triggers: str | None = None
    diary_content: str | None = None
    sleep_quality: int | None = None
    stress_level: int | None = None
    created_at: str | None = None
    ai_emotion_analysis: Any | None = None
    # 管理端专有
    user_id: int | None = None
    username: str | None = None
    nickname: str | None = None
    diary_content_preview: str | None = None
    updated_at: str | None = None


# ===========================================================================
# 知识库
# ===========================================================================


class ArticleIn(ApiIn):
    category_id: int
    title: str = Field(max_length=200)
    summary: str | None = None
    content: str
    cover_image: str | None = None
    tags: str | None = None
    status: Literal[0, 1] | None = Field(default=1)


class ArticleStatusIn(ApiIn):
    status: Literal[0, 1]


class ArticleRow(ApiModel):
    id: str  # UUID 字符串
    category_id: int | None = None
    category_name: str | None = None
    title: str | None = None
    summary: str | None = None
    content: str | None = None
    cover_image: str | None = None
    tags: str | None = None
    author_name: str | None = None
    read_count: int | None = None
    status: int | None = None
    status_text: str | None = None
    is_favorited: bool = False
    favorite_count: int = 0
    published_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CategoryRow(ApiModel):
    id: int
    category_name: str | None = None
    description: str | None = None
    sort_order: int | None = None
    status: int | None = None
    status_text: str | None = None  # 1 → 启用，其余 → 禁用
    article_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class ArticleQuery(ApiIn):
    current_page: int = Field(default=1, ge=1)
    size: int = Field(default=10, ge=1, le=100)
    category_id: int | None = None
    keyword: str | None = None
    status: int | None = None


class DocImportOut(ApiModel):
    """文档导入解析结果 —— 预填到编辑器，不直接入库（见 services/doc_import.py）。"""

    title: str
    content: str
    char_count: int
    paragraph_count: int
    warnings: list[str] = Field(default_factory=list)


# ===========================================================================
# 文件
# ===========================================================================


class FileOut(ApiModel):
    file_id: int
    file_path: str
    url: str
    original_name: str | None = None
    file_type: str | None = None
    file_size: int | None = None


# ===========================================================================
# 心理咨询
# ===========================================================================


class SessionStartIn(ApiIn):
    session_title: Annotated[str, Field(max_length=200)] | None = None
    initial_message: str = Field(min_length=1, max_length=2000)


class StreamIn(ApiIn):
    session_id: str
    user_message: str = Field(min_length=1, max_length=2000)


class SessionStartOut(ApiModel):
    """原 Java record StreamChatSession。注意时间是**毫秒时间戳**。"""

    session_id: str
    user_hash: int | None = None
    initial_message: str | None = None
    start_time: int | None = None
    expiry_time: int | None = None
    message_count: int | None = None
    status: str | None = None


class SessionRow(ApiModel):
    id: int
    user_id: int | None = None
    username: str | None = None
    nickname: str | None = None
    session_title: str | None = None
    started_at: str | None = None
    last_emotion_analysis: Any | None = None
    last_message_content: str | None = None
    message_count: int = 0
    duration_minutes: int = 0
    # ---- 风险标记（管理端整改新增）----
    # 咨询记录默认按时间倒序时，"有风险的会话"会被淹没在大量日常闲聊里。
    # 这两个字段让前端既能标红，也能按"要不要关心"排序。
    risk_level: int | None = None  # 该会话触发过的最高危机等级，无则 None
    crisis_count: int = 0  # 该会话产生的危机事件数


class MessageRow(ApiModel):
    id: int
    session_id: int | None = None
    sender_type: int | None = None
    sender_type_desc: str | None = None
    message_type: int | None = None
    content: str | None = None
    emotion_tag: str | None = None
    ai_model: str | None = None
    created_at: str | None = None


class MessagesOut(ApiModel):
    session_id: str
    messages: list[MessageRow] = Field(default_factory=list)


class EmotionOut(ApiModel):
    session_id: str
    emotion_analysis: Any | None = None


class CrisisCard(ApiModel):
    """SSE 的 crisis 事件载荷。"""

    level: int
    title: str | None = None
    subtitle: str | None = None
    helplines: list[str] = Field(default_factory=list)
    disclaimer: str | None = None


# ===========================================================================
# 危机预警
# ===========================================================================


class CrisisRow(ApiModel):
    id: int
    user_id: int | None = None
    session_id: int | None = None
    diary_id: int | None = None
    source: str | None = None
    level: int | None = None
    trigger_type: str | None = None
    matched_terms: str | None = None
    content_snippet: str | None = None
    status: str | None = None
    handler_id: int | None = None
    handle_note: str | None = None
    handled_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # ---- 整改新增 ----
    # 用户名/昵称：原来列表里只有「用户ID: 52」这种数字，管理员没法知道是谁。
    # 数据就在 user 表里，取得到却没取 —— 这是工单"不可处置"的第一环。
    username: str | None = None
    nickname: str | None = None
    # 处置人姓名：多人值班时不知道谁已经联系过 → 会重复联系学生。
    handler_name: str | None = None
    # 处置时勾选的结构化措施编码（逗号分隔存库，这里拆解成数组）
    measures: list[str] = Field(default_factory=list)
    follow_up_count: int = 0


class MeasureOption(ApiModel):
    """处置措施选项。

    为什么不只留一个备注框：自由文本无法统计，也无法校验"该做的做了没有"。
    结构化之后才能回答「哪些工单根本没采取实质措施」。
    """

    code: str
    label: str
    # 该措施适用于哪些等级（空 = 所有等级都可选）
    levels: list[int] = Field(default_factory=list)


class CrisisHandleIn(ApiIn):
    """status 为空时默认 RESOLVED，这是原版行为。"""

    status: Literal["RESOLVED", "IGNORED", "HANDLING"] | None = None
    handle_note: str | None = None
    measures: list[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def _blank_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("measures", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> Any:
        return v or []


class CrisisFollowUpIn(ApiIn):
    """追加一条跟进记录。

    危机处置天然是多轮的：联系 → 观察 → 复查 → 转介 → 关闭。
    原来只有一个一次性 handle_note，记不了「3 天后复查怎么样」。
    """

    content: str = Field(min_length=1, max_length=2000)


class CrisisFollowUpOut(ApiModel):
    id: int
    event_id: int | None = None
    operator_id: int | None = None
    operator_name: str | None = None
    content: str | None = None
    created_at: str | None = None


class CrisisUserBrief(ApiModel):
    """工单上下文里的用户画像。"""

    id: int | None = None
    username: str | None = None
    nickname: str | None = None
    gender: int | None = None
    birthday: str | None = None
    status: int | None = None
    created_at: str | None = None
    # 汇总指标，用来判断"这是不是个老问题"
    diary_count: int = 0
    session_count: int = 0
    crisis_count: int = 0


class CrisisHistoryItem(ApiModel):
    """该用户的**历史**工单（不含本次）—— 判断是不是复发。"""

    id: int
    level: int | None = None
    status: str | None = None
    source: str | None = None
    content_snippet: str | None = None
    handle_note: str | None = None
    created_at: str | None = None


class CrisisScaleItem(ApiModel):
    id: int
    scale_code: str | None = None
    scale_name: str | None = None
    total_score: int | None = None
    level: str | None = None
    # ⚠️ 自伤项单独看：PHQ-9 第 9 题有分就说明有风险，**与总分高低无关**
    self_harm_score: int | None = None
    self_harm_risk: int | None = None
    created_at: str | None = None


class CrisisDiaryItem(ApiModel):
    id: int
    diary_date: str | None = None
    mood_score: int | None = None
    dominant_emotion: str | None = None
    content: str | None = None
    created_at: str | None = None


class CrisisDiaryTrend(ApiModel):
    """近期日记趋势。

    ⚠️ 这里必须定义成 schema 而不是裸 `dict[str, Any]`：
    `alias_generator` 只作用于**模型字段**，dict 的键不会被转成 camelCase，
    于是 JSON 里会出现 `low_days` 而前端按 `lowDays` 读 → 静默拿到 undefined。
    这正是本项目最常见的一类 bug（见 MEMORY.md「静默失效」）。
    """

    count: int = 0
    avg_mood: float | None = None
    low_days: int = 0  # 心情分 ≤3 的天数
    min_mood: int | None = None


class CrisisSourceMessage(ApiModel):
    """触发本次工单的原始对话消息（完整，不截断）。"""

    id: int
    sender_type: int | None = None
    sender_type_desc: str | None = None
    content: str | None = None
    created_at: str | None = None


class CrisisSourceOut(ApiModel):
    """触发本次工单的原始记录 —— 工单只有 120 字片段时无法判断真假。"""

    source: str | None = None  # CHAT / DIARY
    session_id: int | None = None
    diary_id: int | None = None
    session_title: str | None = None
    # 会话上下文：触发点**前后**各若干条，而不只是触发那一条
    messages: list[CrisisSourceMessage] = Field(default_factory=list)
    trigger_message_id: int | None = None
    diary: CrisisDiaryItem | None = None


class CrisisContextOut(ApiModel):
    """处置工作台所需的一切 —— 一屏看全决策依据。"""

    event: CrisisRow
    user: CrisisUserBrief | None = None
    history: list[CrisisHistoryItem] = Field(default_factory=list)
    scales: list[CrisisScaleItem] = Field(default_factory=list)
    diaries: list[CrisisDiaryItem] = Field(default_factory=list)
    diary_trend: CrisisDiaryTrend = Field(default_factory=CrisisDiaryTrend)
    source: CrisisSourceOut | None = None
    follow_ups: list[CrisisFollowUpOut] = Field(default_factory=list)
    # 处置清单（按等级给，固化 SOP，新手也知道该做什么）
    checklist: list[str] = Field(default_factory=list)
    measure_options: list[MeasureOption] = Field(default_factory=list)


class CrisisResourcesOut(ApiModel):
    title: str | None = None
    subtitle: str | None = None
    helplines: list[str] = Field(default_factory=list)
    disclaimer: str | None = None


# ===========================================================================
# 数据看板
# ===========================================================================


class SystemOverview(ApiModel):
    total_users: int = 0
    active_users: int = 0
    total_diaries: int = 0
    total_sessions: int = 0
    avg_mood_score: float = 0.0
    today_new_users: int = 0
    today_new_diaries: int = 0
    today_new_sessions: int = 0


class HeatPoint(ApiModel):
    x: int = 0
    y: int = 0
    value: int = 0
    avg_mood_score: float = 0.0
    dominant_emotion: str | None = None


class EmotionHeatmap(ApiModel):
    """⚠️ `gridData` 是**二维数组**：7 行（周一~周日）× 10 列（评分 1~10）。

    行下标 y = 创建日的星期（0 = 周一），列下标 x = 评分 - 1。
    """

    grid_data: list[list[HeatPoint]] = Field(default_factory=list)


class ConsultationStats(ApiModel):
    total_sessions: int = 0
    total_messages: int = 0
    avg_messages_per_session: float = 0.0


class DailyTrendRow(ApiModel):
    date: str
    session_count: int = 0
    user_count: int = 0


class TrendRow(ApiModel):
    date: str
    avg_mood_score: float = 0.0
    record_count: int = 0


class ActivityRow(ApiModel):
    date: str
    new_users: int = 0
    diary_users: int = 0
    consultation_users: int = 0
    active_users: int = 0


class AnalyticsOverview(ApiModel):
    system_overview: SystemOverview
    emotion_heatmap: EmotionHeatmap
    consultation_stats: ConsultationStats
    daily_trend: list[DailyTrendRow] = Field(default_factory=list)
    trend_data: list[TrendRow] = Field(default_factory=list)
    activity_data: list[ActivityRow] = Field(default_factory=list)


# ===========================================================================
# 标准化量表（P2-6）
# ===========================================================================


class ScaleQuestionsOut(ApiModel):
    """量表题目。前端据此渲染表单 —— 题目文案由后端统一下发，避免两端各写一份。"""

    code: str
    name: str
    questions: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    disclaimer: str = ""


class ScaleSubmitIn(ApiIn):
    scale_code: str
    answers: list[int]


class ScaleResultOut(ApiModel):
    code: str
    name: str
    total: int
    level: str
    answers: list[int] = Field(default_factory=list)
    max_total: int = 0
    self_harm_risk: bool = False
    self_harm_score: int = 0
    disclaimer: str = ""
    created_at: str | None = None


class ScaleHistoryRow(ApiModel):
    id: int
    scale_code: str | None = None
    scale_name: str | None = None
    total_score: int | None = None
    level: str | None = None
    self_harm_risk: bool = False
    created_at: str | None = None


class ScaleTrendPoint(ApiModel):
    date: str
    scale_code: str | None = None
    total_score: int | None = None
    level: str | None = None


class ScaleAdminRow(ApiModel):
    """管理端的量表记录行（附用户名，便于跟进）。"""

    id: int
    user_id: int | None = None
    username: str | None = None
    nickname: str | None = None
    scale_code: str | None = None
    scale_name: str | None = None
    total_score: int | None = None
    level: str | None = None
    self_harm_risk: bool = False
    created_at: str | None = None


__all__ = [
    "ActivityRow",
    "AnalyticsOverview",
    "ApiModel",
    "ArticleIn",
    "ArticleQuery",
    "ArticleRow",
    "ArticleStatusIn",
    "CategoryRow",
    "ConsultationStats",
    "CrisisCard",
    "CrisisContextOut",
    "CrisisDiaryItem",
    "CrisisDiaryTrend",
    "CrisisFollowUpIn",
    "CrisisFollowUpOut",
    "CrisisHandleIn",
    "CrisisHistoryItem",
    "CrisisResourcesOut",
    "CrisisRow",
    "CrisisScaleItem",
    "CrisisSourceMessage",
    "CrisisSourceOut",
    "CrisisUserBrief",
    "DailyTrendRow",
    "DiaryIn",
    "DiaryOut",
    "DiaryRow",
    "EmotionHeatmap",
    "EmotionOut",
    "FileOut",
    "HeatPoint",
    "LoginIn",
    "LoginOut",
    "MeasureOption",
    "MessageRow",
    "MessagesOut",
    "PageOut",
    "PasswordChangeIn",
    "RegisterIn",
    "SessionRow",
    "SessionStartIn",
    "SessionStartOut",
    "StreamIn",
    "SystemOverview",
    "TokenRefreshIn",
    "TrendRow",
    "UserDetail",
    "to_camel",
]
