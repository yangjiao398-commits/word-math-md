"""Public API for math-agent-app (paid Flutter client).

Admin / conversion endpoints stay on the existing exam-bank routes.
These /api/app/* handlers are the only surface the mobile app should call.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv

from word_math_md.exam_bank import list_papers, paper_filter_options
from word_math_md.legal_terms import legal_public_config, validate_registration_consent

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.I)
_SMS_CODES: dict[str, tuple[str, float]] = {}


def app_public_origin() -> str:
    return (os.environ.get("APP_PUBLIC_ORIGIN") or "http://127.0.0.1:3010").rstrip("/")


def app_cdn_base() -> str:
    return (os.environ.get("APP_CDN_BASE") or "").rstrip("/")


def app_jwt_secret() -> str:
    return os.environ.get("APP_JWT_SECRET") or "dev-math-agent-change-me"


def katex_asset_url(path: str) -> str:
    return f"{app_public_origin()}/vendor/katex/{path.lstrip('/')}"


def app_runtime_config() -> dict[str, Any]:
    from word_math_md.app_pay import pay_public_config

    cdn = app_cdn_base()
    origin = app_public_origin()
    return {
        "ok": True,
        "api_origin": origin,
        "cdn_base": cdn,
        "katex": {
            "version": "0.18.4",
            "css_url": katex_asset_url("katex.min.css"),
            "js_url": katex_asset_url("katex.min.js"),
            "font_base": katex_asset_url("fonts/"),
        },
        "pay": pay_public_config(),
        "push": {
            "ios": "apns",
            "android": os.environ.get("APP_ANDROID_PUSH") or "getui",
            "android_vendors": ["huawei", "xiaomi", "oppo", "vivo"],
        },
        "sms_provider": os.environ.get("APP_SMS_PROVIDER") or "dev",
        "trial_days": int(os.environ.get("APP_TRIAL_DAYS") or "7"),
        "legal": legal_public_config(),
        "papers": paper_filter_options(),
    }


def rewrite_asset_url(url: str) -> str:
    """Send paper images through the domestic OSS/CDN host when configured."""
    raw = (url or "").strip()
    if not raw or raw.startswith("data:") or raw.startswith("blob:"):
        return raw
    cdn = app_cdn_base()
    origin = app_public_origin()
    if raw.startswith("//"):
        raw = "https:" + raw
    if raw.startswith("/"):
        raw = origin + raw
    if not cdn:
        return raw
    parsed = urlparse(raw)
    path = parsed.path or ""
    if "/storage/v1/object/public/" in path:
        path = path.split("/storage/v1/object/public/", 1)[-1]
        path = path.lstrip("/")
        return f"{cdn}/exam/{path}"
    if path.startswith("/files/") or path.startswith("/vendor/") or path.startswith("/static/"):
        return f"{cdn}{path}"
    if parsed.netloc and parsed.netloc in {urlparse(origin).netloc, "127.0.0.1:3010", "localhost:3010"}:
        return f"{cdn}{path}"
    return raw


def rewrite_html_assets(html: str) -> str:
    if not html:
        return html

    def _sub(match: re.Match[str]) -> str:
        return f"{match.group(1)}{rewrite_asset_url(match.group(2))}{match.group(3)}"

    return IMG_SRC_RE.sub(_sub, html)


def rewrite_preview_payload(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    for q in out.get("questions") or []:
        for key in ("stemHtml", "answerHtml", "analysisHtml", "detailHtml"):
            if q.get(key):
                q[key] = rewrite_html_assets(q[key])
    return out


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def issue_token(user: dict[str, Any], *, hours: int = 24 * 14) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    now = int(time.time())
    payload = {
        "sub": user["id"],
        "phone": user.get("phone") or "",
        "iat": now,
        "exp": now + hours * 3600,
    }
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    msg = f"{header}.{body}".encode()
    sig = _b64url(hmac.new(app_jwt_secret().encode(), msg, hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


def decode_token(token: str) -> dict[str, Any]:
    parts = (token or "").split(".")
    if len(parts) != 3:
        raise ValueError("无效登录态")
    header, body, sig = parts
    msg = f"{header}.{body}".encode()
    expect = _b64url(hmac.new(app_jwt_secret().encode(), msg, hashlib.sha256).digest())
    if not hmac.compare_digest(expect, sig):
        raise ValueError("登录态校验失败")
    pad = "=" * (-len(body) % 4)
    payload = json.loads(base64.urlsafe_b64decode(body + pad))
    if int(payload.get("exp") or 0) < int(time.time()):
        raise ValueError("登录已过期")
    return payload


def send_sms_code(phone: str) -> dict[str, Any]:
    if not PHONE_RE.match(phone):
        raise ValueError("请输入正确的大陆手机号")
    provider = (os.environ.get("APP_SMS_PROVIDER") or "dev").strip().lower()
    code = "888888" if provider == "dev" else f"{secrets.randbelow(1000000):06d}"
    _SMS_CODES[phone] = (code, time.time() + 300)
    if provider == "dev":
        return {"ok": True, "dev_code": code, "ttl": 300}
    # Production: wire Aliyun Dysms or Tencent SMS here using APP_SMS_PROVIDER.
    raise ValueError(f"短信通道 {provider} 尚未配置。开发环境请设 APP_SMS_PROVIDER=dev")


def verify_sms_code(phone: str, code: str) -> None:
    if not PHONE_RE.match(phone):
        raise ValueError("请输入正确的大陆手机号")
    packed = _SMS_CODES.get(phone)
    if not packed:
        raise ValueError("请先获取验证码")
    expect, exp = packed
    if time.time() > exp:
        _SMS_CODES.pop(phone, None)
        raise ValueError("验证码已过期")
    if not hmac.compare_digest(str(expect), str(code).strip()):
        raise ValueError("验证码不正确")
    _SMS_CODES.pop(phone, None)


def _client():
    from word_math_md.exam_bank import _client as exam_client

    return exam_client()


def upsert_user_by_phone(phone: str, *, consent: dict[str, Any] | None = None) -> dict[str, Any]:
    client = _client()
    found = (
        client.table("app_users")
        .select("id,phone,nickname,created_at,extra")
        .eq("phone", phone)
        .limit(1)
        .execute()
    )
    extra_update = {}
    if consent:
        extra_update = {
            "age_group": consent.get("age_group"),
            "consent": {
                **consent,
                "accepted_at": datetime.now(timezone.utc).isoformat(),
            },
        }
    if found.data:
        user = found.data[0]
        if extra_update:
            extra = dict(user.get("extra") or {})
            extra.update(extra_update)
            client.table("app_users").update(
                {"extra": extra, "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", user["id"]).execute()
            user["extra"] = extra
        return user
    trial_days = int(os.environ.get("APP_TRIAL_DAYS") or "7")
    inserted = (
        client.table("app_users")
        .insert(
            {
                "phone": phone,
                "nickname": f"学员{phone[-4:]}",
                "extra": extra_update or {},
            }
        )
        .execute()
    )
    user = (inserted.data or [{}])[0]
    if user.get("id") and trial_days > 0:
        expires = (datetime.now(timezone.utc) + timedelta(days=trial_days)).isoformat()
        client.table("app_memberships").insert(
            {
                "user_id": user["id"],
                "plan": "trial",
                "status": "active",
                "expires_at": expires,
            }
        ).execute()
    return user


def get_membership(user_id: str) -> dict[str, Any]:
    client = _client()
    res = (
        client.table("app_memberships")
        .select("plan,status,expires_at")
        .eq("user_id", user_id)
        .order("expires_at", desc=True)
        .limit(1)
        .execute()
    )
    row = (res.data or [None])[0] or {}
    expires = row.get("expires_at")
    active = False
    if row.get("status") == "active" and expires:
        try:
            exp = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            active = exp > datetime.now(timezone.utc)
        except ValueError:
            active = False
    return {
        "plan": row.get("plan") or "",
        "status": "active" if active else (row.get("status") or "none"),
        "expires_at": expires,
        "entitled": active,
    }


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    member = get_membership(user["id"]) if user.get("id") else {"entitled": False}
    return {
        "id": user.get("id"),
        "phone": user.get("phone"),
        "nickname": user.get("nickname") or "",
        "membership": member,
    }


def login_with_sms(
    phone: str,
    code: str,
    *,
    age_group: str = "",
    accept_minor_terms: bool = False,
    accept_ip_terms: bool = False,
    guardian_consent: bool = False,
    terms_version: str = "",
) -> dict[str, Any]:
    consent = validate_registration_consent(
        age_group=age_group,
        accept_minor_terms=accept_minor_terms,
        accept_ip_terms=accept_ip_terms,
        guardian_consent=guardian_consent,
        terms_version=terms_version,
    )
    verify_sms_code(phone, code)
    user = upsert_user_by_phone(phone, consent=consent)
    token = issue_token(user)
    return {"ok": True, "token": token, "user": public_user(user)}


def load_user(user_id: str) -> dict[str, Any]:
    if not UUID_RE.match(user_id or ""):
        raise ValueError("无效用户")
    client = _client()
    res = (
        client.table("app_users")
        .select("id,phone,nickname,created_at")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not res.data:
        raise ValueError("用户不存在")
    return res.data


def register_device(user_id: str, body: dict[str, Any]) -> dict[str, Any]:
    platform = (body.get("platform") or "").strip().lower()
    if platform not in {"ios", "android"}:
        raise ValueError("platform 必须是 ios 或 android")
    token = (body.get("push_token") or "").strip()
    if not token:
        raise ValueError("缺少 push_token")
    vendor = (body.get("vendor") or "").strip().lower()
    if platform == "ios":
        vendor = vendor or "apns"
    else:
        vendor = vendor or (os.environ.get("APP_ANDROID_PUSH") or "getui")
    allowed = {"apns", "getui", "jpush", "huawei", "xiaomi", "oppo", "vivo"}
    if vendor not in allowed:
        raise ValueError("不支持的推送通道")
    client = _client()
    row = {
        "user_id": user_id,
        "platform": platform,
        "vendor": vendor,
        "push_token": token[:512],
        "extra": {
            "brand": body.get("brand") or "",
            "app_version": body.get("app_version") or "",
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    existing = (
        client.table("app_devices")
        .select("id")
        .eq("user_id", user_id)
        .eq("push_token", token)
        .limit(1)
        .execute()
    )
    if existing.data:
        client.table("app_devices").update(row).eq("id", existing.data[0]["id"]).execute()
        row["id"] = existing.data[0]["id"]
    else:
        inserted = client.table("app_devices").insert(row).execute()
        row = (inserted.data or [row])[0]
    return {"ok": True, "device": row}


def slim_papers(
    *,
    province: str | None = None,
    gaokao_paper: str | None = None,
) -> list[dict[str, Any]]:
    rows = list_papers(limit=80, province=province, gaokao_paper=gaokao_paper)
    out = []
    for p in rows:
        out.append(
            {
                "id": p.get("id"),
                "paper_code": p.get("paper_code"),
                "title": p.get("title"),
                "semester": p.get("semester") or "",
                "exam_type": p.get("exam_type") or "",
                "province": p.get("province") or "",
                "gaokao_paper": p.get("gaokao_paper") or "",
                "question_count": p.get("question_count") or 0,
            }
        )
    return out


def require_entitled(user: dict[str, Any]) -> None:
    member = get_membership(user["id"])
    if not member.get("entitled"):
        raise PermissionError("需要有效会员才能使用该内容")
