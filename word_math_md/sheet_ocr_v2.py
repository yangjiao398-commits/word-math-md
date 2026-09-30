"""Answer-sheet grading reader: PaddleOCR layout and text, pix2tex for formulas.

Layout detection splits each photo into text blocks and formula blocks.
PaddleOCR reads Chinese, question numbers, and ordinary text.
pix2tex (LaTeX-OCR) reads only the formula crops and returns LaTeX.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from word_math_md.sheet_grade import parse_answers_in_order
from word_math_md.sheet_ocr import prepare_image

_LAYOUT = None
_TEXT = None
_FORMULA = None
_LAYOUT_FAILED = False
_TEXT_FAILED = False
_FORMULA_FAILED = False

FORMULA_LABELS = {"formula", "equation", "display_formula", "inline_formula"}
SKIP_LABELS = {"footer", "seal", "chart", "image", "figure", "header_image"}


def layout_model_name() -> str:
    name = (os.environ.get("LAYOUT_MODEL") or "PP-DocLayout-M").strip()
    return name or "PP-DocLayout-M"


def module_installed(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def ocr_v2_configured() -> dict[str, Any]:
    return {
        "layout_model": layout_model_name() if module_installed("paddleocr") else "",
        "text_model": "PaddleOCR" if module_installed("paddleocr") else "",
        "formula_model": "pix2tex" if module_installed("pix2tex") else "",
        "ready": module_installed("paddleocr") and module_installed("pix2tex"),
    }


def is_formula_label(label: str) -> bool:
    name = (label or "").strip().lower().replace("-", "_")
    if name in {"formula_number", "formula_caption"}:
        return False
    return name in FORMULA_LABELS or name.endswith("_formula")


def compose_reading_order(blocks: list[dict[str, Any]]) -> str:
    """Join recognized blocks from top to bottom, and left to right on one row."""
    rows: list[dict[str, Any]] = []
    ordered = sorted(blocks, key=lambda block: (float(block.get("y0") or 0), float(block.get("x0") or 0)))
    for block in ordered:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        y0 = float(block.get("y0") or 0)
        height = max(8.0, float(block.get("y1") or 0) - y0)
        if rows and abs(y0 - float(rows[-1]["y0"])) <= height * 0.6:
            rows[-1]["parts"].append(block)
        else:
            rows.append({"y0": y0, "parts": [block]})
    lines: list[str] = []
    for row in rows:
        parts = sorted(row["parts"], key=lambda block: float(block.get("x0") or 0))
        texts = [str(part.get("text") or "").strip() for part in parts if str(part.get("text") or "").strip()]
        if not texts:
            continue
        header, rest = _peel_question_header(texts[0])
        body = " ".join(piece for piece in [rest, *texts[1:]] if piece)
        if header and body:
            lines.append(header)
            lines.append(body)
        else:
            lines.append(" ".join(texts))
    return "\n".join(line for line in lines if line)


def _peel_question_header(text: str) -> tuple[str, str]:
    """Keep ``14.`` on its own line so the answer parser does not drop the rest of that row."""
    match = re.match(r"^((?:第\s*)?\d{1,2}\s*(?:题|[.．、]))\s*(.*)$", text.strip())
    if not match:
        return "", text.strip()
    return match.group(1).strip(), match.group(2).strip()


def drop_text_covered_by_formula(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formulas = [region for region in regions if is_formula_label(str(region.get("label") or ""))]
    kept: list[dict[str, Any]] = []
    for region in regions:
        if is_formula_label(str(region.get("label") or "")):
            kept.append(region)
            continue
        if any(_covered_ratio(region, formula) >= 0.7 for formula in formulas):
            continue
        kept.append(region)
    return kept


def recognize_page(
    image: Image.Image,
    *,
    detect: Callable[[Image.Image], list[dict[str, Any]]] | None = None,
    read_text: Callable[[Image.Image], str] | None = None,
    read_formula: Callable[[Image.Image], str] | None = None,
) -> str:
    """Detect layout, then read text blocks and formula blocks separately."""
    detect = detect or detect_layout
    read_text = read_text or read_text_block
    read_formula = read_formula or read_formula_block
    regions = drop_text_covered_by_formula(detect(image))
    if not regions:
        return read_text(image).strip()
    pieces: list[dict[str, Any]] = []
    for region in regions:
        label = str(region.get("label") or "")
        if label.strip().lower() in SKIP_LABELS:
            continue
        crop = _crop(image, region)
        if crop is None:
            continue
        if is_formula_label(label):
            latex = read_formula(crop).strip().strip("$")
            text = f"${latex}$" if latex else ""
        else:
            text = read_text(crop).strip()
        if text:
            pieces.append({**region, "text": text})
    return compose_reading_order(pieces)


def ocr_images_v2(
    images: list[tuple[bytes, str]],
    *,
    questions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """OCR photos with the layout, PaddleOCR, and pix2tex pipeline."""
    status = ocr_v2_configured()
    if not status["ready"]:
        missing = []
        if not status["text_model"]:
            missing.append("paddleocr")
        if not status["formula_model"]:
            missing.append("pix2tex")
        raise RuntimeError("评分2需要安装 " + " 和 ".join(missing) + "。")
    if not images:
        raise ValueError("请至少上传一张答卷照片。")
    if len(images) > 12:
        raise ValueError("一次最多上传 12 张照片。")
    pages: list[str] = []
    for raw, mime in images:
        image, _blob, _mime = prepare_image(raw, mime)
        pages.append(recognize_page(image))
    text = "\n\n".join(page for page in pages if page).strip()
    answers = parse_answers_in_order(text, questions or []) if questions else {}
    return {
        "engine": "paddleocr+pix2tex",
        "ocr_text": text,
        "answers_by_no": answers,
    }


def detect_layout(image: Image.Image) -> list[dict[str, Any]]:
    model = _layout_model()
    if model is None:
        return []
    output = _predict(model, image)
    regions: list[dict[str, Any]] = []
    for item in output:
        data = _result_dict(item)
        for box in data.get("boxes") or []:
            if not isinstance(box, dict):
                continue
            coord = box.get("coordinate") or box.get("bbox") or []
            if len(coord) < 4:
                continue
            score = float(box.get("score") or 0)
            if score < 0.35:
                continue
            regions.append(
                {
                    "label": str(box.get("label") or ""),
                    "score": score,
                    "x0": float(coord[0]),
                    "y0": float(coord[1]),
                    "x1": float(coord[2]),
                    "y1": float(coord[3]),
                }
            )
    return regions


def read_text_block(image: Image.Image) -> str:
    model = _text_model()
    if model is None:
        return ""
    output = _predict(model, image)
    chunks: list[str] = []
    for item in output:
        data = _result_dict(item)
        for text in data.get("rec_texts") or []:
            piece = str(text or "").strip()
            if piece:
                chunks.append(piece)
    return " ".join(chunks).strip()


def read_formula_block(image: Image.Image) -> str:
    model = _formula_model()
    if model is None:
        return ""
    try:
        latex = model(_pad(image.convert("RGB"), 8))
    except Exception:
        return ""
    return str(latex or "").strip()


def _layout_model() -> Any:
    global _LAYOUT, _LAYOUT_FAILED
    if _LAYOUT is not None or _LAYOUT_FAILED:
        return _LAYOUT
    if not module_installed("paddleocr"):
        _LAYOUT_FAILED = True
        return None
    try:
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import LayoutDetection

        _LAYOUT = LayoutDetection(model_name=layout_model_name())
    except Exception:
        _LAYOUT_FAILED = True
        _LAYOUT = None
    return _LAYOUT


def _text_model() -> Any:
    global _TEXT, _TEXT_FAILED
    if _TEXT is not None or _TEXT_FAILED:
        return _TEXT
    if not module_installed("paddleocr"):
        _TEXT_FAILED = True
        return None
    try:
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import PaddleOCR

        _TEXT = PaddleOCR(
            lang="ch",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except Exception:
        _TEXT_FAILED = True
        _TEXT = None
    return _TEXT


def _formula_model() -> Any:
    global _FORMULA, _FORMULA_FAILED
    if _FORMULA is not None or _FORMULA_FAILED:
        return _FORMULA
    if not module_installed("pix2tex"):
        _FORMULA_FAILED = True
        return None
    try:
        from pix2tex.cli import LatexOCR

        _FORMULA = LatexOCR()
    except Exception:
        _FORMULA_FAILED = True
        _FORMULA = None
    return _FORMULA


def _predict(model: Any, image: Image.Image) -> list[Any]:
    try:
        with tempfile.TemporaryDirectory(prefix="sheet-v2-") as tmp:
            path = Path(tmp) / "block.png"
            image.convert("RGB").save(path)
            output = model.predict(input=str(path), **_predict_kwargs(model))
    except Exception:
        return []
    return list(output or [])


def _predict_kwargs(model: Any) -> dict[str, Any]:
    """PaddleOCR.predict rejects batch_size. Layout models accept it."""
    params = inspect.signature(model.predict).parameters
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()):
        return {"batch_size": 1}
    if "batch_size" in params:
        return {"batch_size": 1}
    return {}


def _result_dict(item: Any) -> dict[str, Any]:
    raw: Any = item
    if isinstance(getattr(type(item), "json", None), property):
        try:
            raw = item.json
        except Exception:
            raw = item
    if isinstance(raw, dict) and isinstance(raw.get("res"), dict):
        return raw["res"]
    if isinstance(raw, dict):
        return raw
    return {}


def _crop(image: Image.Image, region: dict[str, Any]) -> Image.Image | None:
    x0 = max(0, int(float(region.get("x0") or 0)))
    y0 = max(0, int(float(region.get("y0") or 0)))
    x1 = min(image.width, int(float(region.get("x1") or 0)))
    y1 = min(image.height, int(float(region.get("y1") or 0)))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return image.crop((x0, y0, x1, y1))


def _pad(image: Image.Image, pad: int) -> Image.Image:
    canvas = Image.new("RGB", (image.width + pad * 2, image.height + pad * 2), "white")
    canvas.paste(image, (pad, pad))
    return canvas


def _covered_ratio(inner: dict[str, Any], outer: dict[str, Any]) -> float:
    x0 = max(float(inner.get("x0") or 0), float(outer.get("x0") or 0))
    y0 = max(float(inner.get("y0") or 0), float(outer.get("y0") or 0))
    x1 = min(float(inner.get("x1") or 0), float(outer.get("x1") or 0))
    y1 = min(float(inner.get("y1") or 0), float(outer.get("y1") or 0))
    area = max(0.0, float(inner.get("x1") or 0) - float(inner.get("x0") or 0)) * max(
        0.0, float(inner.get("y1") or 0) - float(inner.get("y0") or 0)
    )
    if area <= 0 or x1 <= x0 or y1 <= y0:
        return 0.0
    return ((x1 - x0) * (y1 - y0)) / area
