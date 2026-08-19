# -*- coding: utf-8 -*-
"""SPA 静态托管安全：路径穿越必须回退 index.html，绝不能读到 dist 之外的文件。"""
import pytest

from main import DIST_DIR

pytestmark = pytest.mark.skipif(not DIST_DIR.is_dir(), reason="frontend/dist 不存在（未构建）")


class TestSpaFallback:
    def test_root_serves_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_path_traversal_falls_back_to_index(self, client):
        """编码的 ..\\ 穿越请求：回退 index.html，不回 .env 内容。"""
        index_html = (DIST_DIR / "index.html").read_bytes()
        for path in ("/..%5c..%5c.env", "/%2e%2e/%2e%2e/.env", "/..%5c..%5cREADME.md"):
            resp = client.get(path)
            assert resp.status_code == 200
            assert resp.content == index_html, f"路径穿越未被拦截：{path}"
