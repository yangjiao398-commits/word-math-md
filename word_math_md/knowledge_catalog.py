"""Maintain the high-school math knowledge-point dictionary (knowledge_points)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from word_math_md.exam_bank import (
    ParsedKnowledge,
    exam_bank_configured,
    list_knowledge_points,
    upsert_knowledge_points,
    _client,
)

CODE_RE = re.compile(r"^[^\s]{1,40}$")
LINE_RE = re.compile(r"^(?P<code>\S+)(?:\s+|[:：]\s*)(?P<desc>.+)$")


def normalize_code(code: str) -> str:
    return (code or "").strip()


def parse_catalog_text(text: str) -> list[ParsedKnowledge]:
    """Parse bulk input. One knowledge point per line: `1.1 集合的含义`."""
    seen: set[str] = set()
    out: list[ParsedKnowledge] = []
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for part in re.split(r"[；;]+", line):
            item = part.strip()
            if not item:
                continue
            match = LINE_RE.match(item)
            if match:
                code = normalize_code(match.group("code"))
                desc = (match.group("desc") or "").strip()
            else:
                code = normalize_code(item)
                desc = ""
            if not code or code in seen or not CODE_RE.match(code):
                continue
            seen.add(code)
            out.append(ParsedKnowledge(code=code, description=desc))
    return out


def list_catalog(limit: int = 2000) -> list[dict[str, Any]]:
    rows = list_knowledge_points(limit=limit)
    client = _client()
    links = (
        client.table("question_knowledge_points")
        .select("knowledge_code")
        .execute()
    )
    counts: dict[str, int] = {}
    for row in links.data or []:
        code = row.get("knowledge_code")
        if code:
            counts[code] = counts.get(code, 0) + 1
    anim_counts: dict[str, int] = {}
    try:
        anims = (
            client.table("knowledge_geogebra_animations")
            .select("knowledge_code")
            .execute()
        )
        for row in anims.data or []:
            code = row.get("knowledge_code")
            if code:
                anim_counts[code] = anim_counts.get(code, 0) + 1
    except Exception:
        anim_counts = {}
    for row in rows:
        row["question_count"] = counts.get(row["code"], 0)
        row["animation_count"] = anim_counts.get(row["code"], 0)
    return rows


def _display_description(major_category: str, minor_category: str, description: str = "") -> str:
    minor = (minor_category or "").strip()
    major = (major_category or "").strip()
    desc = (description or "").strip()
    return desc or minor or major


def create_catalog_item(
    code: str,
    description: str = "",
    sort_order: int = 0,
    semester: str = "",
    major_category: str = "",
    minor_category: str = "",
) -> dict[str, Any]:
    code = normalize_code(code)
    semester = (semester or "").strip()
    major_category = (major_category or "").strip()
    minor_category = (minor_category or "").strip()
    description = _display_description(major_category, minor_category, description)
    if not CODE_RE.match(code):
        raise ValueError("编号不能为空，且不能含空格（最长 40 字）。")
    if not description:
        raise ValueError("请填写知识点小类或文字描述。")
    client = _client()
    existing = (
        client.table("knowledge_points")
        .select("code")
        .eq("code", code)
        .limit(1)
        .execute()
    )
    if existing.data:
        raise ValueError(f"编号 {code} 已存在。")
    row = {
        "code": code,
        "description": description,
        "semester": semester,
        "major_category": major_category,
        "minor_category": minor_category,
        "sort_order": int(sort_order or 0),
    }
    client.table("knowledge_points").insert(row).execute()
    return row


def update_catalog_item(
    code: str,
    description: str = "",
    sort_order: int | None = None,
    semester: str | None = None,
    major_category: str | None = None,
    minor_category: str | None = None,
) -> dict[str, Any]:
    code = normalize_code(code)
    if not CODE_RE.match(code):
        raise ValueError("无效的知识点编号。")
    client = _client()
    existing = (
        client.table("knowledge_points")
        .select("code,description,semester,major_category,minor_category")
        .eq("code", code)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise ValueError("知识点不存在。")
    current = existing.data[0]
    if semester is not None:
        current["semester"] = semester.strip()
    if major_category is not None:
        current["major_category"] = major_category.strip()
    if minor_category is not None:
        current["minor_category"] = minor_category.strip()
    desc = _display_description(
        current.get("major_category") or "",
        current.get("minor_category") or "",
        description,
    )
    if not desc:
        raise ValueError("请填写知识点小类或文字描述。")
    payload: dict[str, Any] = {
        "description": desc,
        "semester": current.get("semester") or "",
        "major_category": current.get("major_category") or "",
        "minor_category": current.get("minor_category") or "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if sort_order is not None:
        payload["sort_order"] = int(sort_order)
    client.table("knowledge_points").update(payload).eq("code", code).execute()
    payload["code"] = code
    return payload


def delete_catalog_item(code: str) -> None:
    code = normalize_code(code)
    if not code:
        raise ValueError("无效的知识点编号。")
    client = _client()
    used = (
        client.table("question_knowledge_points")
        .select("question_id", count="exact")
        .eq("knowledge_code", code)
        .execute()
    )
    n = used.count if used.count is not None else len(used.data or [])
    if n:
        raise ValueError(f"仍有 {n} 道题引用该知识点，不能删除。")
    client.table("knowledge_points").delete().eq("code", code).execute()


def bulk_upsert_catalog(text: str) -> dict[str, Any]:
    items = parse_catalog_text(text)
    if not items:
        raise ValueError("没有识别到知识点。每行写成：编号 文字描述")
    client = _client()
    existing = (
        client.table("knowledge_points")
        .select("code")
        .in_("code", [item.code for item in items])
        .execute()
    )
    have = {row["code"] for row in (existing.data or [])}
    upsert_knowledge_points(client, items)
    inserted = sum(1 for item in items if item.code not in have)
    return {
        "total": len(items),
        "inserted": inserted,
        "updated": len(items) - inserted,
    }


def seed_gaokao_catalog() -> dict[str, Any]:
    from word_math_md.gaokao_knowledge_data import GAOKAO_KNOWLEDGE_POINTS

    client = _client()
    existing = (
        client.table("knowledge_points")
        .select("code")
        .in_("code", [row[0] for row in GAOKAO_KNOWLEDGE_POINTS])
        .execute()
    )
    have = {row["code"] for row in (existing.data or [])}
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for i, (code, semester, major, minor) in enumerate(GAOKAO_KNOWLEDGE_POINTS, start=1):
        rows.append(
            {
                "code": code,
                "description": _display_description(major, minor),
                "semester": semester,
                "major_category": major,
                "minor_category": minor,
                "sort_order": i,
                "updated_at": now,
            }
        )
    for start in range(0, len(rows), 40):
        client.table("knowledge_points").upsert(
            rows[start : start + 40], on_conflict="code"
        ).execute()
    inserted = sum(1 for row in rows if row["code"] not in have)
    return {
        "total": len(rows),
        "inserted": inserted,
        "updated": len(rows) - inserted,
    }


def catalog_ready() -> bool:
    return exam_bank_configured()
