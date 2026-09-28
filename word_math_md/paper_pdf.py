"""Render an exam paper (stems only) to PDF for the mobile app share flow."""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from word_math_md.app_api import app_public_origin, rewrite_html_assets

_IMG_TAG = re.compile(r"<img\b([^>]*)>", re.I)
_UNSAFE_FILE = re.compile(r'[\\/:*?"<>|]+')

_BROWSER_CANDIDATES = [
    os.environ.get("CHROME_PATH") or "",
    os.environ.get("EDGE_PATH") or "",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge",
    "msedge",
    "chrome",
    "google-chrome",
    "chromium",
]


def pdf_filename(title: str) -> str:
    raw = _UNSAFE_FILE.sub("_", (title or "试卷").strip()) or "试卷"
    if not raw.lower().endswith(".pdf"):
        raw = f"{raw}.pdf"
    return raw


def _esc(text: Any) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def _eager_images(markup: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        attrs = match.group(1) or ""
        attrs = re.sub(r"\sloading\s*=\s*(['\"][^'\"]*['\"])", "", attrs, flags=re.I)
        attrs = re.sub(r"\sdecoding\s*=\s*(['\"][^'\"]*['\"])", "", attrs, flags=re.I)
        return f'<img loading="eager" decoding="sync"{attrs}>'

    return _IMG_TAG.sub(_repl, markup or "")


_TYPE_SECTION_FALLBACK = (
    ("single_choice", "一、单项选择题"),
    ("multi_choice", "二、多项选择题"),
    ("fill_blank", "三、填空题"),
    ("solution", "四、解答题"),
)


def _group_questions(data: dict[str, Any]) -> list[dict[str, Any]]:
    questions = list(data.get("questions") or [])
    by_no: dict[str, dict[str, Any]] = {}
    for i, raw in enumerate(questions):
        q = raw if isinstance(raw, dict) else {}
        by_no[str(q.get("index") if q.get("index") is not None else i + 1)] = {
            "q": q,
            "i": i,
        }
    used: set[int] = set()
    groups: list[dict[str, Any]] = []
    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        items = []
        for number in section.get("questionIndexes") or []:
            hit = by_no.get(str(number))
            if not hit or hit["i"] in used:
                continue
            used.add(hit["i"])
            items.append(hit)
        if not items:
            continue
        groups.append(
            {
                "title": str(section.get("title") or ""),
                "titleHtml": str(section.get("titleHtml") or ""),
                "items": items,
            }
        )
    rest = [
        {"q": raw if isinstance(raw, dict) else {}, "i": i}
        for i, raw in enumerate(questions)
        if i not in used
    ]
    if not rest:
        return groups
    if groups:
        groups.append({"title": "", "titleHtml": "", "items": rest})
        return groups
    buckets: dict[str, list[dict[str, Any]]] = {}
    for hit in rest:
        code = str(hit["q"].get("type_code") or "")
        buckets.setdefault(code, []).append(hit)
    for code, title in _TYPE_SECTION_FALLBACK:
        items = buckets.pop(code, None)
        if items:
            groups.append({"title": title, "titleHtml": "", "items": items})
    for code, items in buckets.items():
        label = dict(_TYPE_SECTION_FALLBACK).get(code, "")
        groups.append({"title": label, "titleHtml": "", "items": items})
    return groups


def _question_card(q: dict[str, Any], fallback_index: int) -> str:
    index = q.get("index") if q.get("index") is not None else fallback_index
    stem = _eager_images(rewrite_html_assets(str(q.get("stemHtml") or "")))
    score = q.get("score")
    try:
        score_n = float(score)
        score_txt = str(int(score_n)) if score_n == int(score_n) else str(score_n)
        qno = f"{_esc(index)}.（{_esc(score_txt)}分）"
    except (TypeError, ValueError):
        qno = f"{_esc(index)}."
    return (
        f'<article class="q-card"><div class="q-no">{qno}</div>'
        f'<div class="rich-content">{stem}</div></article>'
    )


def paper_stem_html(data: dict[str, Any]) -> str:
    paper = data.get("paper") or {}
    questions = data.get("questions") or []
    title = paper.get("title") or paper.get("paper_code") or "试卷"
    meta_bits = " · ".join(
        part
        for part in (
            paper.get("province") or "",
            paper.get("gaokao_paper") or "",
            paper.get("semester") or "",
            paper.get("exam_type") or "",
        )
        if part
    )
    heading = _esc(title)
    if meta_bits:
        heading += f" · {_esc(meta_bits)}"
    heading += f" · 共 {len(questions)} 题"
    css = f"{app_public_origin()}/vendor/katex/katex.min.css"
    parts: list[str] = []
    groups = _group_questions(data)
    if not groups and not questions:
        parts.append("<p>未能解析出题目。</p>")
    for group in groups:
        heading_html = str(group.get("titleHtml") or "").strip()
        title_text = str(group.get("title") or "").strip()
        block = ['<section class="paper-section">']
        if heading_html:
            block.append(
                f'<div class="paper-section-title">{_eager_images(rewrite_html_assets(heading_html))}</div>'
            )
        elif title_text:
            block.append(f'<div class="paper-section-title">{_esc(title_text)}</div>')
        for hit in group.get("items") or []:
            q = hit.get("q") if isinstance(hit, dict) else {}
            i = hit.get("i") if isinstance(hit, dict) else 0
            if not isinstance(q, dict):
                q = {}
            block.append(_question_card(q, int(i or 0) + 1))
        block.append("</section>")
        parts.append("\n".join(block))
    body = "\n".join(parts) or "<p>未能解析出题目。</p>"
    header = str(data.get("headerHtml") or "").strip()
    masthead = (
        f'<div class="paper-masthead">{_eager_images(rewrite_html_assets(header))}</div>'
        if header
        else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>{_esc(title)}</title>
<link rel="stylesheet" href="{css}"/>
<style>
  @page {{ size: A4; margin: 14mm 12mm; }}
  html, body {{ margin: 0; background: #fff; color: #111; }}
  body {{
    font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", "PingFang SC", serif;
    font-size: 15px;
    line-height: 1.7;
  }}
  h1 {{ font-size: 20px; font-weight: 650; margin: 0 0 6px; }}
  .meta {{ color: #444; font-size: 12px; margin: 0 0 16px; }}
  .paper-masthead {{
    text-align: center;
    margin: 0 0 16px;
    line-height: 1.85;
    font-size: 15px;
  }}
  .paper-masthead p {{ margin: 0.2em 0; }}
  .paper-masthead img {{ max-width: 100%; max-height: 48px; height: auto; }}
  .paper-section {{ margin: 0 0 16px; }}
  .paper-section-title {{
    font-weight: 700;
    margin: 0 0 10px;
    line-height: 1.7;
  }}
  .paper-section-title p {{ margin: 0.15em 0; }}
  .q-card {{ break-inside: avoid; margin: 0 0 14px; }}
  .q-no {{ font-weight: 650; margin-bottom: 4px; }}
  .rich-content .katex {{ font-size: 1.05em; }}
  .rich-content .katex-display {{ margin: 8px 0; }}
  .rich-content img {{ max-width: 100%; height: auto; }}
  .rich-content table, .md-table-wrap table {{
    border-collapse: collapse;
    width: 100%;
    margin: 8px 0;
  }}
  .rich-content th, .rich-content td {{
    border: 1px solid #333;
    padding: 4px 8px;
    text-align: center;
  }}
  .rich-content table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
  .rich-content th, .rich-content td {{
    border: 1px solid #333; padding: 4px 8px; text-align: center;
  }}
  .md-table-wrap {{ overflow-x: auto; }}
</style>
</head>
<body>
<h1>{_esc(title)}</h1>
<p class="meta">{heading}</p>
{masthead}
{body}
</body>
</html>
"""


def _browser_paths() -> list[str]:
    out: list[str] = []
    for raw in _BROWSER_CANDIDATES:
        name = (raw or "").strip()
        if not name or name in out:
            continue
        if os.path.sep in name or (os.name == "nt" and ":\\" in name):
            if Path(name).is_file():
                out.append(name)
            continue
        found = shutil.which(name)
        if found:
            out.append(found)
    return out


def _run_chrome_pdf(browser: str, html_path: Path, pdf_path: Path) -> None:
    uri = html_path.resolve().as_uri()
    flags = [
        ["--headless=new"],
        ["--headless"],
    ]
    extra = [
        "--disable-gpu",
        "--allow-running-insecure-content",
        "--no-first-run",
        "--no-pdf-header-footer",
        "--virtual-time-budget=12000",
        f"--print-to-pdf={pdf_path}",
        uri,
    ]
    kwargs: dict[str, Any] = {
        "check": False,
        "timeout": 60,
        "capture_output": True,
        "text": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    last_err = ""
    for headless in flags:
        if pdf_path.exists():
            pdf_path.unlink()
        proc = subprocess.run([browser, *headless, *extra], **kwargs)
        if pdf_path.exists() and pdf_path.stat().st_size > 100:
            return
        last_err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
    raise RuntimeError(last_err or "浏览器未能写出 PDF")


def html_to_pdf_bytes(document: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="paper-pdf-") as tmp:
        root = Path(tmp)
        html_path = root / "paper.html"
        pdf_path = root / "paper.pdf"
        html_path.write_text(document, encoding="utf-8")
        errors: list[str] = []
        for browser in _browser_paths():
            try:
                _run_chrome_pdf(browser, html_path, pdf_path)
                return pdf_path.read_bytes()
            except Exception as exc:
                errors.append(f"{browser}: {exc}")
        try:
            from weasyprint import HTML  # type: ignore

            return HTML(string=document, base_url=app_public_origin()).write_pdf()
        except Exception as exc:
            errors.append(f"weasyprint: {exc}")
        raise RuntimeError("无法生成 PDF。" + "；".join(errors[:4]))
