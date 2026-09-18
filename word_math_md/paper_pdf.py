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
    cards = []
    for i, raw in enumerate(questions):
        q = raw if isinstance(raw, dict) else {}
        index = q.get("index") if q.get("index") is not None else i + 1
        stem = _eager_images(rewrite_html_assets(str(q.get("stemHtml") or "")))
        cards.append(
            f'<article class="q-card"><div class="q-no">{_esc(index)}.</div>'
            f'<div class="rich-content">{stem}</div></article>'
        )
    body = "\n".join(cards) or "<p>未能解析出题目。</p>"
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
  .q-card {{ break-inside: avoid; margin: 0 0 14px; }}
  .q-no {{ font-weight: 650; margin-bottom: 4px; }}
  .rich-content .katex {{ font-size: 1.05em; }}
  .rich-content .katex-display {{ margin: 8px 0; }}
  .rich-content img {{ max-width: 100%; height: auto; }}
</style>
</head>
<body>
<h1>{_esc(title)}</h1>
<p class="meta">{heading}</p>
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
