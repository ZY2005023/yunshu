"""危机干预业务：检测落库 + 管理端工单。

规则层算法在 `app/core/crisis.py`（纯函数、可单独测），
这里只负责**落库、去重、工单流转**。

⚠️ `HELPLINES` 里的热线号码**上线前必须人工核验**（原版注释也这么写的）。
心理援助热线会调整，正式发布前应由校方心理中心确认号码仍然有效。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.crisis import DEDUP_MINUTES, CrisisSignal, snippet
from app.core.exceptions import BusinessError
from app.models import (
    ConsultationMessage,
    ConsultationSession,
    CrisisEvent,
    CrisisFollowUp,
    EmotionDiary,
    ScaleRecord,
    User,
)

# ===========================================================================
# 固定求助资源 —— 与 AI 回复解耦，不依赖模型是否"愿意"提供
# ===========================================================================

CARD_TITLE = "如果你正在经历难以承受的痛苦，请立刻联系专业帮助"

CARD_SUBTITLE = "你不需要一个人扛着。下面这些渠道是免费且保密的，现在就有人可以陪你说话。"

HELPLINES: list[str] = [
    "全国统一心理援助热线：12356（24 小时）",
    "北京心理危机研究与干预中心：010-82951332（24 小时）",
    "紧急医疗救助：120　｜　报警：110",
    "校内：学校心理健康教育中心（请通过学校官网/辅导员获取当日值班电话）",
]

DISCLAIMER = (
    "免责声明：本系统由 AI 提供内容支持，不能替代专业心理诊疗或医疗诊断，"
    "也无法提供紧急救援。若你或他人正面临生命危险，请立即拨打 120/110。"
)

# 附加在系统提示词后面，规则层兜底之外再让模型保持同样的姿态
CRISIS_PROMPT_CLAUSE = (
    "\n\n【危机场景要求】当用户表达出自伤、自杀或绝望等想法时：\n"
    "1. 首先明确表达关心与陪伴，不做评判；\n"
    "2. 不要用空洞的安慰搪塞，也不要承诺保密到「谁都不告诉」；\n"
    "3. 直接建议并鼓励其立刻联系专业帮助（心理援助热线 12356 / 学校心理中心 / 120、110）；\n"
    "4. 可以询问「你现在安全吗」「身边有没有可以陪伴你的人」，帮助其建立即时支持；\n"
    "5. 严禁提供任何自伤方式的细节或方法。"
)

STATUS_PENDING = "PENDING"
STATUS_HANDLING = "HANDLING"
STATUS_RESOLVED = "RESOLVED"
STATUS_IGNORED = "IGNORED"

# ===========================================================================
# 处置措施 / 处置清单
# ===========================================================================

# 结构化措施。原来只有一个自由文本的 handle_note —— 文本无法统计，
# 也回答不了「哪些工单其实没采取任何实质措施」。
MEASURES: list[dict[str, Any]] = [
    {"code": "READ_CONTEXT", "label": "已阅读完整原始对话/日记", "levels": []},
    {"code": "CONTACTED_STUDENT", "label": "已联系学生本人", "levels": []},
    {"code": "CONTACTED_COUNSELOR", "label": "已通知辅导员", "levels": [2, 3]},
    {"code": "CONTACTED_PARENT", "label": "已通知家长", "levels": [3]},
    {"code": "REFERRED_CENTER", "label": "已转介学校心理中心", "levels": [2, 3]},
    {"code": "EMERGENCY", "label": "已联系 120/110 紧急介入", "levels": [3]},
    {"code": "SCHEDULED_TALK", "label": "已预约面谈", "levels": [1, 2, 3]},
    {"code": "WATCHLIST", "label": "加入关注名单持续观察", "levels": [1, 2]},
    {"code": "FALSE_ALARM", "label": "判定为误报（请填写原因）", "levels": []},
]

MEASURE_CODES: set[str] = {m["code"] for m in MEASURES}

# 按等级的处置清单 —— 固化 SOP。
# 原来页面上是「三个单选 + 一个备注框」，新手拿到工单根本不知道该干什么。
CHECKLIST: dict[int, list[str]] = {
    3: [
        "先跳到原始对话/日记，读完整上下文再判断（不要只看 120 字片段）",
        "翻该用户历史工单：是不是复发？上次怎么处置的？",
        "判断是否为即时危险（有具体计划/手段/时间）",
        "即时危险 → 立即联系 120/110，并同步辅导员与学院",
        "非即时 → 立即联系学生本人确认安全，询问「身边有没有人陪你」",
        "联系辅导员，必要时通知家长",
        "24 小时内完成首次跟进记录",
    ],
    2: [
        "跳到原始记录看完整上下文",
        "翻历史工单判断是否为持续恶化",
        "24 小时内联系学生或约面谈",
        "通知辅导员，评估是否需要转介心理中心",
        "72 小时内复查并追加跟进",
    ],
    1: [
        "跳到原始记录确认是否误报",
        "若判定误报：勾选误报并填写原因（用于调整关键词规则）",
        "若非误报：加入关注名单，暂不惊动学生",
        "结合近期日记趋势观察，1 周内复查",
    ],
}


def measure_options(level: int | None = None) -> list[dict[str, Any]]:
    """可选的处置措施。传 level 时返回该等级适用 + 通用项。"""
    if level is None:
        return [dict(m) for m in MEASURES]
    return [dict(m) for m in MEASURES if not m["levels"] or level in m["levels"]]


def checklist_for(level: int | None) -> list[str]:
    return list(CHECKLIST.get(level or 1, CHECKLIST[1]))


def resources() -> dict[str, Any]:
    """对应 `/api/admin/crisis/resources` 的返回体。

    注意原版这里是 `helplines: List<String>`（纯字符串数组），
    不是对象数组 —— 前端按字符串渲染。
    """
    return {
        "title": CARD_TITLE,
        "subtitle": CARD_SUBTITLE,
        "helplines": list(HELPLINES),
        "disclaimer": DISCLAIMER,
    }


# ===========================================================================
# 落库（带去重）
# ===========================================================================


def record_if_needed(
    db: Session,
    user_id: int | None,
    session_id: int | None,
    diary_id: int | None,
    source: str,
    signal: CrisisSignal | None,
    raw_text: str | None,
) -> bool:
    """写入一条危机事件。窗口内已记过则跳过。

    Returns:
        是否真的新写了一条
    """
    if signal is None or signal.level <= 0 or user_id is None:
        return False
    if _recently_recorded(db, session_id, diary_id, user_id):
        return False

    now = datetime.now()
    event = CrisisEvent(
        user_id=user_id,
        session_id=session_id,
        diary_id=diary_id,
        source=source,
        level=signal.level,
        trigger_type=signal.trigger_type,
        matched_terms=",".join(signal.matched_terms),
        content_snippet=snippet(raw_text),
        status=STATUS_PENDING,
        created_at=now,
        updated_at=now,
    )
    db.add(event)
    db.commit()

    # ★ 主动触达：这是**唯一收口点** —— 规则层（对话/日记）与模型层
    #   （diary._record_llm_risk）都汇到这里，所以只需在这一处接入。
    #   异步发出，不阻塞用户；未配置 webhook 时只记日志。
    from app.services import notifier

    notifier.notify_crisis(event)
    return True


def _recently_recorded(
    db: Session, session_id: int | None, diary_id: int | None, user_id: int
) -> bool:
    """同一来源在 5 分钟窗口内只记一条，避免用户连续刷屏产生大量重复工单。"""
    conditions = []
    if session_id is not None:
        conditions.append(CrisisEvent.session_id == session_id)
    elif diary_id is not None:
        conditions.append(CrisisEvent.diary_id == diary_id)
    else:
        conditions.append(CrisisEvent.user_id == user_id)
    conditions.append(CrisisEvent.created_at >= datetime.now() - timedelta(minutes=DEDUP_MINUTES))

    return (db.scalar(select(func.count()).select_from(CrisisEvent).where(*conditions)) or 0) > 0


# ===========================================================================
# 管理端工单
# ===========================================================================

MAX_PAGE_SIZE = 50  # ⚠️ 危机列表的上限是 50，与全局的 100 不同（原版硬编码）


def page(
    db: Session,
    current_page: int = 1,
    size: int = 10,
    status: str | None = None,
    level: int | None = None,
    keyword: str | None = None,
) -> dict[str, Any]:
    page_no = max(1, current_page)
    page_size = min(max(1, size), MAX_PAGE_SIZE)

    conditions = []
    if status and status.strip():
        conditions.append(CrisisEvent.status == status)
    if level is not None:
        conditions.append(CrisisEvent.level == level)

    kw = (keyword or "").strip()
    if kw:
        # 三路匹配，覆盖三种检索意图：
        #   1. 从咨询记录跳过来按账号/昵称过滤（沿用原行为）
        #   2. 按用户实际说的话找工单（content_snippet）
        #   3. 按命中的关键词找工单（matched_terms）
        # 之前只走第 1 路，对"撑不下去了"等中等风险话术搜不到对应工单
        # （FINDINGS.md #1，自动化框架实测）—— 工单其实落库了，只是
        # 检索接口的语义覆盖不全。补 2 3 两条 OR 子句对齐用户检索心智。
        like = f"%{kw}%"
        conditions.append(
            or_(
                CrisisEvent.user_id.in_(
                    select(User.id).where(
                        or_(User.username.like(like), User.nickname.like(like))
                    )
                ),
                CrisisEvent.content_snippet.like(like),
                CrisisEvent.matched_terms.like(like),
            )
        )

    total = db.scalar(select(func.count()).select_from(CrisisEvent).where(*conditions)) or 0
    records = list(
        db.scalars(
            select(CrisisEvent)
            .where(*conditions)
            # ⚠️ 这里是**有意偏离原版**的：原版（以及本项目的早期版本）按 created_at 倒序，
            #    结果是 1 级误报（例如「推荐几本关于焦虑的书」）和 3 级真警混在同一屏，
            #    要在一堆求书单里翻出「想自杀」。危机列表不做分诊＝没有分诊。
            #    改为等级优先：3 级永远在最上面，同级内再按时间倒序。
            #    （管理端页头本来就写着「按风险等级排序」，之前名不副实。）
            .order_by(CrisisEvent.level.desc(), CrisisEvent.created_at.desc())
            .offset((page_no - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return {"records": records, "total": total}


def pending_count(db: Session) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(CrisisEvent)
            .where(CrisisEvent.status == STATUS_PENDING)
        )
        or 0
    )


def handle(
    db: Session,
    event_id: int,
    handler_id: int,
    status: str | None,
    note: str | None,
    measures: list[str] | None = None,
) -> None:
    """处置工单。status 为空时默认 RESOLVED（原版行为）。"""
    event = db.get(CrisisEvent, event_id)
    if event is None:
        raise BusinessError("危机事件不存在")

    if event.status not in (STATUS_PENDING, STATUS_HANDLING):
        raise BusinessError("该事件已处置，无需重复处理")

    codes = _validated_measures(measures)

    now = datetime.now()
    event.status = status or STATUS_RESOLVED
    event.handler_id = handler_id
    event.handle_note = note
    event.measures = ",".join(codes) if codes else None
    event.handled_at = now
    event.updated_at = now
    db.commit()


def _validated_measures(measures: list[str] | None) -> list[str]:
    """过滤空值并校验编码。

    ⚠️ 这里**必须**报错而不是静默丢弃：如果前端传错编码被悄悄忽略，
    管理员会以为自己勾了「已通知家长」而系统里什么都没记 —— 这正是本项目
    最常见的「静默失效」形态（见 MEMORY.md）。
    """
    codes = [c.strip() for c in (measures or []) if c and c.strip()]
    unknown = [c for c in codes if c not in MEASURE_CODES]
    if unknown:
        raise BusinessError(f"未知的处置措施：{','.join(unknown)}")
    # 去重但保持顺序
    return list(dict.fromkeys(codes))


# ===========================================================================
# 跟进记录 —— 让处置从「一次性备注」变成可跟进的过程
# ===========================================================================


def add_follow_up(db: Session, event_id: int, operator_id: int, content: str) -> None:
    text = (content or "").strip()
    if not text:
        raise BusinessError("跟进内容不能为空")
    event = db.get(CrisisEvent, event_id)
    if event is None:
        raise BusinessError("危机事件不存在")

    row = CrisisFollowUp(
        event_id=event_id,
        operator_id=operator_id,
        content=text,
        created_at=datetime.now(),
    )
    db.add(row)
    # 追加跟进说明工单仍在推进中 —— 已关闭的重新拉回「处理中」，
    # 否则管理员会以为没人再看这条了。
    if event.status in (STATUS_RESOLVED, STATUS_IGNORED):
        event.status = STATUS_HANDLING
        event.updated_at = datetime.now()
    db.commit()


def list_follow_ups(db: Session, event_id: int) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(CrisisFollowUp)
            .where(CrisisFollowUp.event_id == event_id)
            .order_by(CrisisFollowUp.created_at.desc(), CrisisFollowUp.id.desc())
        ).all()
    )
    if not rows:
        return []
    operators = _user_names(db, [r.operator_id for r in rows if r.operator_id])
    return [
        {
            "id": r.id,
            "event_id": r.event_id,
            "operator_id": r.operator_id,
            "operator_name": operators.get(r.operator_id or 0),
            "content": r.content,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def _user_names(db: Session, user_ids: list[int]) -> dict[int, str]:
    """批量取「昵称（账号）」，避免 N+1。"""
    ids = list({i for i in user_ids if i})
    if not ids:
        return {}
    users = db.scalars(select(User).where(User.id.in_(ids))).all()
    result: dict[int, str] = {}
    for u in users:
        result[u.id] = u.nickname or u.username or str(u.id)
    return result


# ===========================================================================
# 列表行富化：把「用户ID: 52」变成能认出的人
# ===========================================================================


def enrich_rows(db: Session, events: list[CrisisEvent]) -> list[CrisisRow]:
    """批量补上用户名/昵称、处置人姓名、措施、跟进数。

    必须批量查 —— 列表一页最多 50 条，逐条查就是 N+1。
    """
    from app.schemas import CrisisRow

    if not events:
        return []

    user_ids = [e.user_id for e in events if e.user_id]
    handler_ids = [e.handler_id for e in events if e.handler_id]
    users = _users_by_ids(db, user_ids + handler_ids)
    names = _user_names(db, handler_ids)

    event_ids = [e.id for e in events]
    follow_counts: dict[int, int] = {}
    if event_ids:
        rows = db.execute(
            select(CrisisFollowUp.event_id, func.count())
            .where(CrisisFollowUp.event_id.in_(event_ids))
            .group_by(CrisisFollowUp.event_id)
        ).all()
        follow_counts = {eid: n for eid, n in rows if eid is not None}

    result: list[CrisisRow] = []
    for e in events:
        u = users.get(e.user_id or 0)
        result.append(
            CrisisRow(
                id=e.id,
                user_id=e.user_id,
                session_id=e.session_id,
                diary_id=e.diary_id,
                source=e.source,
                level=e.level,
                trigger_type=e.trigger_type,
                matched_terms=e.matched_terms,
                content_snippet=e.content_snippet,
                status=e.status,
                handler_id=e.handler_id,
                handle_note=e.handle_note,
                handled_at=e.handled_at.isoformat() if e.handled_at else None,
                created_at=e.created_at.isoformat() if e.created_at else None,
                updated_at=e.updated_at.isoformat() if e.updated_at else None,
                username=u.username if u else None,
                nickname=u.nickname if u else None,
                handler_name=names.get(e.handler_id or 0),
                measures=[c for c in (e.measures or "").split(",") if c],
                follow_up_count=follow_counts.get(e.id, 0),
            )
        )
    return result


def _users_by_ids(db: Session, user_ids: list[int]) -> dict[int, User]:
    ids = list({i for i in user_ids if i})
    if not ids:
        return {}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids))).all()}


# ===========================================================================
# 处置上下文 —— 一屏看全决策依据
# ===========================================================================

CONTEXT_MESSAGE_LIMIT = 200  # 单次会话最多回传多少条
CONTEXT_HISTORY_LIMIT = 10
CONTEXT_SCALE_LIMIT = 5
CONTEXT_DIARY_LIMIT = 10


def context_of(db: Session, event_id: int) -> CrisisContextOut:
    """工单处置所需的全部信息。

    解决的问题：原来管理员拿到工单只有一句 120 字片段 + 一个用户 ID，
    「只能处置、什么信息都不了解」。这里把**决策依据**一次性给全：
    这人是谁 / 是不是复发 / 量表与日记趋势 / 触发时的完整原文。
    """
    from app.schemas import (
        CrisisContextOut,
        CrisisDiaryItem,
        CrisisFollowUpOut,
        CrisisHistoryItem,
        CrisisScaleItem,
        CrisisSourceMessage,
        CrisisSourceOut,
        CrisisUserBrief,
        MeasureOption,
    )

    event = db.get(CrisisEvent, event_id)
    if event is None:
        raise BusinessError("危机事件不存在")

    row = enrich_rows(db, [event])[0]
    user = _users_by_ids(db, [event.user_id]).get(event.user_id or 0)

    brief: CrisisUserBrief | None = None
    history: list[CrisisHistoryItem] = []
    scales: list[CrisisScaleItem] = []
    diaries: list[CrisisDiaryItem] = []
    trend: dict[str, Any] = {}

    if user is not None:
        brief = CrisisUserBrief(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            gender=user.gender,
            birthday=user.birthday.isoformat() if user.birthday else None,
            status=user.status,
            created_at=user.created_at.isoformat() if user.created_at else None,
            diary_count=_count(db, EmotionDiary, EmotionDiary.user_id == user.id),
            session_count=_count(
                db, ConsultationSession, ConsultationSession.user_id == user.id
            ),
            crisis_count=_count(db, CrisisEvent, CrisisEvent.user_id == user.id),
        )
        history = [
            CrisisHistoryItem(
                id=h.id,
                level=h.level,
                status=h.status,
                source=h.source,
                content_snippet=h.content_snippet,
                handle_note=h.handle_note,
                created_at=h.created_at.isoformat() if h.created_at else None,
            )
            for h in db.scalars(
                select(CrisisEvent)
                .where(CrisisEvent.user_id == user.id, CrisisEvent.id != event.id)
                .order_by(CrisisEvent.created_at.desc())
                .limit(CONTEXT_HISTORY_LIMIT)
            ).all()
        ]
        scales = [
            CrisisScaleItem(
                id=s.id,
                scale_code=s.scale_code,
                scale_name=s.scale_name,
                total_score=s.total_score,
                level=s.level,
                self_harm_score=s.self_harm_score,
                self_harm_risk=s.self_harm_risk,
                created_at=s.created_at.isoformat() if s.created_at else None,
            )
            for s in db.scalars(
                select(ScaleRecord)
                .where(ScaleRecord.user_id == user.id)
                .order_by(ScaleRecord.created_at.desc())
                .limit(CONTEXT_SCALE_LIMIT)
            ).all()
        ]
        diaries, trend = _diary_brief(db, user.id)

    return CrisisContextOut(
        event=row,
        user=brief,
        history=history,
        scales=scales,
        diaries=diaries,
        diary_trend=trend,
        source=_source_of(db, event),
        follow_ups=[CrisisFollowUpOut(**f) for f in list_follow_ups(db, event.id)],
        checklist=checklist_for(event.level),
        measure_options=[MeasureOption(**m) for m in measure_options(event.level)],
    )


def _count(db: Session, model: Any, *conditions: Any) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0


def _diary_brief(
    db: Session, user_id: int
) -> tuple[list[CrisisDiaryItem], CrisisDiaryTrend]:
    """近 10 条日记 + 趋势指标。

    `low_days` 是关键：单看某一天的心情分意义不大，
    **连续多天低分**才是"恶化"的信号 —— 这个维度系统此前完全没有。
    """
    from app.schemas import CrisisDiaryItem, CrisisDiaryTrend

    rows = list(
        db.scalars(
            select(EmotionDiary)
            .where(EmotionDiary.user_id == user_id)
            .order_by(EmotionDiary.diary_date.desc(), EmotionDiary.id.desc())
            .limit(CONTEXT_DIARY_LIMIT)
        ).all()
    )
    items = [
        CrisisDiaryItem(
            id=d.id,
            diary_date=d.diary_date.isoformat() if d.diary_date else None,
            mood_score=d.mood_score,
            dominant_emotion=d.dominant_emotion,
            content=d.diary_content,
            created_at=d.created_at.isoformat() if d.created_at else None,
        )
        for d in rows
    ]
    scores = [d.mood_score for d in rows if d.mood_score is not None]
    trend = CrisisDiaryTrend(
        count=len(rows),
        avg_mood=round(sum(scores) / len(scores), 1) if scores else None,
        low_days=sum(1 for s in scores if s <= 3),
        min_mood=min(scores) if scores else None,
    )
    return items, trend


def _source_of(db: Session, event: CrisisEvent) -> CrisisSourceOut | None:
    """触发本次工单的原始记录。

    ⚠️ 工单接口早就返回了 sessionId / diaryId，但前端一行都没用 ——
    「明明能一键跳到原始对话」却要管理员自己回咨询记录页翻。这里是补上那一环。
    """
    from app.schemas import CrisisDiaryItem, CrisisSourceMessage, CrisisSourceOut

    if event.source == "DIARY" and event.diary_id:
        d = db.get(EmotionDiary, event.diary_id)
        diary = (
            CrisisDiaryItem(
                id=d.id,
                diary_date=d.diary_date.isoformat() if d.diary_date else None,
                mood_score=d.mood_score,
                dominant_emotion=d.dominant_emotion,
                content=d.diary_content,
                created_at=d.created_at.isoformat() if d.created_at else None,
            )
            if d
            else None
        )
        return CrisisSourceOut(
            source="DIARY", diary_id=event.diary_id, diary=diary, messages=[]
        )

    if not event.session_id:
        return None

    session = db.get(ConsultationSession, event.session_id)
    messages = list(
        db.scalars(
            select(ConsultationMessage)
            .where(ConsultationMessage.session_id == event.session_id)
            .order_by(ConsultationMessage.created_at, ConsultationMessage.id)
            .limit(CONTEXT_MESSAGE_LIMIT)
        ).all()
    )
    trigger_id = _find_trigger_message_id(messages, event)
    return CrisisSourceOut(
        source="CHAT",
        session_id=event.session_id,
        session_title=session.session_title if session else None,
        messages=[
            CrisisSourceMessage(
                id=m.id,
                sender_type=m.sender_type,
                sender_type_desc=m.sender_type_desc(),
                content=m.content,
                created_at=m.created_at.isoformat() if m.created_at else None,
            )
            for m in messages
        ],
        trigger_message_id=trigger_id,
    )


def _find_trigger_message_id(
    messages: list[ConsultationMessage], event: CrisisEvent
) -> int | None:
    """定位到底是哪一句话触发的。

    工单里只有 120 字片段，管理员还要自己在整段对话里找触发点。
    命中不到就返回 None（例如 LLM 触发没有 matched_terms）。
    """
    terms = [t.strip() for t in (event.matched_terms or "").split(",") if t.strip()]
    if not terms:
        return None
    for m in reversed(messages):  # 取最近一条命中的用户消息
        if (m.sender_type or 0) == 1 and m.content:
            if any(t in m.content for t in terms):
                return m.id
    return None
