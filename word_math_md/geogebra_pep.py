"""Map GeoGebra 人教配套册 pages to gaokao knowledge-point codes."""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any

BOOK_ID = "dyetmjzr"
BOOK_API = f"https://api.geogebra.org/v1.0/books/{BOOK_ID}"
BOOK_JSON = Path(__file__).resolve().parent / "geogebra_pep_book.json"

# chapter title -> [(title regex, knowledge codes)]
# A trailing r".*" rule is the chapter fallback.
CHAPTER_RULES: dict[str, list[tuple[str, list[str]]]] = {
    "集合与常用逻辑用语": [
        (r"交集|并集|运算", ["1.3"]),
        (r"包含|数集", ["1.2"]),
        (r"属于|识别", ["1.1"]),
        (r".*", ["1.1", "1.2"]),
    ],
    "一元二次函数、方程和不等式": [
        (r"赵爽|基本不等式", ["2.2"]),
        (r"最值|二次|八边形", ["2.3"]),
        (r".*", ["2.2", "2.3"]),
    ],
    "函数的概念与性质": [
        (r"幂函数", ["3.3"]),
        (r"单调|奇|偶|最大|最小|周期|变换|三次|折叠|面积", ["3.2"]),
        (r".*", ["3.1", "3.2"]),
    ],
    "指数函数与对数函数": [
        (r"零点|二分法|实数解", ["4.5", "19.2"]),
        (r"无理数指数|指数幂", ["4.1"]),
        (r"幂函数", ["3.3", "19.1"]),
        (r"对数", ["4.4"]),
        (r"指数", ["4.2"]),
        (r".*", ["4.2", "4.4"]),
    ],
    "三角函数": [
        (r"任意角|正角|负角|弧度|象限", ["5.1"]),
        (r"诱导", ["5.3"]),
        (r"定义|三角函数线|任意角的三角", ["5.2"]),
        (r"图像|图象|周期|变换|正弦函数", ["5.4", "5.6"]),
        (r"射影|扇形|应用", ["5.7"]),
        (r".*", ["5.2", "5.4"]),
    ],
    "平面向量及其应用": [
        (r"正弦|余弦|物理|曲柄", ["6.4"]),
        (r"基本定理|三点共线|奔驰|距离", ["6.3"]),
        (r"加减|加法|减法|数乘|数量积|投影", ["6.2"]),
        (r".*", ["6.1", "6.2"]),
    ],
    "复数": [
        (r".*", ["7.1"]),
    ],
    "立体几何初步": [
        (r"祖暅|体积|球的体积", ["8.3"]),
        (r"平行", ["8.5"]),
        (r"垂直|折纸", ["8.6"]),
        (r"棱柱|棱锥|折叠|外接球", ["8.1", "8.4"]),
        (r".*", ["8.4"]),
    ],
    "统计": [
        (r"直方图|估计", ["9.2"]),
        (r"抽样|随机数|转盘", ["9.1"]),
        (r".*", ["9.1", "9.2"]),
    ],
    "概率": [
        (r".*", ["10.1"]),
    ],
    "空间向量与立体几何": [
        (r".*", ["11.4"]),
    ],
    "直线和圆的方程": [
        (r"截距|直线的", ["12.2"]),
        (r"点到直线|距离", ["12.3"]),
        (r"圆", ["12.4", "12.5"]),
        (r".*", ["12.2", "12.3"]),
    ],
    "圆锥曲线的方程": [
        (r"二分法|零点", ["4.5", "19.2"]),
        (r"椭圆", ["13.1"]),
        (r"双曲线", ["13.2"]),
        (r"抛物线", ["13.3"]),
        (r".*", ["13.4"]),
    ],
    "数列": [
        (r".*", ["14.1"]),
    ],
    "一元函数的导数及其应用": [
        (r".*", ["15.3", "15.4"]),
    ],
}

CHAPTER_REVIEW: dict[str, list[str]] = {
    "集合与常用逻辑用语": ["25"],
    "一元二次函数、方程和不等式": ["25"],
    "函数的概念与性质": ["19.1"],
    "指数函数与对数函数": ["19.1"],
    "三角函数": ["23"],
    "平面向量及其应用": ["26"],
    "立体几何初步": ["21.1"],
    "统计": ["22.1"],
    "概率": ["22.1"],
    "空间向量与立体几何": ["21.1", "21.2"],
    "直线和圆的方程": ["20.1"],
    "圆锥曲线的方程": ["20.2"],
    "数列": ["24"],
    "一元函数的导数及其应用": ["19.2"],
}

CHAPTER_PREFIX: dict[str, tuple[str, ...]] = {
    "集合与常用逻辑用语": ("1.",),
    "一元二次函数、方程和不等式": ("2.",),
    "函数的概念与性质": ("3.",),
    "指数函数与对数函数": ("4.",),
    "三角函数": ("5.",),
    "平面向量及其应用": ("6.",),
    "复数": ("7.",),
    "立体几何初步": ("8.",),
    "统计": ("9.",),
    "概率": ("10.",),
    "空间向量与立体几何": ("11.",),
    "直线和圆的方程": ("12.",),
    "圆锥曲线的方程": ("13.",),
    "数列": ("14.",),
    "一元函数的导数及其应用": ("15.",),
}


def material_id_from_thumb(thumb: str) -> str:
    if "/resource/" not in (thumb or ""):
        return ""
    return thumb.split("/resource/", 1)[1].split("/", 1)[0]


def embed_url(material_id: str, width: int = 1280, height: int = 720) -> str:
    mid = (material_id or "").strip()
    if not mid:
        return ""
    w = max(320, int(width or 1280))
    h = max(240, int(height or 720))
    return (
        f"https://www.geogebra.org/material/iframe/id/{mid}"
        f"/width/{w}/height/{h}/border/ffffff"
        f"/sfsb/true/sdz/true/szb/true/sri/true/ctl/true"
        f"?embed=1"
    )


def view_url(page_id: str) -> str:
    pid = (page_id or "").strip()
    if not pid:
        return ""
    return f"https://www.geogebra.org/m/{pid}"


def _unique(codes: list[str]) -> list[str]:
    out: list[str] = []
    for code in codes:
        if code and code not in out:
            out.append(code)
    return out


def infer_knowledge_codes(chapter_title: str, page_title: str) -> list[str]:
    chapter = (chapter_title or "").strip()
    title = (page_title or "").strip()
    rules = CHAPTER_RULES.get(chapter)
    if not rules:
        for key, item in CHAPTER_RULES.items():
            if key in chapter or chapter in key:
                rules = item
                chapter = key
                break
    if not rules:
        return []
    matched: list[str] = []
    fallback: list[str] = []
    for pattern, codes in rules:
        if pattern == ".*":
            fallback = list(codes)
            continue
        if title and re.search(pattern, title):
            matched.extend(codes)
    if not matched:
        matched = list(fallback)
    prefixes = CHAPTER_PREFIX.get(chapter, ())
    if prefixes and any(code.startswith(prefixes) for code in matched):
        matched.extend(CHAPTER_REVIEW.get(chapter, []))
    elif not prefixes:
        matched.extend(CHAPTER_REVIEW.get(chapter, []))
    return _unique(matched)


def fetch_book() -> dict[str, Any]:
    req = urllib.request.Request(
        BOOK_API,
        headers={"User-Agent": "word-math-md/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return normalize_book(data)


def normalize_book(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("chapters") and isinstance(data["chapters"][0], dict):
        first = data["chapters"][0]
        if "pages" in first and first.get("pages") and "page_id" in (first["pages"][0] or {}):
            return data
    chapters = []
    for ch in data.get("chapters") or []:
        pages = []
        for page in ch.get("pages") or []:
            thumb = page.get("thumbUrl") or page.get("thumb_url") or ""
            page_id = page.get("id") or page.get("page_id") or ""
            pages.append(
                {
                    "page_id": page_id,
                    "material_id": page.get("material_id")
                    or material_id_from_thumb(thumb)
                    or page_id,
                    "title": page.get("title") or "",
                    "thumb_url": thumb,
                    "chapter_id": str(ch.get("id") or ""),
                    "chapter_title": ch.get("title") or "",
                }
            )
        chapters.append(
            {
                "id": str(ch.get("id") or ""),
                "title": ch.get("title") or "",
                "pages": pages,
            }
        )
    return {
        "book_id": data.get("id") or data.get("book_id") or BOOK_ID,
        "title": data.get("title") or "",
        "chapters": chapters,
        "page_count": sum(len(ch["pages"]) for ch in chapters),
    }


def load_book(*, live: bool = False) -> dict[str, Any]:
    if live:
        return fetch_book()
    if BOOK_JSON.exists():
        return normalize_book(json.loads(BOOK_JSON.read_text(encoding="utf-8")))
    return fetch_book()


def mapped_rows(*, live: bool = False) -> list[dict[str, Any]]:
    book = load_book(live=live)
    book_id = book.get("book_id") or BOOK_ID
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    order = 0
    for chapter in book.get("chapters") or []:
        chapter_title = chapter.get("title") or ""
        chapter_id = str(chapter.get("id") or "")
        for page in chapter.get("pages") or []:
            order += 1
            page_id = page.get("page_id") or ""
            material_id = page.get("material_id") or page_id
            title = page.get("title") or ""
            codes = infer_knowledge_codes(chapter_title, title)
            for code in codes:
                key = (code, page_id)
                if not page_id or key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "knowledge_code": code,
                        "book_id": book_id,
                        "page_id": page_id,
                        "material_id": material_id,
                        "title": title.strip(),
                        "chapter_title": chapter_title,
                        "chapter_id": chapter_id,
                        "thumb_url": page.get("thumb_url") or "",
                        "sort_order": order,
                    }
                )
    return rows


def serialize_animation(row: dict[str, Any], codes: list[str] | None = None) -> dict[str, Any]:
    material_id = row.get("material_id") or row.get("page_id") or ""
    page_id = row.get("page_id") or ""
    item = {
        "knowledge_code": row.get("knowledge_code") or "",
        "book_id": row.get("book_id") or BOOK_ID,
        "page_id": page_id,
        "material_id": material_id,
        "title": row.get("title") or "",
        "chapter_title": row.get("chapter_title") or "",
        "chapter_id": row.get("chapter_id") or "",
        "thumb_url": row.get("thumb_url") or "",
        "sort_order": row.get("sort_order") or 0,
        "embed_url": embed_url(material_id),
        "view_url": view_url(page_id),
    }
    if codes is not None:
        item["knowledge_codes"] = codes
    return item
