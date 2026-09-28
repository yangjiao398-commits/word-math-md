"""Upload and list PPT courseware for knowledge points (Supabase Storage + PG)."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from word_math_md.exam_bank import BUCKET, _client, _ensure_bucket, public_asset_url

TABLE = "knowledge_point_courseware"
MAX_BYTES = 80 * 1024 * 1024
ALLOWED_SUFFIX = {".ppt", ".pptx"}
MIME_BY_SUFFIX = {
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _storage_folder(code: str) -> str:
    safe = hashlib.sha1(code.encode("utf-8")).hexdigest()[:16]
    return f"knowledge-ppt/{safe}"


def _normalize_code(code: str) -> str:
    code = (code or "").strip()
    if not code:
        raise ValueError("无效的知识点编号。")
    return code


def _guess_mime(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    return MIME_BY_SUFFIX.get(ext, "application/octet-stream")


def _safe_filename(name: str) -> str:
    base = Path(name or "courseware.pptx").name
    base = re.sub(r'[\\/:*?"<>|]+', "_", base).strip() or "courseware.pptx"
    ext = Path(base).suffix.lower()
    if ext not in ALLOWED_SUFFIX:
        raise ValueError("仅支持 .ppt 或 .pptx 课件。")
    return base


def serialize_courseware(row: dict[str, Any]) -> dict[str, Any]:
    key = str(row.get("storage_key") or "")
    url = public_asset_url(key) if key else ""
    office_view = ""
    if url:
        office_view = (
            "https://view.officeapps.live.com/op/embed.aspx?src="
            + quote(url, safe="")
        )
    return {
        "id": row.get("id"),
        "knowledge_code": row.get("knowledge_code"),
        "title": row.get("title") or row.get("filename") or "",
        "filename": row.get("filename") or "",
        "mime_type": row.get("mime_type") or "",
        "byte_size": int(row.get("byte_size") or 0),
        "sort_order": int(row.get("sort_order") or 0),
        "public_url": url,
        "office_view_url": office_view,
        "created_at": row.get("created_at"),
    }


def list_courseware(code: str) -> list[dict[str, Any]]:
    code = _normalize_code(code)
    client = _client()
    res = (
        client.table(TABLE)
        .select("*")
        .eq("knowledge_code", code)
        .order("sort_order")
        .order("created_at")
        .execute()
    )
    return [serialize_courseware(row) for row in (res.data or [])]


def list_courseware_for_codes(codes: list[str]) -> dict[str, list[dict[str, Any]]]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        code = (raw or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        cleaned.append(code)
    if not cleaned:
        return {}
    client = _client()
    res = (
        client.table(TABLE)
        .select("*")
        .in_("knowledge_code", cleaned)
        .order("sort_order")
        .order("created_at")
        .execute()
    )
    out: dict[str, list[dict[str, Any]]] = {code: [] for code in cleaned}
    for row in res.data or []:
        code = row.get("knowledge_code")
        if code in out:
            out[code].append(serialize_courseware(row))
    return out


def upload_courseware(
    code: str,
    filename: str,
    data: bytes,
    *,
    title: str = "",
) -> dict[str, Any]:
    code = _normalize_code(code)
    if not data:
        raise ValueError("课件文件为空。")
    if len(data) > MAX_BYTES:
        raise ValueError("课件不能超过 80 MB。")
    safe_name = _safe_filename(filename)
    mime = _guess_mime(safe_name)
    client = _client()
    exists = (
        client.table("knowledge_points")
        .select("code")
        .eq("code", code)
        .limit(1)
        .execute()
    )
    if not exists.data:
        raise ValueError(f"知识点 {code} 不存在，请先维护编号。")
    _ensure_bucket(client)
    folder = _storage_folder(code)
    # Storage keys must be ASCII. The original Chinese filename stays in the table.
    key = f"{folder}/{uuid.uuid4().hex[:16]}{Path(safe_name).suffix.lower()}"
    client.storage.from_(BUCKET).upload(
        key,
        data,
        {"content-type": mime, "upsert": "false"},
    )
    display = (title or "").strip() or Path(safe_name).stem
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "knowledge_code": code,
        "title": display,
        "filename": safe_name,
        "storage_key": key,
        "mime_type": mime,
        "byte_size": len(data),
        "sort_order": 0,
        "updated_at": now,
    }
    inserted = client.table(TABLE).insert(row).execute()
    saved = (inserted.data or [row])[0]
    return serialize_courseware(saved)


def delete_courseware(item_id: str) -> None:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", item_id or ""):
        raise ValueError("无效的课件 id")
    client = _client()
    res = client.table(TABLE).select("storage_key").eq("id", item_id).limit(1).execute()
    if not res.data:
        raise ValueError("课件不存在")
    key = res.data[0].get("storage_key")
    client.table(TABLE).delete().eq("id", item_id).execute()
    if key:
        try:
            client.storage.from_(BUCKET).remove([key])
        except Exception:
            pass
