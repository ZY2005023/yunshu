"""宁渡课堂 · 全功能端到端测试（真实后端 + 真实 MySQL）

覆盖 39 个接口 + 权限边界，输出逐项结果。

与 `apps/api/tests/` 下 pytest 的分工：
  - pytest 跑在 SQLite 内存库上，验证「逻辑对不对」
  - 本脚本打真实后端、连真实 MySQL，验证「接口通不通、字段名和契约是否一致」
两者互补，不能互相替代（历史上踩过：SQLite 测不出来、真库才暴露的字段问题）。

用法：
    python scripts/e2e_full.py
    python scripts/e2e_full.py --base-url http://127.0.0.1:1236

前置条件：
    1. 后端已启动（默认 127.0.0.1:1236）
    2. 数据库可连（仅用于把测试账号提权为管理员，见 DB 配置）
    3. 会真实调用 2 次 AI（日记分析 + 对话流），其余项不消耗

注意：脚本会在库里创建测试账号与少量数据，建议在副本库上跑。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx


def _db_password() -> str:
    """数据库口令：环境变量优先，其次读 apps/api/.env（与后端同源）。

    ⚠️ 不要在这里写死口令 —— 这个脚本会进代码仓库，明文口令 = 随仓库分发。
    """
    if os.getenv("DB_PASSWORD"):
        return os.environ["DB_PASSWORD"]
    env_file = Path(__file__).resolve().parent.parent / "apps" / "api" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("DB_PASSWORD="):
                return line.split("=", 1)[1].strip()
    return ""


# ---- 数据库（只用于提权，不读写业务数据）----
DB = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USERNAME", "root"),
    "password": _db_password(),
    "database": os.getenv("DB_NAME", "mental_health_py"),
    "charset": "utf8mb4",
}

ROOT = None  # 由 main 注入的 httpx.Client

# ============================ 结果收集 ============================

_PASS: list[str] = []
_FAIL: list[tuple[str, str]] = []
_SKIP: list[str] = []


def ok(name: str, detail: str = "") -> None:
    _PASS.append(name)
    print(f"  \033[32m✓\033[0m {name}" + (f"  \033[90m{detail}\033[0m" if detail else ""))


def bad(name: str, reason: str) -> None:
    _FAIL.append((name, reason))
    print(f"  \033[31m✗\033[0m {name}  \033[31m{reason}\033[0m")


def skip(name: str, reason: str) -> None:
    _SKIP.append(f"{name}（{reason}）")
    print(f"  \033[33m—\033[0m {name}  \033[90m{reason}\033[0m")


def check(name: str, cond: bool, detail: str = "", reason: str = "") -> bool:
    if cond:
        ok(name, detail)
    else:
        bad(name, reason or detail or "断言失败")
    return cond


def section(title: str) -> None:
    print(f"\n\033[1m── {title} ──\033[0m")


# ============================ HTTP 辅助 ============================


def api(method: str, path: str, token: str | None = None, **kw):
    """返回 (status_code, json_or_text)。"""
    headers = kw.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = ROOT.request(method, path, headers=headers, **kw)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text


def body(resp):
    _, j = resp
    return j if isinstance(j, dict) else {}


# ============================ 用户端 ============================


def test_user_module(ts: str) -> dict:
    """注册 → 登录 → 当前用户 → 刷新 → 改密 → 登出。返回上下文。"""
    section("用户模块（6 个接口）")
    ctx: dict = {}

    # 1. 注册 —— 顺带验证「提权防护」：显式传 userType=2 也必须被强制成 1
    username = f"e2e_u_{ts}"
    password = "e2ePass123"
    sc, j = api(
        "POST",
        "/api/user/add",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "confirmPassword": password,
            "userType": 2,  # 恶意提权尝试
            "gender": 0,
        },
    )
    data = (j or {}).get("data") or {}
    check("POST /user/add 注册", (j or {}).get("code") == "200", f"id={data.get('id')}")
    check(
        "  提权防护：userType 被强制为 1",
        data.get("userType") == 1,
        reason=f"期望 1，实际 {data.get('userType')}",
    )
    ctx["username"] = username
    ctx["password"] = password
    ctx["user_id"] = data.get("id")

    # 2. 重复注册应被拒
    sc, j = api(
        "POST",
        "/api/user/add",
        json={
            "username": username,
            "email": f"other_{ts}@example.com",
            "password": password,
            "confirmPassword": password,
        },
    )
    check("  重复用户名被拒", (j or {}).get("code") != "200", f"code={(j or {}).get('code')}")

    # 3. 两次密码不一致应被拒
    sc, j = api(
        "POST",
        "/api/user/add",
        json={
            "username": f"e2e_mismatch_{ts}",
            "email": f"mm_{ts}@example.com",
            "password": "abc123456",
            "confirmPassword": "different1",
        },
    )
    check("  两次密码不一致被拒", (j or {}).get("code") != "200", f"code={(j or {}).get('code')}")

    # 4. 登录
    sc, j = api("POST", "/api/user/login", json={"username": username, "password": password})
    d = (j or {}).get("data") or {}
    check("POST /user/login 登录", bool(d.get("token")), f"roleType={d.get('roleType')!r}")
    check(
        "  roleType 是字符串（契约）",
        isinstance(d.get("roleType"), str),
        reason=f"实际类型 {type(d.get('roleType')).__name__}",
    )
    ctx["token"] = d.get("token")
    ctx["refresh_token"] = d.get("refreshToken")

    # 5. 错误密码
    sc, j = api("POST", "/api/user/login", json={"username": username, "password": "wrongpass"})
    check("  错误密码被拒", not ((j or {}).get("data") or {}).get("token"), f"code={(j or {}).get('code')}")

    # 6. 当前用户（带 token）
    sc, j = api("GET", "/api/user/current", token=ctx["token"])
    check(
        "GET /user/current",
        (j or {}).get("code") == "200" and ((j or {}).get("data") or {}).get("username") == username,
    )

    # 7. 刷新令牌
    sc, j = api("POST", "/api/user/refresh", json={"refreshToken": ctx["refresh_token"]})
    new_token = ((j or {}).get("data") or {}).get("token")
    check("POST /user/refresh 换发新令牌", bool(new_token))
    if new_token:
        sc, j2 = api("GET", "/api/user/current", token=new_token)
        check("  新令牌可用", (j2 or {}).get("code") == "200")
        ctx["token_after_refresh"] = new_token

    # 8. 登出（用刷新后的令牌，避免影响后续改密测试）
    live = ctx.get("token_after_refresh") or ctx["token"]
    sc, j = api("POST", "/api/user/logout", token=live, json={"refreshToken": ctx.get("refresh_token")})
    check("POST /user/logout", (j or {}).get("code") == "200", f"http={sc}")
    sc, j2 = api("GET", "/api/user/current", token=live)
    check(
        "  登出后原令牌失效（黑名单生效）",
        sc == 401,
        reason=f"期望 401，实际 {sc}",
    )

    # 9. 重新登录 + 改密
    sc, j = api("POST", "/api/user/login", json={"username": username, "password": password})
    t = ((j or {}).get("data") or {}).get("token")
    new_pwd = "e2eNewPass456"
    sc, j = api(
        "POST",
        "/api/user/password",
        token=t,
        json={"oldPassword": password, "newPassword": new_pwd, "confirmPassword": new_pwd},
    )
    check("POST /user/password 改密", (j or {}).get("code") == "200")

    sc, j = api("POST", "/api/user/login", json={"username": username, "password": password})
    check("  旧密码失效", not ((j or {}).get("data") or {}).get("token"))

    sc, j = api("POST", "/api/user/login", json={"username": username, "password": new_pwd})
    ctx["password"] = new_pwd
    ctx["token"] = ((j or {}).get("data") or {}).get("token")
    check("  新密码可登录", bool(ctx["token"]))

    return ctx


def test_profile(ctx: dict) -> None:
    """个人中心：/user/profile（PUT）。

    这是本次新增的接口 —— 原来用户**没有任何途径修改自己的资料**。
    """
    section("个人资料（1 个接口）")
    token = ctx["token"]

    sc, j = api(
        "PUT",
        "/api/user/profile",
        token=token,
        json={"nickname": "E2E 昵称", "phone": "13800138000", "gender": 1},
    )
    data = (j or {}).get("data") or {}
    check("PUT /user/profile 更新资料", (j or {}).get("code") == "200", f"nickname={data.get('nickname')}")
    check("  昵称已生效", data.get("nickname") == "E2E 昵称", reason=f"实际 {data.get('nickname')}")
    check("  手机号已生效", data.get("phone") == "13800138000")

    # 只传昵称时不能把其它字段清空（None = 跳过，不是置空）
    sc, j = api("PUT", "/api/user/profile", token=token, json={"nickname": "只改昵称"})
    data = (j or {}).get("data") or {}
    check(
        "  只传部分字段不影响其它字段",
        data.get("nickname") == "只改昵称" and data.get("phone") == "13800138000",
        reason=f"phone={data.get('phone')}",
    )

    # 提权防护：带上 userType/status 也必须被忽略
    sc, j = api(
        "PUT",
        "/api/user/profile",
        token=token,
        json={"nickname": "想提权", "userType": 2, "status": 0},
    )
    data = (j or {}).get("data") or {}
    check("  提权防护：userType/status 被忽略", data.get("userType") == 1, reason=f"userType={data.get('userType')}")

    sc, j = api("PUT", "/api/user/profile", json={"nickname": "未登录"})
    check("  未登录访问返回 401", sc == 401, reason=f"HTTP {sc}")


def test_user_admin(admin_token: str) -> None:
    """管理端用户管理：/user/admin/*（3 个接口）。

    原版完全没有这一组能力，导致 `deps.py` 里 `status != 1 → 403` 的校验永不触发，
    且「忘记密码」指引用户找管理员重置、管理员却没有重置能力。
    """
    section("用户管理（管理端 3 个接口）")
    ts = str(int(time.time()))

    # 造一个被管理的对象
    victim = f"e2e_v_{ts}"
    api(
        "POST",
        "/api/user/add",
        json={
            "username": victim,
            "email": f"{victim}@example.com",
            "password": "victim123",
            "confirmPassword": "victim123",
        },
    )

    # 1. 分页查询
    sc, j = api("GET", "/api/user/admin/page", token=admin_token, params={"keyword": victim})
    data = (j or {}).get("data") or {}
    records = data.get("records") or []
    check("GET /user/admin/page 分页", (j or {}).get("code") == "200", f"命中 {data.get('total')} 条")
    check("  关键词搜索命中", len(records) == 1, reason=f"命中 {len(records)} 条")
    check("  响应不含密码字段", all("password" not in r for r in records))

    if not records:
        check("  后续用例依赖该用户，跳过", False, reason="没搜到用户")
        return
    victim_id = records[0]["id"]

    # 2. 禁用 → 对方令牌立即失效
    sc, j = api("POST", "/api/user/login", json={"username": victim, "password": "victim123"})
    victim_token = ((j or {}).get("data") or {}).get("token")
    check("  受害者已登录", bool(victim_token))

    time.sleep(1.1)  # 跨过 iat 的秒级精度边界，见黑名单里的容差说明
    sc, j = api(
        "PUT", f"/api/user/admin/{victim_id}/status", token=admin_token, json={"status": 0}
    )
    check("PUT /user/admin/{id}/status 禁用", (j or {}).get("code") == "200")

    sc, j = api("GET", "/api/user/current", token=victim_token)
    check("  禁用后旧令牌失效", sc == 401, reason=f"HTTP {sc}")

    sc, j = api("POST", "/api/user/login", json={"username": victim, "password": "victim123"})
    check("  禁用后无法登录", not ((j or {}).get("data") or {}).get("token"))

    # 3. 重置密码 → 顺带解禁
    sc, j = api(
        "POST",
        f"/api/user/admin/{victim_id}/password",
        token=admin_token,
        json={"newPassword": "resetted789"},
    )
    check("POST /user/admin/{id}/password 重置", (j or {}).get("code") == "200")

    sc, j = api("POST", "/api/user/login", json={"username": victim, "password": "resetted789"})
    check("  重置后新密码可登录（且已解禁）", bool(((j or {}).get("data") or {}).get("token")))

    # 4. 越权：普通用户不能访问管理接口
    sc, j = api("GET", "/api/user/admin/page")
    check("  未登录访问管理接口返回 401", sc == 401, reason=f"HTTP {sc}")


def test_diary(ctx: dict) -> None:
    section("情绪日记（用户端 2 个接口）")
    today = date.today().isoformat()
    sc, j = api(
        "POST",
        "/api/emotion-diary",
        token=ctx["token"],
        timeout=120,
        json={
            "diaryDate": today,
            "moodScore": 7,
            "dominantEmotion": "平静",
            "emotionTriggers": "E2E 测试",
            "diaryContent": "端到端测试写入的日记",
            "sleepQuality": 4,
            "stressLevel": 2,
        },
    )
    d = (j or {}).get("data") or {}
    check("POST /emotion-diary 保存（含 AI 分析）", (j or {}).get("code") == "200", f"moodScore={d.get('moodScore')}")
    check("  返回带 aiEmotionAnalysis", d.get("aiEmotionAnalysis") is not None, "AI 未配置时可为 null")

    sc, j = api("GET", "/api/emotion-diary/my", token=ctx["token"])
    rows = (j or {}).get("data") or []
    check("GET /emotion-diary/my", isinstance(rows, list) and len(rows) >= 1, f"{len(rows)} 条")

    REQUIRED = ["diaryDate", "moodScore", "dominantEmotion", "sleepQuality", "stressLevel", "aiEmotionAnalysis"]
    if rows:
        missing = [k for k in REQUIRED if k not in rows[0]]
        check("  列表字段齐全（前端月历/统计依赖）", not missing, reason=f"缺失 {missing}")


def test_file(ctx: dict) -> None:
    section("文件上传（1 个接口）")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 256
    sc, j = api(
        "POST",
        "/api/file/upload",
        token=ctx["token"],
        timeout=30,
        files={"file": ("e2e.png", png, "image/png")},
        data={"businessType": "avatar"},  # camelCase alias 校验
    )
    d = (j or {}).get("data") or {}
    fp = d.get("filePath") or ""
    check("POST /file/upload", (j or {}).get("code") == "200", fp)
    check("  businessType alias 生效（落到 avatar 目录）", "/avatar/" in fp, reason=f"实际 {fp}")
    if fp:
        r = ROOT.get(fp)
        check("  上传的文件可访问", r.status_code == 200, f"HTTP {r.status_code}")

    # 非法类型应被拒
    sc, j = api(
        "POST",
        "/api/file/upload",
        token=ctx["token"],
        timeout=30,
        files={"file": ("bad.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    check("  非白名单类型被拒", (j or {}).get("code") != "200", f"code={(j or {}).get('code')}")


def test_knowledge_user(ctx: dict) -> None:
    section("知识库（用户端 4 个接口）")
    sc, j = api("GET", "/api/knowledge/article/page", token=ctx["token"], params={"currentPage": 1, "size": 5})
    d = (j or {}).get("data") or {}
    check("GET /knowledge/article/page", "records" in d and "total" in d, f"total={d.get('total')}")

    # 分页参数 alias 校验：第 2 页不应与第 1 页完全相同
    first = [r.get("id") for r in (d.get("records") or [])]
    sc, j2 = api("GET", "/api/knowledge/article/page", token=ctx["token"], params={"currentPage": 2, "size": 5})
    second = [r.get("id") for r in (((j2 or {}).get("data") or {}).get("records") or [])]
    if first and second:
        check("  currentPage alias 生效（第 2 页内容不同）", first != second)
    else:
        skip("currentPage alias 校验", "文章不足两页")

    sc, j = api("GET", "/api/knowledge/article", token=ctx["token"], params={"currentPage": 1, "size": 5})
    check("GET /knowledge/article", isinstance((j or {}).get("data"), (list, dict)))

    sc, j = api("GET", "/api/knowledge/category/tree", token=ctx["token"])
    tree = (j or {}).get("data") or []
    check("GET /knowledge/category/tree", isinstance(tree, list) and len(tree) > 0, f"{len(tree)} 个分类")

    # 详情：访问即阅读数 +1
    article_id = first[0] if first else None
    if article_id:
        sc, j1 = api("GET", f"/api/knowledge/article/{article_id}", token=ctx["token"])
        c1 = ((j1 or {}).get("data") or {}).get("readCount")
        sc, j2 = api("GET", f"/api/knowledge/article/{article_id}", token=ctx["token"])
        c2 = ((j2 or {}).get("data") or {}).get("readCount")
        check("GET /knowledge/article/{id}", c1 is not None, f"readCount={c1}")
        check("  访问即阅读数 +1（契约）", c2 == (c1 or 0) + 1, f"{c1} → {c2}")
    else:
        skip("文章详情", "库里没有文章")


def test_chat(ctx: dict) -> None:
    section("心理咨询（用户端 6 个接口，含 SSE）")
    sc, j = api("GET", "/api/psychological-chat/agents", token=ctx["token"])
    agents = (j or {}).get("data") or []
    check("GET /psychological-chat/agents", isinstance(agents, list) and len(agents) >= 5, f"{len(agents)} 个")

    sc, j = api(
        "POST",
        "/api/psychological-chat/session/start",
        token=ctx["token"],
        json={"initialMessage": "E2E 测试会话"},
    )
    sid = ((j or {}).get("data") or {}).get("sessionId")
    check("POST /session/start", bool(sid), f"sessionId={sid}")
    if not sid:
        return
    ctx["session_id"] = sid

    sc, j = api("GET", "/api/psychological-chat/sessions", token=ctx["token"], params={"currentPage": 1, "size": 10})
    d = (j or {}).get("data") or {}
    check("GET /sessions 列表", "records" in d or "total" in d, f"total={d.get('total')}")

    sc, j = api("GET", f"/api/psychological-chat/sessions/{sid}/messages", token=ctx["token"])
    msgs = ((j or {}).get("data") or {}).get("messages") or []
    check("GET /sessions/{id}/messages", isinstance(msgs, list), f"{len(msgs)} 条")
    if msgs:
        check("  含 senderType 与 senderTypeDesc", "senderType" in msgs[0] and "senderTypeDesc" in msgs[0])

    # 会话情绪：契约规定永远为 null（Java 侧从未写入）
    sc, j = api("GET", f"/api/psychological-chat/session/{sid}/emotion", token=ctx["token"])
    # 契约：lastEmotionAnalysis 在 Java 侧从未写入，因此 emotionAnalysis 恒为 null
    # （注意返回的是对象 {sessionId, emotionAnalysis}，不是裸 null）
    emo = (j or {}).get("data") or {}
    check(
        "GET /session/{id}/emotion 的 emotionAnalysis 恒为 null（契约行为）",
        isinstance(emo, dict) and emo.get("emotionAnalysis") is None,
        f"emotionAnalysis={emo.get('emotionAnalysis')!r}",
    )

    # SSE 流式（真实调用一次 AI）
    print("    \033[90m…SSE 流式测试会真实调用 AI，约 10-30 秒\033[0m")
    try:
        with ROOT.stream(
            "POST",
            "/api/psychological-chat/stream",
            headers={"Authorization": f"Bearer {ctx['token']}"},
            json={"sessionId": sid, "userMessage": "你好，简单介绍一下你自己"},
            timeout=150,
        ) as r:
            ctype = r.headers.get("content-type", "")
            raw = r.read().decode("utf-8")
        check("POST /stream 返回 SSE", ctype.startswith("text/event-stream"), ctype[:40])
        events = [ln[6:].strip() for ln in raw.split("\n") if ln.startswith("event:")]
        check("  含 message 事件", "message" in events, f"事件={sorted(set(events))}")
        check("  以 done 收尾", events and events[-1] == "done", f"末事件={events[-1] if events else '无'}")
        check("  含 agent 事件（路由结果）", "agent" in events)
    except Exception as e:  # noqa: BLE001
        bad("POST /stream SSE", f"异常 {e}")

    # 删会话
    sc, j = api("DELETE", f"/api/psychological-chat/sessions/{sid}", token=ctx["token"])
    check("DELETE /sessions/{id}", (j or {}).get("code") == "200")
    sc, j = api("GET", f"/api/psychological-chat/sessions/{sid}/messages", token=ctx["token"])
    check("  删除后不可再取消息", (j or {}).get("code") != "200")


def test_scale(ctx: dict) -> None:
    section("心理量表（用户端 5 个接口）")
    sc, j = api("GET", "/api/scale/questions", token=ctx["token"], params={"code": "PHQ9"})
    d = (j or {}).get("data") or {}
    qs = d.get("questions") or []
    check("GET /scale/questions", len(qs) == 9, f"PHQ-9 {len(qs)} 题")
    check("  选项 4 档", len(d.get("options") or []) == 4)

    sc, j = api("GET", "/api/scale/questions", token=ctx["token"], params={"code": "GAD7"})
    check("  GAD-7 共 7 题", len(((j or {}).get("data") or {}).get("questions") or []) == 7)

    # 第 9 题（自伤项）给 3 分 —— 应触发危机工单
    answers = [0] * 8 + [3]
    sc, j = api("POST", "/api/scale/submit", token=ctx["token"], json={"scaleCode": "PHQ9", "answers": answers})
    d = (j or {}).get("data") or {}
    check("POST /scale/submit", (j or {}).get("code") == "200", f"total={d.get('total')} level={d.get('level')}")
    check("  自伤项命中被标记", bool(d.get("selfHarmRisk")), f"selfHarmRisk={d.get('selfHarmRisk')}")
    ctx["scale_total"] = d.get("total")

    sc, j = api("GET", "/api/scale/my", token=ctx["token"])
    rows = (j or {}).get("data") or []
    check("GET /scale/my", isinstance(rows, list) and len(rows) >= 1, f"{len(rows)} 条")

    sc, j = api("GET", "/api/scale/my/latest", token=ctx["token"])
    check("GET /scale/my/latest", isinstance((j or {}).get("data"), dict))

    sc, j = api("GET", "/api/scale/trend", token=ctx["token"], params={"code": "PHQ9"})
    check("GET /scale/trend", isinstance((j or {}).get("data"), list))

    # 参数校验：答案数量不对应被拒
    sc, j = api("POST", "/api/scale/submit", token=ctx["token"], json={"scaleCode": "PHQ9", "answers": [0, 1]})
    check("  答案数量不符被拒", (j or {}).get("code") != "200", f"code={(j or {}).get('code')}")


# ============================ 管理端 ============================


def test_admin_crisis(admin: str, ctx: dict) -> None:
    section("危机预警工单（管理端 4 个接口）")
    sc, j = api("GET", "/api/admin/crisis/page", token=admin, params={"currentPage": 1, "size": 10})
    d = (j or {}).get("data") or {}
    check("GET /admin/crisis/page", "records" in d and "total" in d, f"total={d.get('total')}")
    records = d.get("records") or []

    # 量表自伤项应自动生成工单
    src_kinds = {r.get("source") for r in records}
    check(
        "  量表自伤项已自动生成工单（source=SCALE）",
        "SCALE" in src_kinds,
        f"来源={src_kinds}",
    )

    sc, j = api("GET", "/api/admin/crisis/pending/count", token=admin)
    check("GET /pending/count", isinstance((j or {}).get("data"), int), f"待处理 {((j or {}).get('data'))}")

    sc, j = api("GET", "/api/admin/crisis/resources", token=admin)
    d = (j or {}).get("data") or {}
    helplines = d.get("helplines")
    check("GET /resources", bool(d.get("title")), d.get("title"))
    check(
        "  helplines 是纯字符串数组（契约）",
        isinstance(helplines, list) and all(isinstance(x, str) for x in helplines),
        f"{len(helplines) if isinstance(helplines, list) else '?'} 条热线",
    )

    if records:
        eid = records[0].get("id")
        sc, j = api(
            "POST",
            f"/api/admin/crisis/{eid}/handle",
            token=admin,
            # status 是字符串枚举 RESOLVED/IGNORED/HANDLING（原版行为），不是数字
            json={"handleNote": "E2E 测试处置", "status": "RESOLVED"},
        )
        check("POST /crisis/{id}/handle 处置工单", (j or {}).get("code") == "200", f"id={eid}")
        sc, j2 = api("GET", "/api/admin/crisis/page", token=admin, params={"currentPage": 1, "size": 10})
        hit = next((x for x in ((j2 or {}).get("data") or {}).get("records", []) if x.get("id") == eid), None)
        check("  处置结果已留痕", bool(hit and hit.get("handleNote")), f"note={hit.get('handleNote') if hit else None}")
    else:
        skip("处置工单", "没有工单可处置")


def test_admin_analytics(admin: str) -> None:
    section("数据看板（1 个接口）")
    sc, j = api("GET", "/api/data-analytics/overview", token=admin, timeout=30)
    d = (j or {}).get("data") or {}
    check("GET /data-analytics/overview", (j or {}).get("code") == "200")

    # 契约 2.8 要求这 6 个顶层字段，名字必须完全一致
    KEYS = ["systemOverview", "emotionHeatmap", "consultationStats", "dailyTrend", "trendData", "activityData"]
    missing = [k for k in KEYS if k not in d]
    check("  6 个顶层字段齐全（契约 2.8）", not missing, reason=f"缺失 {missing}")

    grid = (d.get("emotionHeatmap") or {}).get("gridData")
    check(
        "  热力图 7×10 二维数组",
        isinstance(grid, list) and len(grid) == 7 and all(len(r) == 10 for r in grid),
        f"{len(grid) if isinstance(grid, list) else '?'} 行",
    )
    check("  dailyTrend 为 7 天序列", len(d.get("dailyTrend") or []) == 7)
    tro = d.get("systemOverview") or {}
    check(
        "  systemOverview 字段齐全",
        all(k in tro for k in ["totalUsers", "activeUsers", "totalDiaries", "totalSessions", "avgMoodScore"]),
    )
    cs = d.get("consultationStats") or {}
    check(
        "  consultationStats 无 avgDurationMinutes（契约里不存在）",
        "avgDurationMinutes" not in cs,
        f"实际键={sorted(cs)}",
    )


def test_admin_diary_and_scale(admin: str, ctx: dict) -> None:
    section("管理端：情绪日志 / 量表记录（3 个接口）")
    sc, j = api("GET", "/api/emotion-diary/admin/page", token=admin, params={"currentPage": 1, "size": 10})
    d = (j or {}).get("data") or {}
    check("GET /emotion-diary/admin/page", "records" in d and "total" in d, f"total={d.get('total')}")

    sc, j = api("GET", "/api/scale/admin/page", token=admin, params={"currentPage": 1, "size": 10})
    d = (j or {}).get("data") or {}
    check("GET /scale/admin/page", "records" in d and "total" in d, f"total={d.get('total')}")

    # 只看自伤项命中的记录
    sc, j = api(
        "GET", "/api/scale/admin/page", token=admin,
        params={"currentPage": 1, "size": 10, "onlySelfHarm": "true"},
    )
    d = (j or {}).get("data") or {}
    check("  自伤项筛选生效", "records" in d, f"total={d.get('total')}")

    sc, j = api("GET", "/api/psychological-chat/admin/sessions", token=admin, params={"currentPage": 1, "size": 10})
    d = (j or {}).get("data") or {}
    check("GET /psychological-chat/admin/sessions", "records" in d and "total" in d, f"total={d.get('total')}")


def test_admin_knowledge(admin: str, ctx: dict) -> None:
    section("管理端：知识文章 CRUD + 索引（5 个接口）")

    # 取分类（新增文章要 categoryId）
    sc, j = api("GET", "/api/knowledge/category/tree", token=admin)
    tree = (j or {}).get("data") or []
    cid = tree[0].get("id") if tree else 1

    title = f"E2E 测试文章 {int(time.time())}"
    sc, j = api(
        "POST",
        "/api/knowledge/article",
        token=admin,
        json={"categoryId": cid, "title": title, "summary": "E2E", "content": "这是端到端测试创建的文章内容。", "status": 1},
    )
    aid = ((j or {}).get("data") or {}).get("id")
    check("POST /knowledge/article 新增", bool(aid), f"id={aid}")
    if not aid:
        return

    sc, j = api(
        "PUT",
        f"/api/knowledge/article/{aid}",
        token=admin,
        json={"categoryId": cid, "title": title + "（已改）", "summary": "E2E", "content": "更新后的内容。", "status": 1},
    )
    check("PUT /knowledge/article/{id} 更新", (j or {}).get("code") == "200")

    sc, j = api("GET", f"/api/knowledge/article/{aid}", token=admin)
    got = ((j or {}).get("data") or {}).get("title")
    check("  更新已生效", got == title + "（已改）", f"title={got}")

    sc, j = api("PUT", f"/api/knowledge/article/{aid}/status", token=admin, json={"status": 0})
    check("PUT /article/{id}/status 改状态", (j or {}).get("code") == "200")

    sc, j = api("POST", "/api/knowledge/admin/reindex", token=admin, timeout=60)
    check("POST /knowledge/admin/reindex 重建索引", (j or {}).get("code") == "200", f"data={(j or {}).get('data')}")

    sc, j = api("DELETE", f"/api/knowledge/article/{aid}", token=admin)
    check("DELETE /knowledge/article/{id} 删除", (j or {}).get("code") == "200")
    sc, j = api("GET", f"/api/knowledge/article/{aid}", token=admin)
    # 原版对不存在的文章返回 code=200 + data=null（不是 404）
    check(
        "  删除后详情为 ok(null)（原版行为）",
        (j or {}).get("code") == "200" and (j or {}).get("data") is None,
        f"code={(j or {}).get('code')} data={(j or {}).get('data')}",
    )


def test_admin_diary_delete(admin: str, ctx: dict) -> None:
    section("管理端：删除情绪日记（1 个接口）")
    # 找到刚才那个测试用户的日记
    sc, j = api("GET", "/api/emotion-diary/admin/page", token=admin, params={"currentPage": 1, "size": 50})
    rows = ((j or {}).get("data") or {}).get("records") or []
    target = next((r for r in rows if r.get("username") == ctx.get("username")), None)
    if not target:
        skip("DELETE /emotion-diary/admin/{id}", "没找到该测试用户的日记")
        return
    sc, j = api("DELETE", f"/api/emotion-diary/admin/{target['id']}", token=admin)
    check("DELETE /emotion-diary/admin/{id}", (j or {}).get("code") == "200", f"id={target['id']}")


# ============================ 权限边界 ============================


def test_authz(user: str, admin: str) -> None:
    section("权限与鉴权边界")

    ADMIN_ONLY = [
        ("GET", "/api/admin/crisis/page"),
        ("GET", "/api/data-analytics/overview"),
        ("GET", "/api/emotion-diary/admin/page"),
        ("GET", "/api/scale/admin/page"),
        ("GET", "/api/psychological-chat/admin/sessions"),
    ]
    for method, path in ADMIN_ONLY:
        sc, j = api(method, path, token=user, params={"currentPage": 1, "size": 5})
        c = (j or {}).get("code")
        check(
            f"普通用户访问 {path} 被拒（400/A0300）",
            sc == 400 and c == "A0300",
            reason=f"实际 HTTP {sc} / code={c}",
        )

    # 未登录
    r = ROOT.get("/api/user/current")
    check("未登录访问 /user/current → 401", r.status_code == 401, f"HTTP {r.status_code}")
    r = ROOT.get("/api/admin/crisis/page")
    check("未登录访问管理端接口 → 401", r.status_code == 401, f"HTTP {r.status_code}")

    # 伪造令牌
    sc, j = api("GET", "/api/user/current", token="fake.token.value")
    check("伪造令牌 → 401", sc == 401, f"HTTP {sc}")

    # 普通用户不能访问管理端页面（前端路由守卫，此处验证后端不靠前端）
    sc, j = api("POST", "/api/knowledge/article", token=user, json={"categoryId": 1, "title": "x", "content": "y"})
    check("普通用户新增文章被拒", sc == 400 and (j or {}).get("code") == "A0300", f"HTTP {sc}")


# ============================ 主流程 ============================


def promote_to_admin(username: str) -> bool:
    """把测试账号提权为管理员（真实系统靠 SQL 改 user_type）。"""
    try:
        import pymysql

        conn = pymysql.connect(autocommit=True, **DB)
        cur = conn.cursor()
        cur.execute("UPDATE user SET user_type = 2 WHERE username = %s", (username,))
        conn.close()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  \033[33m提权失败（管理端测试将跳过）：{e}\033[0m")
        return False


def main() -> int:
    global ROOT

    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:1236")
    args = ap.parse_args()

    print(f"\033[1m云舒 · 全功能端到端测试\033[0m")
    print(f"目标：{args.base_url}")
    print(f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")

    with httpx.Client(base_url=args.base_url, timeout=30, follow_redirects=True) as client:
        ROOT = client
        try:
            client.get("/actuator/health")
        except Exception as e:  # noqa: BLE001
            print(f"\n\033[31m后端未就绪：{e}\033[0m")
            return 2

        ts = str(int(time.time()))
        started = time.time()

        # ---- 用户端 ----
        ctx = test_user_module(ts)
        if not ctx.get("token"):
            print("\n\033[31m注册/登录失败，后续用户端测试无法进行\033[0m")
            return 1

        test_diary(ctx)
        test_file(ctx)
        test_knowledge_user(ctx)
        test_scale(ctx)
        test_chat(ctx)
        test_profile(ctx)

        # ---- 管理端（另建一个账号并提权）----
        admin_user = f"e2e_a_{ts}"
        sc, j = api(
            "POST",
            "/api/user/add",
            json={
                "username": admin_user,
                "email": f"{admin_user}@example.com",
                "password": "adminPass123",
                "confirmPassword": "adminPass123",
            },
        )
        if promote_to_admin(admin_user):
            sc, j = api("POST", "/api/user/login", json={"username": admin_user, "password": "adminPass123"})
            admin_token = ((j or {}).get("data") or {}).get("token")
            if admin_token:
                test_admin_crisis(admin_token, ctx)
                test_admin_analytics(admin_token)
                test_admin_diary_and_scale(admin_token, ctx)
                test_admin_knowledge(admin_token, ctx)
                test_admin_diary_delete(admin_token, ctx)
                test_user_admin(admin_token)
            else:
                bad("管理员登录", "拿不到令牌")
        else:
            skip("管理端全部测试", "无法提权")

        # ---- 权限边界 ----
        test_authz(ctx["token"], locals().get("admin_token", ""))

        elapsed = time.time() - started

    total = len(_PASS) + len(_FAIL)
    print("\n" + "=" * 62)
    print(f"\033[1m结果：通过 {len(_PASS)} / {total}\033[0m" + (f"，跳过 {len(_SKIP)}" if _SKIP else ""))
    if _FAIL:
        print(f"\n\033[31m失败项：\033[0m")
        for name, reason in _FAIL:
            print(f"  ✗ {name}  —— {reason}")
    if _SKIP:
        print(f"\n\033[33m跳过项：\033[0m")
        for s in _SKIP:
            print(f"  — {s}")
    print(f"\n耗时 {elapsed:.1f}s")
    print("=" * 62)

    return 0 if not _FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
