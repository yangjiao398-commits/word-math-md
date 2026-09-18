"""WeChat Pay + Alipay for math-agent-app membership.

APP_PAY_PROVIDER=dev (default) simulates checkout so the local app can be tested.
APP_PAY_PROVIDER=live uses merchant credentials from the environment.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from word_math_md.app_api import app_jwt_secret, app_public_origin, get_membership

PLANS: list[dict[str, Any]] = [
    {"code": "monthly", "title": "月卡", "price_fen": 3900, "days": 31},
    {"code": "term", "title": "学期卡", "price_fen": 9900, "days": 150},
    {"code": "yearly", "title": "年卡", "price_fen": 16900, "days": 366},
]

CHANNELS = ("wechat", "alipay")
SCENES = ("qr", "h5", "wap", "app", "page")


def pay_provider() -> str:
    raw = (os.environ.get("APP_PAY_PROVIDER") or "dev").strip().lower()
    return "live" if raw == "live" else "dev"


def plan_by_code(code: str) -> dict[str, Any]:
    for plan in PLANS:
        if plan["code"] == code:
            return plan
    raise ValueError("请选择有效的会员套餐")


def wechat_configured() -> bool:
    return all(
        [
            (os.environ.get("WECHAT_PAY_APPID") or "").strip(),
            (os.environ.get("WECHAT_PAY_MCHID") or "").strip(),
            (os.environ.get("WECHAT_PAY_SERIAL") or "").strip(),
            (os.environ.get("WECHAT_PAY_API_V3_KEY") or "").strip(),
            (os.environ.get("WECHAT_PAY_PRIVATE_KEY") or "").strip(),
        ]
    )


def alipay_configured() -> bool:
    return all(
        [
            (os.environ.get("ALIPAY_APP_ID") or "").strip(),
            (os.environ.get("ALIPAY_PRIVATE_KEY") or "").strip(),
            (os.environ.get("ALIPAY_PUBLIC_KEY") or "").strip(),
        ]
    )


def pay_public_config() -> dict[str, Any]:
    provider = pay_provider()
    return {
        "plans": PLANS,
        "channels": list(CHANNELS),
        "provider": provider,
        "wechat_ready": provider == "dev" or wechat_configured(),
        "alipay_ready": provider == "dev" or alipay_configured(),
        "mock": provider == "dev",
    }


def next_expires(existing_iso: str | None, days: int, *, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    start = now
    if existing_iso:
        try:
            exp = datetime.fromisoformat(str(existing_iso).replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp > start:
                start = exp
        except ValueError:
            pass
    return start + timedelta(days=int(days))


def trade_no_from_order_id(order_id: str) -> str:
    return str(order_id).replace("-", "")


def order_id_from_trade_no(trade_no: str) -> str:
    raw = "".join(ch for ch in (trade_no or "") if ch.isalnum())
    if len(raw) != 32:
        raise ValueError("无效的商户订单号")
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def _client():
    from word_math_md.app_api import _client as exam_client

    return exam_client()


def _env_pem(name: str) -> bytes:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        raise ValueError(f"缺少 {name}")
    if raw.endswith(".pem") and Path(raw).is_file():
        raw = Path(raw).read_text(encoding="utf-8")
    raw = raw.replace("\\n", "\n").strip()
    if "BEGIN" not in raw:
        kind = "PUBLIC" if "PUBLIC" in name.upper() or name.endswith("PUBLIC_KEY") else "PRIVATE"
        body = "".join(raw.split())
        wrapped = "\n".join(body[i : i + 64] for i in range(0, len(body), 64))
        raw = f"-----BEGIN {kind} KEY-----\n{wrapped}\n-----END {kind} KEY-----"
    return raw.encode("utf-8")


def _rsa_private_sign(message: bytes, pem_env: str) -> bytes:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = serialization.load_pem_private_key(_env_pem(pem_env), password=None)
    return key.sign(message, padding.PKCS1v15(), hashes.SHA256())


def _rsa_public_verify(message: bytes, signature: bytes, pem_env: str) -> bool:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    try:
        key = serialization.load_pem_public_key(_env_pem(pem_env))
        key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:
        return False


def mock_token(order_id: str, *, ttl: int = 1800) -> str:
    exp = int(time.time()) + ttl
    body = f"{order_id}.{exp}"
    sig = hmac.new(app_jwt_secret().encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{exp}.{sig}"


def verify_mock_token(order_id: str, token: str) -> None:
    parts = (token or "").split(".", 1)
    if len(parts) != 2:
        raise ValueError("模拟支付链接无效")
    exp_s, sig = parts
    try:
        exp = int(exp_s)
    except ValueError as exc:
        raise ValueError("模拟支付链接无效") from exc
    if exp < int(time.time()):
        raise ValueError("模拟支付链接已过期")
    body = f"{order_id}.{exp}"
    expect = hmac.new(app_jwt_secret().encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expect, sig):
        raise ValueError("模拟支付链接校验失败")


def load_order(order_id: str) -> dict[str, Any]:
    res = (
        _client()
        .table("app_orders")
        .select("id,user_id,plan,amount_fen,channel,status,extra,created_at,paid_at")
        .eq("id", order_id)
        .limit(1)
        .execute()
    )
    row = (res.data or [None])[0]
    if not row:
        raise ValueError("订单不存在")
    return row


def _get_order(order_id: str) -> dict[str, Any]:
    return load_order(order_id)


def public_order(row: dict[str, Any]) -> dict[str, Any]:
    extra = row.get("extra") or {}
    if not isinstance(extra, dict):
        extra = {}
    return {
        "id": row.get("id"),
        "plan": row.get("plan"),
        "amount_fen": row.get("amount_fen") or 0,
        "channel": row.get("channel"),
        "status": row.get("status"),
        "paid_at": row.get("paid_at"),
        "created_at": row.get("created_at"),
        "pay": extra.get("pay") or {},
    }


def fulfill_order(order_id: str, *, transaction_id: str = "") -> dict[str, Any]:
    row = _get_order(order_id)
    if row.get("status") == "paid":
        return public_order(row)
    if row.get("status") not in {"created", "pending"}:
        raise ValueError("订单已关闭，无法支付")
    plan = plan_by_code(str(row.get("plan") or ""))
    member = get_membership(str(row["user_id"]))
    expires = next_expires(member.get("expires_at") if member.get("entitled") else None, plan["days"])
    now = datetime.now(timezone.utc)
    extra = dict(row.get("extra") or {})
    extra["transaction_id"] = transaction_id
    client = _client()
    client.table("app_memberships").insert(
        {
            "user_id": row["user_id"],
            "plan": plan["code"],
            "status": "active",
            "expires_at": expires.isoformat(),
            "extra": {"order_id": order_id, "channel": row.get("channel") or ""},
        }
    ).execute()
    updated = (
        client.table("app_orders")
        .update({"status": "paid", "paid_at": now.isoformat(), "extra": extra})
        .eq("id", order_id)
        .eq("status", row.get("status"))
        .execute()
    )
    if not updated.data:
        return public_order(_get_order(order_id))
    return public_order({**row, "status": "paid", "paid_at": now.isoformat(), "extra": extra})


def create_order(
    user_id: str,
    plan_code: str,
    channel: str,
    scene: str,
    *,
    client_ip: str = "127.0.0.1",
) -> dict[str, Any]:
    plan = plan_by_code(plan_code)
    channel = (channel or "").strip().lower()
    scene = (scene or "qr").strip().lower()
    if channel not in CHANNELS:
        raise ValueError("请选择微信支付或支付宝")
    if scene not in SCENES:
        scene = "qr"
    client = _client()
    inserted = (
        client.table("app_orders")
        .insert(
            {
                "user_id": user_id,
                "plan": plan["code"],
                "amount_fen": plan["price_fen"],
                "channel": channel,
                "status": "pending",
                "extra": {"scene": scene},
            }
        )
        .execute()
    )
    row = (inserted.data or [None])[0]
    if not row or not row.get("id"):
        raise RuntimeError("创建订单失败")
    pay = _build_pay(row, plan, channel, scene, client_ip=client_ip)
    extra = dict(row.get("extra") or {})
    extra.update(
        {
            "out_trade_no": trade_no_from_order_id(row["id"]),
            "scene": scene,
            "pay": {k: v for k, v in pay.items() if k != "form_html"},
        }
    )
    client.table("app_orders").update({"extra": extra}).eq("id", row["id"]).execute()
    row["extra"] = extra
    out = public_order(row)
    out["pay"] = pay
    return out


def _build_pay(
    row: dict[str, Any],
    plan: dict[str, Any],
    channel: str,
    scene: str,
    *,
    client_ip: str,
) -> dict[str, Any]:
    if pay_provider() == "dev":
        return _mock_pay(row, channel)
    if channel == "wechat":
        if not wechat_configured():
            raise ValueError("尚未配置微信支付商户号（WECHAT_PAY_*）")
        return _wechat_pay(row, plan, scene, client_ip=client_ip)
    if not alipay_configured():
        raise ValueError("尚未配置支付宝应用（ALIPAY_*）")
    return _alipay_pay(row, plan, scene)


def _mock_pay(row: dict[str, Any], channel: str) -> dict[str, Any]:
    order_id = row["id"]
    token = mock_token(order_id)
    origin = app_public_origin()
    url = f"{origin}/api/app/pay/mock/{order_id}?token={urllib.parse.quote(token)}"
    return {
        "type": "mock",
        "channel": channel,
        "mock": True,
        "pay_url": url,
        "instruction": "开发环境：确认支付后立即开通会员。云上请配置微信/支付宝商户号。",
    }


def mock_page_html(order_id: str, token: str) -> str:
    row = _get_order(order_id)
    plan = plan_by_code(str(row.get("plan") or ""))
    yuan = f"{(row.get('amount_fen') or 0) / 100:.2f}"
    channel = "微信支付" if row.get("channel") == "wechat" else "支付宝"
    action = f"/api/app/pay/mock/{xml_escape(order_id)}?token={xml_escape(token)}"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>确认支付</title>
<style>
  body {{ font-family: sans-serif; background:#f6f3ec; color:#1c2430; max-width:420px; margin:40px auto; padding:0 16px; }}
  .card {{ background:#fff; border-radius:12px; padding:20px; }}
  button {{ width:100%; padding:12px; border:0; border-radius:8px; background:#1f6feb; color:#fff; font-size:16px; }}
</style></head>
<body>
<div class="card">
  <h1>数理助理会员</h1>
  <p>{xml_escape(plan['title'])} · {xml_escape(channel)}</p>
  <p>金额 <strong>¥{xml_escape(yuan)}</strong></p>
  <p style="color:#5c6b7a;font-size:13px">当前为开发模拟支付。配置商户号后将跳转微信/支付宝。</p>
  <form method="post" action="{action}"><button type="submit">确认支付</button></form>
</div>
</body></html>
"""


def mock_result_html(ok: bool, message: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>支付结果</title></head>
<body style="font-family:sans-serif;padding:32px">
<h1>{"支付成功" if ok else "支付未完成"}</h1>
<p>{xml_escape(message)}</p>
<p>请返回 App 查看会员状态。</p>
</body></html>
"""


def wechat_notify_url() -> str:
    return (os.environ.get("WECHAT_PAY_NOTIFY_URL") or f"{app_public_origin()}/api/app/pay/wechat/notify").rstrip("/")


def alipay_notify_url() -> str:
    return (os.environ.get("ALIPAY_NOTIFY_URL") or f"{app_public_origin()}/api/app/pay/alipay/notify").rstrip("/")


def _wechat_v3(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = "" if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    message = f"{method}\n{path}\n{ts}\n{nonce}\n{payload}\n"
    signature = base64.b64encode(_rsa_private_sign(message.encode("utf-8"), "WECHAT_PAY_PRIVATE_KEY")).decode("ascii")
    mchid = os.environ["WECHAT_PAY_MCHID"].strip()
    serial = os.environ["WECHAT_PAY_SERIAL"].strip()
    auth = (
        f'WECHATPAY2-SHA256-RSA2048 mchid="{mchid}",nonce_str="{nonce}",'
        f'signature="{signature}",timestamp="{ts}",serial_no="{serial}"'
    )
    req = urllib.request.Request(
        f"https://api.mch.weixin.qq.com{path}",
        data=payload.encode("utf-8") if payload else None,
        method=method,
        headers={
            "Authorization": auth,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "math-agent-app",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise ValueError(f"微信支付下单失败：{detail or exc}") from exc


def _wechat_app_params(prepay_id: str) -> dict[str, str]:
    appid = os.environ["WECHAT_PAY_APPID"].strip()
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    package = "Sign=WXPay"
    message = f"{appid}\n{ts}\n{nonce}\nprepay_id={prepay_id}\n"
    pay_sign = base64.b64encode(
        _rsa_private_sign(message.encode("utf-8"), "WECHAT_PAY_PRIVATE_KEY")
    ).decode("ascii")
    return {
        "appid": appid,
        "partnerid": os.environ["WECHAT_PAY_MCHID"].strip(),
        "prepayid": prepay_id,
        "package": package,
        "noncestr": nonce,
        "timestamp": ts,
        "sign": pay_sign,
    }


def _wechat_pay(row: dict[str, Any], plan: dict[str, Any], scene: str, *, client_ip: str) -> dict[str, Any]:
    trade_no = trade_no_from_order_id(row["id"])
    base = {
        "appid": os.environ["WECHAT_PAY_APPID"].strip(),
        "mchid": os.environ["WECHAT_PAY_MCHID"].strip(),
        "description": f"数理助理{plan['title']}",
        "out_trade_no": trade_no,
        "notify_url": wechat_notify_url(),
        "amount": {"total": int(plan["price_fen"]), "currency": "CNY"},
    }
    if scene == "app":
        data = _wechat_v3("POST", "/v3/pay/transactions/app", base)
        prepay_id = str(data.get("prepay_id") or "")
        if not prepay_id:
            raise ValueError("微信 APP 支付未返回 prepay_id")
        return {"type": "app", "channel": "wechat", "app_params": _wechat_app_params(prepay_id)}
    if scene == "h5":
        body = dict(base)
        body["scene_info"] = {
            "payer_client_ip": client_ip or "127.0.0.1",
            "h5_info": {"type": "Wap", "app_name": "数理助理", "app_url": app_public_origin()},
        }
        data = _wechat_v3("POST", "/v3/pay/transactions/h5", body)
        h5_url = str(data.get("h5_url") or "")
        if not h5_url:
            raise ValueError("微信 H5 支付未返回 h5_url")
        return {"type": "h5", "channel": "wechat", "pay_url": h5_url}
    data = _wechat_v3("POST", "/v3/pay/transactions/native", base)
    code_url = str(data.get("code_url") or "")
    if not code_url:
        raise ValueError("微信扫码支付未返回 code_url")
    return {
        "type": "qr",
        "channel": "wechat",
        "qr_code": code_url,
        "instruction": "请使用微信扫一扫完成支付",
    }


def decrypt_wechat_resource(resource: dict[str, Any]) -> dict[str, Any]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = (os.environ.get("WECHAT_PAY_API_V3_KEY") or "").encode("utf-8")
    if len(key) != 32:
        raise ValueError("WECHAT_PAY_API_V3_KEY 必须是 32 字节")
    nonce = str(resource.get("nonce") or "").encode("utf-8")
    aad = str(resource.get("associated_data") or "").encode("utf-8")
    ciphertext = base64.b64decode(str(resource.get("ciphertext") or ""))
    pt = AESGCM(key).decrypt(nonce, ciphertext, aad)
    return json.loads(pt.decode("utf-8"))


def handle_wechat_notify(body: dict[str, Any]) -> dict[str, Any]:
    resource = body.get("resource") or {}
    if not isinstance(resource, dict):
        raise ValueError("回调数据无效")
    event = decrypt_wechat_resource(resource)
    if str(event.get("trade_state") or "") != "SUCCESS":
        return {"code": "SUCCESS", "message": "忽略未成功支付"}
    order_id = order_id_from_trade_no(str(event.get("out_trade_no") or ""))
    row = _get_order(order_id)
    total = ((event.get("amount") or {}) if isinstance(event.get("amount"), dict) else {}).get("total")
    if total is not None and int(total) != int(row.get("amount_fen") or 0):
        raise ValueError("支付金额与订单不符")
    fulfill_order(order_id, transaction_id=str(event.get("transaction_id") or ""))
    return {"code": "SUCCESS", "message": "成功"}


def _alipay_gateway() -> str:
    return (
        os.environ.get("ALIPAY_GATEWAY") or "https://openapi.alipay.com/gateway.do"
    ).rstrip("/")


def alipay_sign_params(params: dict[str, str]) -> str:
    items = [f"{k}={params[k]}" for k in sorted(params) if k != "sign" and params[k] is not None]
    unsigned = "&".join(items)
    return base64.b64encode(_rsa_private_sign(unsigned.encode("utf-8"), "ALIPAY_PRIVATE_KEY")).decode("ascii")


def alipay_verify_params(params: dict[str, str]) -> bool:
    sign = str(params.get("sign") or "")
    items = [f"{k}={params[k]}" for k in sorted(params) if k not in {"sign", "sign_type"} and params[k] is not None]
    unsigned = "&".join(items)
    try:
        signature = base64.b64decode(sign)
    except Exception:
        return False
    return _rsa_public_verify(unsigned.encode("utf-8"), signature, "ALIPAY_PUBLIC_KEY")


def _alipay_common(method: str, biz: dict[str, Any]) -> dict[str, str]:
    params = {
        "app_id": os.environ["ALIPAY_APP_ID"].strip(),
        "method": method,
        "format": "JSON",
        "charset": "utf-8",
        "sign_type": "RSA2",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0",
        "notify_url": alipay_notify_url(),
        "biz_content": json.dumps(biz, ensure_ascii=False, separators=(",", ":")),
    }
    return_url = (os.environ.get("ALIPAY_RETURN_URL") or "").strip()
    if return_url:
        params["return_url"] = return_url
    params["sign"] = alipay_sign_params(params)
    return params


def _alipay_pay(row: dict[str, Any], plan: dict[str, Any], scene: str) -> dict[str, Any]:
    trade_no = trade_no_from_order_id(row["id"])
    amount = f"{int(plan['price_fen']) / 100:.2f}"
    subject = f"数理助理{plan['title']}"
    if scene == "app":
        biz = {
            "out_trade_no": trade_no,
            "total_amount": amount,
            "subject": subject,
            "product_code": "QUICK_MSECURITY_PAY",
        }
        params = _alipay_common("alipay.trade.app.pay", biz)
        order_str = urllib.parse.urlencode(params)
        return {"type": "app", "channel": "alipay", "order_str": order_str}
    if scene in {"h5", "wap"}:
        biz = {
            "out_trade_no": trade_no,
            "total_amount": amount,
            "subject": subject,
            "product_code": "QUICK_WAP_WAY",
            "quit_url": app_public_origin(),
        }
        params = _alipay_common("alipay.trade.wap.pay", biz)
        pay_url = f"{_alipay_gateway()}?{urllib.parse.urlencode(params)}"
        return {"type": "wap", "channel": "alipay", "pay_url": pay_url}
    if scene == "page":
        biz = {
            "out_trade_no": trade_no,
            "total_amount": amount,
            "subject": subject,
            "product_code": "FAST_INSTANT_TRADE_PAY",
        }
        params = _alipay_common("alipay.trade.page.pay", biz)
        pay_url = f"{_alipay_gateway()}?{urllib.parse.urlencode(params)}"
        return {"type": "page", "channel": "alipay", "pay_url": pay_url}
    biz = {
        "out_trade_no": trade_no,
        "total_amount": amount,
        "subject": subject,
    }
    params = _alipay_common("alipay.trade.precreate", biz)
    req = urllib.request.Request(
        _alipay_gateway(),
        data=urllib.parse.urlencode(params).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    inner = data.get("alipay_trade_precreate_response") or {}
    if str(inner.get("code") or "") != "10000":
        raise ValueError(f"支付宝下单失败：{inner.get('sub_msg') or inner.get('msg') or inner}")
    qr_code = str(inner.get("qr_code") or "")
    if not qr_code:
        raise ValueError("支付宝未返回收款码")
    return {
        "type": "qr",
        "channel": "alipay",
        "qr_code": qr_code,
        "instruction": "请使用支付宝扫一扫完成支付",
    }


def handle_alipay_notify(params: dict[str, str]) -> str:
    if not alipay_verify_params(params):
        return "fail"
    if str(params.get("trade_status") or "") not in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
        return "success"
    order_id = order_id_from_trade_no(str(params.get("out_trade_no") or ""))
    row = _get_order(order_id)
    paid = params.get("total_amount")
    if paid is not None:
        expect = f"{int(row.get('amount_fen') or 0) / 100:.2f}"
        if str(paid) != expect:
            return "fail"
    fulfill_order(order_id, transaction_id=str(params.get("trade_no") or ""))
    return "success"
