from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from word_math_md.app_pay import (
    alipay_sign_params,
    alipay_verify_params,
    mock_token,
    next_expires,
    order_id_from_trade_no,
    plan_by_code,
    trade_no_from_order_id,
    verify_mock_token,
)


def test_plan_by_code():
    plan = plan_by_code("monthly")
    assert plan["price_fen"] == 3900
    assert plan["days"] == 31


def test_trade_no_roundtrip():
    oid = "11111111-2222-3333-4444-555555555555"
    trade = trade_no_from_order_id(oid)
    assert len(trade) == 32
    assert order_id_from_trade_no(trade) == oid


def test_next_expires_extends_active_membership():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    current = (now + timedelta(days=10)).isoformat()
    nxt = next_expires(current, 31, now=now)
    assert nxt.date().isoformat() == "2026-02-11"


def test_mock_token_roundtrip():
    oid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    token = mock_token(oid)
    verify_mock_token(oid, token)


def test_alipay_sign_and_verify(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("ALIPAY_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("ALIPAY_PUBLIC_KEY", public_pem)
    params = {"app_id": "2024", "biz_content": "{\"x\":1}", "method": "alipay.trade.precreate"}
    params["sign"] = alipay_sign_params(params)
    assert alipay_verify_params(params)


def test_runtime_pay_is_mock_by_default():
    from word_math_md.app_api import app_runtime_config

    cfg = app_runtime_config()
    assert cfg["pay"]["mock"] is True
    assert "wechat" in cfg["pay"]["channels"]
    assert "alipay" in cfg["pay"]["channels"]
    assert cfg["pay"]["wechat_ready"] is True
    assert cfg["pay"]["alipay_ready"] is True
