"""Turn stored answer markdown into KaTeX HTML for the grading report."""

from __future__ import annotations

import html
import json
import tempfile
from pathlib import Path

from word_math_md.gaokao_docx_convert import _run_tsx

ROOT = Path(__file__).resolve().parent.parent
RENDER_SCRIPT = ROOT / "gaokao_docx" / "render-answers.mts"


def render_answer_html_batch(texts: list[str]) -> list[str]:
    """Render each answer. Falls back to escaped text if KaTeX is unavailable."""
    if not texts:
        return []
    try:
        return _render_with_katex(texts)
    except Exception:
        return [_fallback_html(text) for text in texts]


def attach_answer_html(report: dict) -> None:
    items = report.get("items") or []
    texts = [str(item.get("expected_answer") or "") for item in items]
    rendered = render_answer_html_batch(texts)
    for item, fragment in zip(items, rendered):
        item["expected_answer_html"] = fragment


def _render_with_katex(texts: list[str]) -> list[str]:
    if not RENDER_SCRIPT.is_file():
        raise RuntimeError("缺少公式渲染脚本")
    with tempfile.TemporaryDirectory(prefix="answer-html-") as tmp:
        folder = Path(tmp)
        src = folder / "in.json"
        dest = folder / "out.json"
        src.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
        _run_tsx(RENDER_SCRIPT, str(src), str(dest), timeout=60)
        data = json.loads(dest.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != len(texts):
        raise RuntimeError("公式渲染结果数量不一致")
    return [str(item) for item in data]


def _fallback_html(text: str) -> str:
    parts = [part.strip() for part in html.unescape(text or "").split("##")]
    parts = [part for part in parts if part]
    if not parts:
        return ""
    return ' <span class="ans-or">或</span> '.join(html.escape(part) for part in parts)
