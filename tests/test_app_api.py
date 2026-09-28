from word_math_md.app_api import (
    app_runtime_config,
    decode_token,
    issue_token,
    rewrite_asset_url,
    rewrite_html_assets,
    rewrite_preview_payload,
    send_sms_code,
    verify_sms_code,
)


def test_rewrite_supabase_image_to_cdn(monkeypatch):
    monkeypatch.setenv("APP_CDN_BASE", "https://cdn.math-agent.cn")
    monkeypatch.setenv("APP_PUBLIC_ORIGIN", "http://127.0.0.1:3010")
    url = "https://demo.supabase.co/storage/v1/object/public/exam-assets/p1/q.png"
    assert rewrite_asset_url(url) == "https://cdn.math-agent.cn/exam/exam-assets/p1/q.png"
    assert rewrite_asset_url("/files/job/a.png") == "https://cdn.math-agent.cn/files/job/a.png"
    assert rewrite_asset_url("data:image/png;base64,aaa").startswith("data:")


def test_rewrite_html_keeps_katex_and_swaps_img(monkeypatch):
    monkeypatch.setenv("APP_CDN_BASE", "https://cdn.math-agent.cn")
    html = '<div class="katex">x</div><img src="/files/job/fig.png">'
    out = rewrite_html_assets(html)
    assert 'class="katex"' in out
    assert 'src="https://cdn.math-agent.cn/files/job/fig.png"' in out


def test_rewrite_preview_payload_rewrites_header_images(monkeypatch):
    monkeypatch.setenv("APP_CDN_BASE", "https://cdn.math-agent.cn")
    out = rewrite_preview_payload(
        {
            "headerHtml": '<p>卷头</p><img src="/files/job/logo.png">',
            "sections": [
                {"title": "一、选择题", "titleHtml": '<p>一、选择题</p><img src="/files/job/sec.png">'}
            ],
            "questions": [{"stemHtml": '<img src="/files/job/q.png">'}],
        }
    )
    assert "卷头" in out["headerHtml"]
    assert 'src="https://cdn.math-agent.cn/files/job/logo.png"' in out["headerHtml"]
    assert 'src="https://cdn.math-agent.cn/files/job/sec.png"' in out["sections"][0]["titleHtml"]
    assert 'src="https://cdn.math-agent.cn/files/job/q.png"' in out["questions"][0]["stemHtml"]


def test_jwt_roundtrip():
    token = issue_token({"id": "11111111-1111-1111-1111-111111111111", "phone": "13900000000"})
    payload = decode_token(token)
    assert payload["phone"] == "13900000000"


def test_dev_sms_code():
    send_sms_code("13900001111")
    verify_sms_code("13900001111", "888888")


def test_exam_bank_delete_paper_api(monkeypatch):
    from fastapi.testclient import TestClient

    from word_math_md import server

    paper_id = "11111111-1111-1111-1111-111111111111"
    monkeypatch.setattr(server, "exam_bank_configured", lambda: True)
    monkeypatch.setattr(
        server,
        "delete_paper",
        lambda pid: {
            "paper_id": pid,
            "paper_code": "demo",
            "title": "测试卷",
            "question_count": 2,
            "asset_count": 0,
        },
    )
    res = TestClient(server.app).delete(f"/api/exam-bank/papers/{paper_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["paper_id"] == paper_id
    assert data["question_count"] == 2


def test_app_runtime_config_katex_matches_preview():
    cfg = app_runtime_config()
    assert cfg["katex"]["version"] == "0.18.4"
    assert cfg["katex"]["css_url"].endswith("/vendor/katex/katex.min.css")
    assert cfg["push"]["ios"] == "apns"
    assert "huawei" in cfg["push"]["android_vendors"]
    assert cfg["pay"]["mock"] is True
    assert cfg["pay"]["channels"] == ["wechat", "alipay"]
    assert "广东" in cfg["papers"]["provinces"]
    assert cfg["papers"]["gaokao_papers"] == ["全国A卷", "全国B卷"]
