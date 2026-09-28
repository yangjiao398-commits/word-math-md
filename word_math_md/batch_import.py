"""Batch-import 解析版 Word papers through the standard conversion pipeline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from word_math_md.core.cleaner import preprocess_docx
from word_math_md.exam_bank import import_markdown_file
from word_math_md.gaokao_docx_convert import convert_docx_like_gaokao
from word_math_md.ole_to_latex import convert_ole_docx

_SKIP_OUTPUT = re.compile(r"\.(?:ole-latex|preprocessed)(?:\.|$)", re.I)
_PARSED_EDITION = re.compile(r"解析版")


def is_parsed_edition_docx(filename: str) -> bool:
    """True for original 解析版 .docx files, not OLE/preprocess intermediates."""
    name = Path(filename or "").name
    if not name or name.startswith("~$"):
        return False
    if not name.lower().endswith(".docx"):
        return False
    if not _PARSED_EDITION.search(name):
        return False
    if _SKIP_OUTPUT.search(name):
        return False
    return True


def title_from_parsed_docx(filename: str) -> str:
    stem = Path(filename or "").stem.strip() or "试卷"
    cut = re.split(r"[（(]解析版[）)]", stem, maxsplit=1)[0].strip(" -_·")
    return cut or stem


def import_docx_pipeline(
    src: Path,
    *,
    work_dir: Path,
    province: str | None = None,
    gaokao_paper: str | None = None,
    title: str | None = None,
    paper_code: str | None = None,
) -> dict[str, Any]:
    """OLE→preprocess→Markdown→exam bank, in that order."""
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(f"找不到 Word 文件：{src}")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    ole_out = work_dir / f"{src.stem}.ole-latex.docx"
    try:
        formulas = convert_ole_docx(src, ole_out)
    except Exception as exc:
        raise RuntimeError(f"OLE公式转Latex失败: {exc}") from exc

    prep_out = work_dir / f"{src.stem}.ole-latex.preprocessed.docx"
    try:
        prep_stats = preprocess_docx(ole_out, prep_out)
    except Exception as exc:
        raise RuntimeError(f"格式预处理失败: {exc}") from exc

    md_out = work_dir / f"{src.stem}.md"
    try:
        convert_meta = convert_docx_like_gaokao(prep_out, md_out)
    except Exception as exc:
        raise RuntimeError(f"word转换md失败: {exc}") from exc

    paper_title = (title or "").strip() or title_from_parsed_docx(src.name)
    try:
        imported = import_markdown_file(
            md_out,
            paper_code=paper_code,
            title=paper_title,
            province=province,
            gaokao_paper=gaokao_paper,
        )
    except Exception as exc:
        raise RuntimeError(f"导入题库失败: {exc}") from exc

    return {
        **imported,
        "file_name": src.name,
        "ole_formulas": len(formulas or []),
        "preprocess": prep_stats,
        "math_converted": int((convert_meta or {}).get("mathConverted") or 0),
        "image_count": int((convert_meta or {}).get("imageCount") or 0),
        "convert_warnings": list((convert_meta or {}).get("warnings") or []),
        "steps": ["ole-to-latex", "preprocess", "convert-md", "import-bank"],
    }
