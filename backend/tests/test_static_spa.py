# -*- coding: utf-8 -*-
"""SPA 静态托管安全：路径穿越必须回退 index.html，绝不能读到 dist 之外的文件。

测试用临时目录构造最小 dist（index.html + assets），不依赖真实前端构建产物——
frontend/dist 被 gitignore，全新环境下这组安全用例不能整组跳过。
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from main import mount_spa

INDEX_HTML = "<!doctype html><title>fake dist</title>"


@pytest.fixture()
def spa_client(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    app = FastAPI()
    assert mount_spa(app, dist) is True
    return TestClient(app), INDEX_HTML.encode("utf-8")


class TestSpaFallback:
    def test_root_serves_index(self, spa_client):
        client, index = spa_client
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.content == index

    def test_path_traversal_falls_back_to_index(self, spa_client):
        """编码的 ..\\ 穿越请求：回退 index.html，不回 .env 内容。"""
        client, index = spa_client
        for path in ("/..%5c..%5c.env", "/%2e%2e/%2e%2e/.env", "/..%5c..%5cREADME.md"):
            resp = client.get(path)
            assert resp.status_code == 200
            assert resp.content == index, f"路径穿越未被拦截：{path}"

    def test_real_static_file_served(self, spa_client):
        client, _ = spa_client
        resp = client.get("/assets/app.js")
        assert resp.status_code == 200
        assert resp.content == b"console.log(1)"

    def test_unmatched_api_still_404(self, spa_client):
        client, _ = spa_client
        assert client.get("/api/no-such-route").status_code == 404

    def test_dist_missing_not_mounted(self, tmp_path):
        app = FastAPI()
        assert mount_spa(app, tmp_path / "no-dist") is False


class TestRealDistWhenBuilt:
    """真实 frontend/dist 存在时（本机已构建），顺带验证主 app 的挂载效果。"""

    @pytest.fixture()
    def client(self):
        from main import DIST_DIR
        if not DIST_DIR.is_dir():
            pytest.skip("frontend/dist 不存在（未构建）")
        from main import app
        return TestClient(app)

    def test_traversal_on_real_app(self, client):
        index_html = client.get("/").content
        resp = client.get("/..%5c..%5c.env")
        assert resp.status_code == 200
        assert resp.content == index_html
