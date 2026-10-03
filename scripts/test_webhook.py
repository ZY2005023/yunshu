"""验证危机通知**真的能收到**。

用法：
    python scripts/test_webhook.py

配完 CRISIS_WEBHOOK_URL 后一定要跑一次。为什么不能只靠"保存成功"：
通知是在后台线程里 fire-and-forget 发的，**失败既不报错也不上抛**——
地址填错、平台格式不匹配、机器人开了加签，表现都是"群里没人收到"，
而系统日志里只有一行 warning。等你真出事那天才发现，已经晚了。

这个脚本会同步发一条测试消息，并把平台的原始响应打出来。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.core.config import settings  # noqa: E402
from app.services.notifier import _payload, build_message  # noqa: E402

# 各家机器人被拒时的含义，凭 errcode 直接定位，省得去翻文档
_ERR_HINTS = {
    310000: "钉钉：机器人开了「加签」或 IP 不在白名单。本代码没有实现加签签名 —— "
            "去机器人安全设置里改成「自定义关键词」或填服务器 IP 段。",
    93000: "企业微信：无效的 webhook 地址，或机器人已被移除。",
    19001: "飞书：机器人已停用或不在该群里。",
    9499: "飞书：触发了限流，稍后再试。",
}


def main() -> None:
    url = (settings.crisis.webhook_url or "").strip()
    if not url:
        print("CRISIS_WEBHOOK_URL 还没配置。")
        print("在 apps/api/.env 里填一行：CRISIS_WEBHOOK_URL=https://...")
        sys.exit(1)

    # 域名里带 feishu / larksuite 才走飞书格式，其余走企微/钉钉
    platform = "飞书" if ("feishu" in url or "larksuite" in url) else "企业微信 / 钉钉"
    print(f"地址    : {url[:60]}{'...' if len(url) > 60 else ''}")
    print(f"识别平台: {platform}")

    event = SimpleNamespace(
        id=0,
        level=3,
        source="CHAT",
        trigger_type="连通性测试",
        created_at=datetime.now(),
        user_id=0,
        matched_terms="（测试）",
        content_snippet="这是一条部署前的连通性测试。收到这条消息，说明危机通知配置正确。",
    )
    text = build_message(event)

    print("\n将要发送的内容：")
    print("-" * 50)
    print(text)
    print("-" * 50)

    import httpx  # noqa: PLC0415

    try:
        resp = httpx.post(url, json=_payload(text, url), timeout=10.0)
    except Exception as exc:  # noqa: BLE001
        print(f"\n[失败] 请求没发出去：{exc}")
        print("检查服务器能否访问外网（很多内网机器需要配代理）。")
        sys.exit(1)

    print(f"\nHTTP 状态: {resp.status_code}")
    print(f"响应内容: {resp.text[:300]}")

    if resp.status_code != 200:
        print("\n[失败] 平台没有接受这条消息。")
        sys.exit(1)

    code = None
    try:
        body = resp.json()
        if isinstance(body, dict):
            code = body.get("errcode") or body.get("code")
    except Exception:  # noqa: BLE001
        body = None

    if code in (None, 0):
        print("\n[成功] 平台已接收。现在去看群里有没有这条消息 ——")
        print("       **群里没看到就等于没配好**，别只看脚本说成功。")
        return

    print(f"\n[失败] 平台返回错误码 {code}")
    if code in _ERR_HINTS:
        print(f"原因：{_ERR_HINTS[code]}")
    sys.exit(1)


if __name__ == "__main__":
    main()
