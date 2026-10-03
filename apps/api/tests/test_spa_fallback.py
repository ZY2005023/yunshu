"""SPA 兜底路由（main.py `spa_fallback`）的回归测试。

背景：前端是 history 模式路由 + 生产形态由本服务托管 dist。
没有兜底时，在 /profile 上按 F5 会拿到 JSON 404 —— 除首页外所有页面
都不可直达。加了兜底之后，两条边界必须守住：

1. 未知 **API** 路径仍然返回 JSON 404（前端请求层依赖这个形状做错误提示）；
2. 兜底永远不能把 dist 目录之外的文件带出去（路径穿越）。

dist 是否存在走的是运行时判断（`_DIST / "index.html".is_file()`），
所以用 monkeypatch 替换 `_DIST` 即可覆盖两种形态，不用真的构建前端。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import main as app_main


class TestSpaFallback:
    def test_unknown_api_path_stays_json_404(self, client: TestClient):
        """未知 API 路径不进 SPA 兜底 —— 响应必须是 JSON 404，不是 HTML。"""
        resp = client.get("/api/definitely-not-a-route")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "404"
        assert "text/html" not in resp.headers.get("content-type", "")

    def test_spa_route_served_from_dist(self, client: TestClient, monkeypatch, tmp_path):
        """dist 存在时，前端路由路径返回 index.html（HTTP 200）。"""
        (tmp_path / "index.html").write_text("<html>云舒 SPA</html>", encoding="utf-8")
        monkeypatch.setattr(app_main, "_DIST", tmp_path)

        resp = client.get("/profile")
        assert resp.status_code == 200
        assert "云舒 SPA" in resp.text

        # 多级路径同样要兜底（管理端深链接）
        resp = client.get("/back/crisis")
        assert resp.status_code == 200
        assert "云舒 SPA" in resp.text

    def test_dist_static_file_direct_hit(self, client: TestClient, monkeypatch, tmp_path):
        """dist 里的真实静态文件（favicon 之类）应直接命中，而不是回 index.html。"""
        (tmp_path / "index.html").write_text("<html>spa</html>", encoding="utf-8")
        (tmp_path / "favicon.ico").write_bytes(b"ico")
        monkeypatch.setattr(app_main, "_DIST", tmp_path)

        resp = client.get("/favicon.ico")
        assert resp.status_code == 200
        assert resp.content == b"ico"

    def test_json_404_when_dist_missing(self, client: TestClient, monkeypatch, tmp_path):
        """dist 未构建（纯后端调试）时保持旧行为：JSON 404。"""
        monkeypatch.setattr(app_main, "_DIST", tmp_path / "missing-dist")

        resp = client.get("/profile")
        assert resp.status_code == 404
        assert resp.json()["code"] == "404"

    def test_traversal_cannot_escape_dist(self, monkeypatch, tmp_path):
        """兜底不得把 dist 之外的文件带出去（路径穿越防护）。

        直接调用路由函数：TestClient/httpx 会在客户端侧把 `../` 归一化掉，
        打不发出去的攻击载荷只能在函数层验证。
        """
        outside = tmp_path / "outside.txt"
        outside.write_text("SECRET-OUTSIDE", encoding="utf-8")
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
        monkeypatch.setattr(app_main, "_DIST", dist)

        resp = app_main.spa_fallback("../outside.txt")
        # dist 外的文件绝不作为响应体返回 —— 只能回退到 index.html
        assert resp.path == dist / "index.html"
        assert resp.path != outside

    def test_root_still_served_by_index_route(self, client: TestClient):
        """`/` 走原有的 index 路由（注册在兜底之前），行为不变。"""
        resp = client.get("/")
        assert resp.status_code == 200
