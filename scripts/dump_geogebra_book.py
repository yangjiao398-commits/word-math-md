"""Dump GeoGebra PEP companion book chapters and page IDs (UTF-8)."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

BOOK_ID = "dyetmjzr"
URL = f"https://api.geogebra.org/v1.0/books/{BOOK_ID}"
OUT = Path(__file__).resolve().parent.parent / "word_math_md" / "geogebra_pep_book.json"


def material_id_from_thumb(thumb: str) -> str:
    if "/resource/" not in (thumb or ""):
        return ""
    return thumb.split("/resource/", 1)[1].split("/", 1)[0]


def fetch_book() -> dict:
    req = urllib.request.Request(
        URL,
        headers={"User-Agent": "word-math-md/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    data = fetch_book()
    chapters = []
    pages = []
    for ch in data.get("chapters") or []:
        chapter = {
            "id": str(ch.get("id") or ""),
            "title": ch.get("title") or "",
            "pages": [],
        }
        for page in ch.get("pages") or []:
            thumb = page.get("thumbUrl") or ""
            item = {
                "page_id": page.get("id") or "",
                "material_id": material_id_from_thumb(thumb) or (page.get("id") or ""),
                "title": page.get("title") or "",
                "thumb_url": thumb,
                "chapter_id": chapter["id"],
                "chapter_title": chapter["title"],
            }
            chapter["pages"].append(item)
            pages.append(item)
        chapters.append(chapter)
    payload = {
        "book_id": data.get("id") or BOOK_ID,
        "title": data.get("title") or "",
        "chapters": chapters,
        "page_count": len(pages),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} pages={len(pages)} chapters={len(chapters)}")
    for ch in chapters:
        print(f"\n## {ch['title']}")
        for p in ch["pages"]:
            print(f"  {p['page_id']}\t{p['material_id']}\t{p['title']}")


if __name__ == "__main__":
    main()
