"""浏览器自动化走查 —— 用真实 Chromium 逐页查看并截图。

用法：
    cd apps/api
    .venv/Scripts/python.exe ../scripts/ui_walkthrough.py

前提：
    · 后端已启动（127.0.0.1:1236），且 apps/api/static/ 里有前端 dist
    · 存在测试账号 uitest_user / uitest_admin（密码 uitest123）

产出：
    · _shots/<时间戳>/ 下的整页截图（每页一张）
    · 控制台错误 / 页面异常汇总（走查结束打印）
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:1236"
USER = {"username": "uitest_user", "password": "uitest123"}
ADMIN = {"username": "uitest_admin", "password": "uitest123"}

OUT = Path(__file__).resolve().parent.parent / "_shots" / datetime.now().strftime("%Y%m%d-%H%M%S")

console_errors: list[str] = []
page_errors: list[str] = []
failures: list[str] = []


def shot(page, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    print(f"  📸 {name}")


def watch(page, tag: str) -> None:
    page.on(
        "console",
        lambda msg: console_errors.append(f"[{tag}] {msg.text[:200]}")
        if msg.type == "error"
        else None,
    )
    page.on(
        "pageerror",
        lambda exc: page_errors.append(f"[{tag}] {str(exc)[:200]}"),
    )


def step(name: str):
    def deco(fn):
        def run(*a, **kw):
            print(f"▶ {name}")
            try:
                fn(*a, **kw)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{name}: {exc}")
                print(f"  ❌ {exc}")
            return fn
        return run
    return deco


def login(page, account: dict) -> None:
    page.goto(f"{BASE}/auth/login", wait_until="networkidle")
    page.fill('input[placeholder*="用户名"]', account["username"])
    page.fill('input[placeholder*="密码"]', account["password"])
    page.click(".submit-btn")
    page.wait_for_url(lambda url: "/auth" not in url, timeout=15000)
    page.wait_for_load_state("networkidle")


def main() -> int:
    started = time.monotonic()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = ctx.new_page()
        watch(page, "global")

        # ---------- 匿名 ----------
        print("▶ 匿名：首页")
        page.goto(f"{BASE}/", wait_until="networkidle")
        shot(page, "01-home-anonymous")

        print("▶ 匿名：登录页")
        page.goto(f"{BASE}/auth/login", wait_until="networkidle")
        shot(page, "02-login")

        # ---------- 普通用户 ----------
        print("▶ 登录（普通用户）")
        login(page, USER)
        page.wait_for_timeout(800)

        print("▶ /consultation 对话页")
        page.wait_for_url("**/consultation", timeout=10000)
        page.wait_for_load_state("networkidle")
        shot(page, "03-consultation")

        print("▶ 对话：发一条消息等 AI 回复")
        # el-input 的 class 挂在外层 wrapper 上，真正的 textarea 在里面
        page.fill(".message-input textarea", "今天有点累，想找人说说")
        page.keyboard.press("Enter")
        try:
            # 等「AI 回复完成」：三个条件缺一不可 ——
            #   ① .message-item 数 >= 2（欢迎语在 messages.length===0 时出现，
            #      它本身有文字，不判这一条会在发送前就误命中）；
            #   ② 打字指示器消失；③ 最后一条 AI 气泡有内容。
            # 误命中会导致下一步跳转掐断流（离开页面=主动中断，是产品行为）。
            page.wait_for_function(
                """() => {
                    const items = document.querySelectorAll('.message-item');
                    if (items.length < 2) return false;
                    if (document.querySelector('.typing-indicator')) return false;
                    const aiItems = document.querySelectorAll('.ai-message');
                    const last = aiItems[aiItems.length - 1];
                    if (!last) return false;
                    const bubble = last.querySelector('.message-bubble');
                    if (!bubble || !bubble.textContent.trim()) return false;
                    // done 事件到达后时间标签才从「正在输入中...」变成具体时间
                    const timeLabel = last.querySelector('.message-time');
                    return !!(timeLabel && !timeLabel.textContent.includes('正在输入中'));
                }""",
                timeout=90000,
            )
            page.wait_for_timeout(500)
            shot(page, "04-consultation-replied")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"对话回复超时: {exc}")
            shot(page, "04-consultation-replied-timeout")

        print("▶ /emotion-diary 日记页")
        page.goto(f"{BASE}/emotion-diary", wait_until="networkidle")
        shot(page, "05-diary")
        try:
            # 点滑块中段（约 6 分）
            runway = page.locator(".mood-slider .el-slider__runway")
            box = runway.bounding_box()
            page.mouse.click(box["x"] + box["width"] * 0.56, box["y"] + box["height"] / 2)
            # 「想多说一点」选填区：首次进入默认折叠；当天已有记录时会预填并
            # 自动展开 —— 所以按状态判断，不能无脑点 toggle（会把展开的收起来）
            if not page.locator('textarea[placeholder*="写下今天"]').is_visible():
                page.click(".more-toggle")
                page.wait_for_timeout(300)
            page.fill('textarea[placeholder*="写下今天"]', "今天按部就班，晚上散步了半小时，整体平稳。")
            # 当天已有记录时按钮文案是「更新今天」，两种都要能点
            page.click('button:has-text("保存记录"), button:has-text("更新今天")')
            page.wait_for_timeout(3000)  # 等 AI 分析回填（有 AI key 时会等一次分析）
            shot(page, "06-diary-saved")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"日记保存: {exc}")

        print("▶ /scale 测评页（GAD-7 全流程）")
        page.goto(f"{BASE}/scale", wait_until="networkidle")
        shot(page, "07-scale")
        try:
            page.locator(".pick-card", has_text="GAD-7").click()
            page.wait_for_selector(".question", timeout=8000)
            for i in range(7):
                page.locator(f".question:nth-of-type({i + 1}) .el-radio").first.click(timeout=5000)
            page.click('button:has-text("提交并查看结果")')
            page.wait_for_selector(".result", timeout=8000)
            shot(page, "08-scale-result")
            page.click('button:has-text("知道了")')
        except Exception as exc:  # noqa: BLE001
            failures.append(f"量表流程: {exc}")

        print("▶ /knowledge 知识库 + 文章详情")
        page.goto(f"{BASE}/knowledge", wait_until="networkidle")
        shot(page, "09-knowledge")
        try:
            page.locator(".article-item, .recommend-item").first.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(600)
            shot(page, "10-article-detail")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"文章详情: {exc}")

        print("▶ /profile 个人中心")
        page.goto(f"{BASE}/profile", wait_until="networkidle")
        shot(page, "11-profile")

        # ---------- 管理员 ----------
        print("▶ 切换管理员登录")
        page.evaluate("localStorage.clear()")
        login(page, ADMIN)
        page.wait_for_url("**/back/**", timeout=15000)
        page.wait_for_timeout(1200)

        print("▶ /back/dashboard 看板")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)  # 等图表渲染
        shot(page, "12-admin-dashboard")

        for path, name in [
            ("/back/crisis", "13-admin-crisis"),
            ("/back/scales", "14-admin-scales"),
            ("/back/consultations", "15-admin-consultations"),
            ("/back/emotional", "16-admin-emotional"),
            ("/back/knowledge", "17-admin-knowledge"),
            ("/back/users", "18-admin-users"),
        ]:
            print(f"▶ {path}")
            page.goto(f"{BASE}{path}", wait_until="networkidle")
            page.wait_for_timeout(900)
            shot(page, name)

        print("▶ /back/ai-config API 管理（含真实连通测试）")
        page.goto(f"{BASE}/back/ai-config", wait_until="networkidle")
        shot(page, "19-admin-aiconfig")
        try:
            page.click('button:has-text("测试连接")')
            page.wait_for_selector(".test-result", timeout=40000)
            # 管理端滚动发生在内部容器里，full_page 截不到折叠区 —— 先滚进视口
            page.locator(".test-result").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            shot(page, "20-admin-aiconfig-test")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"AI 连通测试: {exc}")

        # ---------- SPA 深链接（生产形态）----------
        print("▶ SPA 深链接：直接打开 /back/crisis（F5 场景）")
        page.goto(f"{BASE}/back/crisis", wait_until="networkidle")
        shot(page, "21-spa-deeplink-crisis")

        browser.close()

    elapsed = time.monotonic() - started
    print("\n" + "=" * 60)
    print(f"走查完成，用时 {elapsed:.0f}s；截图目录: {OUT}")
    print(f"页面异常: {len(page_errors)} 条；控制台错误: {len(console_errors)} 条；步骤失败: {len(failures)} 个")
    for e in page_errors[:10]:
        print("  [pageerror]", e)
    for e in console_errors[:10]:
        print("  [console]", e)
    for e in failures:
        print("  [failed]", e)
    return 1 if (page_errors or failures) else 0


if __name__ == "__main__":
    sys.exit(main())
