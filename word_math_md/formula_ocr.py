"""Formula and full-page readers for answer-sheet grading.

Fill-in blanks use PP-FormulaNet_plus-M (or plus-L via FORMULA_MODEL).
Handwritten formulas are cross-checked with UniMERNet.
A full page of Chinese plus formulas is read with Pix2Text when that package is installed.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from word_math_md.sheet_grade import _looks_like_math_answer, normalize_blank

_FORMULA: dict[str, Any] = {}
_PIX2TEXT: Any = None
_PIX2TEXT_FAILED = False


def formula_model_name() -> str:
    name = (os.environ.get("FORMULA_MODEL") or "PP-FormulaNet_plus-M").strip()
    if name not in {"PP-FormulaNet_plus-M", "PP-FormulaNet_plus-L"}:
        return "PP-FormulaNet_plus-M"
    return name


def module_installed(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def choose_formula(primary: str, handwritten: str) -> str:
    """Prefer the Chinese formula model. Use UniMERNet when that reading is empty or not math."""
    primary = (primary or "").strip()
    handwritten = (handwritten or "").strip()
    if not primary:
        return handwritten
    if not handwritten:
        return primary
    if normalize_blank(primary) == normalize_blank(handwritten) and normalize_blank(primary):
        return primary
    if not _looks_like_math_answer(primary) and _looks_like_math_answer(handwritten):
        return handwritten
    return primary


def recognize_formula(image: Image.Image) -> str:
    """Read one blank crop. Returns LaTeX, or an empty string when the model is unavailable."""
    primary = _predict_formula(formula_model_name(), image)
    handwritten = _predict_formula("UniMERNet", image)
    return choose_formula(primary, handwritten)


def recognize_page_markdown(image: Image.Image) -> str:
    """Read a whole page of Chinese text and formulas into Markdown."""
    engine = _pix2text()
    if engine is None:
        return ""
    try:
        page = engine.recognize_page(
            image,
            text_contain_formula=True,
            table_as_image=True,
        )
    except Exception:
        return ""
    if isinstance(page, str):
        return page.strip()
    writer = getattr(page, "to_markdown", None)
    if writer is None:
        return str(page or "").strip()
    try:
        with tempfile.TemporaryDirectory(prefix="pix2text-") as tmp:
            writer(tmp)
            parts = [
                path.read_text(encoding="utf-8")
                for path in Path(tmp).rglob("*.md")
                if path.is_file()
            ]
    except Exception:
        return str(page or "").strip()
    return "\n\n".join(part.strip() for part in parts if part.strip())


def _predict_formula(model_name: str, image: Image.Image) -> str:
    try:
        model = _formula_model(model_name)
    except Exception:
        return ""
    if model is None:
        return ""
    try:
        with tempfile.TemporaryDirectory(prefix="formula-") as tmp:
            path = Path(tmp) / "crop.png"
            image.save(path)
            output = model.predict(input=str(path), batch_size=1)
    except Exception:
        return ""
    chunks: list[str] = []
    for item in output or []:
        formula = _formula_text(item)
        if formula:
            chunks.append(formula)
    return " ".join(chunks).strip()


def _formula_text(item: Any) -> str:
    raw: Any = item
    as_json = getattr(type(item), "json", None)
    if isinstance(as_json, property):
        try:
            raw = item.json
        except Exception:
            raw = item
    elif callable(getattr(item, "json", None)):
        try:
            raw = item.json()
        except Exception:
            raw = item
    if isinstance(raw, dict):
        inner = raw.get("res") if isinstance(raw.get("res"), dict) else raw
        return _as_formula(inner.get("rec_formula"))
    inner = getattr(item, "res", None)
    if isinstance(inner, dict):
        return _as_formula(inner.get("rec_formula"))
    return ""


def _as_formula(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " ".join(_as_formula(part) for part in value if _as_formula(part)).strip()
    return str(value or "").strip()


def _formula_model(model_name: str) -> Any:
    if model_name in _FORMULA:
        return _FORMULA[model_name]
    if not module_installed("paddleocr"):
        _FORMULA[model_name] = None
        return None
    try:
        from paddleocr import FormulaRecognition

        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        model = FormulaRecognition(model_name=model_name)
    except Exception:
        _FORMULA[model_name] = None
        return None
    _FORMULA[model_name] = model
    return model


def _pix2text() -> Any:
    global _PIX2TEXT, _PIX2TEXT_FAILED
    if _PIX2TEXT is not None or _PIX2TEXT_FAILED:
        return _PIX2TEXT
    if not module_installed("pix2text"):
        _PIX2TEXT_FAILED = True
        return None
    try:
        from pix2text import Pix2Text

        _PIX2TEXT = Pix2Text.from_config(device="cpu", enable_table=False)
    except Exception:
        _PIX2TEXT_FAILED = True
        _PIX2TEXT = None
    return _PIX2TEXT
