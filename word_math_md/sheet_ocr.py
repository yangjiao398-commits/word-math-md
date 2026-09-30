"""OCR photographed exam answer sheets (vision API, RapidOCR, or Tesseract)."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from word_math_md.formula_ocr import (
    formula_model_name,
    module_installed,
    recognize_formula,
    recognize_page_markdown,
)
from word_math_md.sheet_grade import (
    CHOICE_TYPES,
    _header_no,
    _is_choice_token,
    _question_outline,
    _looks_like_math_answer,
    answer_from_snippet,
    normalize_choice,
    parse_answers_in_order,
    parse_ocr_answers,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

MAX_IMAGE_PX = 2800
# Pix2Text and the formula models can spend minutes on one photo. Grading must
# still return the RapidOCR result once this extra budget is used up.
_EXTRA_BUDGET_S = float(os.environ.get("SHEET_OCR_EXTRA_SECONDS") or 8)
_HEAVY_LOCK = threading.Lock()
MAX_IMAGE_BYTES = 12 * 1024 * 1024
ALLOWED_MIME = {
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
    "image/bmp": "BMP",
    "image/gif": "GIF",
}

VISION_PROMPT = """你是高中数学答卷识别助手。图中是学生做完后拍摄的试卷/答题卡照片。
按试卷大题顺序 1、2、3… 读取学生写下或涂选的答案。不要把印刷题干、选项 A.B.C.D. 或解析当成答案。
解答题里的（1）（2）是小题，不是新的大题，不要据此改题号。
用 JSON 返回，不要 markdown：
{"answers":[{"no":1,"answer":"A"},{"no":2,"answer":"BD"},{"no":3,"answer":"3/2"}]}
规则：
- no 是大题题号（整数），顺序与试卷一致
- 选择题 answer 只用学生填在括号里、与括号重叠、或题号旁的 A-G 字母，多选连写，如 ABD。括号里的字母也要读，例如（C）（BD）
- 填空/解答只保留学生手写内容，分数写成 a/b
- 看不清的题不要编造，直接省略
"""

CHOICE_CROP_PROMPT = """图中是选择题答题括号的放大照片。
只输出学生写在括号里或压在括号上的选项字母，例如 D 或 BD。
不要输出题干，不要输出印刷的 A. B. C. D. 选项内容。看不清就留空。"""


def ocr_configured() -> dict[str, Any]:
    engines = available_engines()
    return {
        "configured": bool(engines),
        "engines": engines,
        "formula_model": formula_model_name() if module_installed("paddleocr") else "",
        "handwriting_model": "UniMERNet" if module_installed("paddleocr") else "",
        "page_model": "pix2text" if module_installed("pix2text") else "",
        "choice_vision": _vision_engine(),
    }


def available_engines() -> list[str]:
    found: list[str] = []
    if os.environ.get("DASHSCOPE_API_KEY"):
        found.append("dashscope")
    if os.environ.get("OPENAI_API_KEY"):
        found.append("openai")
    try:
        import rapidocr_onnxruntime  # noqa: F401

        found.append("rapidocr")
    except Exception:
        try:
            import rapidocr  # noqa: F401

            found.append("rapidocr")
        except Exception:
            pass
    try:
        import pytesseract  # noqa: F401

        found.append("tesseract")
    except Exception:
        pass
    return found


def _preferred_engine(requested: str = "") -> str:
    wanted = (requested or os.environ.get("SHEET_OCR_ENGINE") or "auto").strip().lower()
    engines = available_engines()
    if wanted != "auto":
        if wanted not in engines:
            raise RuntimeError(
                f"OCR 引擎 {wanted} 不可用。当前可用：{', '.join(engines) or '无'}。"
                "可安装 rapidocr-onnxruntime，或在 .env 配置 DASHSCOPE_API_KEY / OPENAI_API_KEY。"
            )
        return wanted
    for name in ("dashscope", "openai", "rapidocr", "tesseract"):
        if name in engines:
            return name
    raise RuntimeError(
        "未配置答卷 OCR。请安装 rapidocr-onnxruntime，或在 .env 填写 DASHSCOPE_API_KEY（通义千问视觉）"
        "或 OPENAI_API_KEY。"
    )


def prepare_image(data: bytes, mime: str = "") -> tuple[Image.Image, bytes, str]:
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("单张照片请小于 12MB。")
    kind = ALLOWED_MIME.get((mime or "").lower())
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as exc:
        raise ValueError("无法读取图片，请上传 jpg / png / webp 照片。") from exc
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")
    w, h = img.size
    scale = MAX_IMAGE_PX / max(w, h)
    if scale < 1:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    sharp = ImageEnhance.Contrast(img).enhance(1.25).filter(ImageFilter.SHARPEN)
    sharp = _pad_image(sharp, 24)
    out = io.BytesIO()
    fmt = kind or "JPEG"
    if fmt == "PNG":
        sharp.save(out, format="PNG", optimize=True)
        mime_out = "image/png"
    else:
        sharp.save(out, format="JPEG", quality=85)
        mime_out = "image/jpeg"
    return sharp, out.getvalue(), mime_out


def _bounded_call(fn, timeout: float):
    """Run a slow reader without holding the grade request past ``timeout`` seconds."""
    if timeout <= 0 or not _HEAVY_LOCK.acquire(blocking=False):
        return None
    done = threading.Event()
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except Exception:
            box["value"] = None
        finally:
            done.set()
            _HEAVY_LOCK.release()

    threading.Thread(target=run, daemon=True).start()
    if not done.wait(timeout):
        return None
    return box.get("value")


def ocr_images(
    images: list[tuple[bytes, str]],
    *,
    engine: str = "auto",
    questions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """OCR one or more photos. images is [(bytes, mime), ...]."""
    if not images:
        raise ValueError("请至少上传一张答卷照片。")
    if len(images) > 12:
        raise ValueError("一次最多上传 12 张照片。")
    name = _preferred_engine(engine)
    pages: list[dict[str, Any]] = []
    prepared: list[Image.Image] = []
    merged_text: list[str] = []
    answers: dict[int, str] = {}
    for idx, (raw, mime) in enumerate(images, start=1):
        img, blob, out_mime = prepare_image(raw, mime)
        prepared.append(img)
        page = _ocr_one(img, blob, out_mime, name)
        page["page"] = idx
        pages.append(page)
        merged_text.append(page.get("text") or "")
        for no, ans in (page.get("answers") or {}).items():
            answers[int(no)] = ans
    blob = "\n".join(merged_text)
    extra_deadline = time.perf_counter() + _EXTRA_BUDGET_S
    page_text = ""
    if questions and module_installed("pix2text"):
        page_text = _bounded_call(
            lambda: "\n\n".join(recognize_page_markdown(img) for img in prepared).strip(),
            extra_deadline - time.perf_counter(),
        ) or ""
    if questions:
        ordered = parse_answers_in_order(blob, questions)
        if page_text:
            ordered = _merge_page_answers(
                ordered,
                parse_answers_in_order(page_text, questions),
                questions,
            )
            blob = f"{blob}\n\n{page_text}" if blob else page_text
        if name in {"dashscope", "openai"}:
            answers = _merge_vision_answers(answers, ordered, questions)
        else:
            answers = ordered
        if name == "rapidocr":
            answers = _recover_blank_answers(
                prepared, pages, questions, answers, deadline=extra_deadline
            )
    else:
        parsed = parse_ocr_answers(blob)
        for no, ans in parsed.items():
            answers.setdefault(no, ans)
    return {
        "engine": name,
        "ocr_text": blob,
        "pages": pages,
        "answers": {str(k): v for k, v in sorted(answers.items())},
        "answers_by_no": answers,
    }


def _merge_vision_answers(
    vision: dict[int, str],
    ordered: dict[int, str],
    questions: list[dict[str, Any]],
) -> dict[int, str]:
    """Keep a vision letter only when it is a real choice; otherwise use ordered OCR."""
    kinds = {no: kind for no, kind in _question_outline(questions)}
    found: dict[int, str] = {}
    for no in sorted(set(kinds) | set(vision) | set(ordered)):
        kind = kinds.get(no, "")
        seen = str(vision.get(no) or "").strip()
        alt = str(ordered.get(no) or "").strip()
        if kind in CHOICE_TYPES and _is_choice_token(seen):
            found[no] = normalize_choice(seen)
        elif seen and kind not in CHOICE_TYPES and _is_choice_token(seen) is False:
            chinese = len(re.findall(r"[\u4e00-\u9fff]", seen))
            found[no] = alt if chinese >= 8 and alt else (seen if chinese < 8 else alt)
        elif alt:
            found[no] = alt
        elif seen and kind not in CHOICE_TYPES:
            found[no] = seen
    return {no: ans for no, ans in found.items() if ans}


def _ocr_one(img: Image.Image, blob: bytes, mime: str, engine: str) -> dict[str, Any]:
    if engine in {"dashscope", "openai"}:
        return _ocr_vision(blob, mime, engine)
    if engine == "rapidocr":
        return _ocr_rapid(img)
    return _ocr_tesseract(img)


def _vision_engine() -> str:
    if os.environ.get("DASHSCOPE_API_KEY"):
        return "dashscope"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return ""


def _ocr_vision(
    blob: bytes,
    mime: str,
    engine: str,
    *,
    prompt: str = "",
) -> dict[str, Any]:
    b64 = base64.b64encode(blob).decode("ascii")
    if engine == "dashscope":
        url = os.environ.get("DASHSCOPE_BASE_URL") or (
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        )
        key = os.environ.get("DASHSCOPE_API_KEY") or ""
        model = os.environ.get("DASHSCOPE_VISION_MODEL") or "qwen-vl-plus"
    else:
        url = os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1/chat/completions"
        key = os.environ.get("OPENAI_API_KEY") or ""
        model = os.environ.get("OPENAI_VISION_MODEL") or "gpt-4o-mini"
    if not key:
        raise RuntimeError(f"缺少 {engine} 的 API Key。")
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt or VISION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"视觉 OCR 调用失败 HTTP {exc.code}: {detail}") from exc
    text = (
        (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    ).strip()
    answers = _answers_from_vision_text(text)
    return {"text": text, "answers": answers, "engine": engine}


def _answers_from_vision_text(text: str) -> dict[int, str]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return parse_ocr_answers(text)
        else:
            return parse_ocr_answers(text)
    out: dict[int, str] = {}
    rows = data.get("answers") if isinstance(data, dict) else data
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                no = int(row.get("no") or row.get("question_no") or 0)
            except (TypeError, ValueError):
                continue
            ans = str(row.get("answer") or row.get("student_answer") or "").strip()
            if no >= 1 and ans:
                out[no] = ans
    if out:
        return out
    return parse_ocr_answers(text)


_RAPID = None


def _pad_image(img: Image.Image, pad: int) -> Image.Image:
    canvas = Image.new("RGB", (img.width + pad * 2, img.height + pad * 2), "white")
    canvas.paste(img, (pad, pad))
    return canvas


def _rapid_engine():
    global _RAPID
    if _RAPID is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            from rapidocr import RapidOCR
        # 检测短边放到 1280，矮字框门槛降到 16。model_path 留空表示仍用自带的 PP-OCRv3。
        _RAPID = RapidOCR(
            min_height=16,
            det_limit_side_len=1280,
            det_thresh=0.2,
            det_model_path="",
        )
    return _RAPID


def _rapid_items(img: Image.Image, *, text_score: float = 0.3) -> list[dict[str, Any]]:
    import numpy as np

    result, _elapse = _rapid_engine()(
        np.array(img),
        text_score=text_score,
        box_thresh=0.3,
        unclip_ratio=2.2,
    )
    items: list[dict[str, Any]] = []
    for item in result or []:
        if not item or len(item) < 2:
            continue
        box, txt = item[0], item[1]
        text = str(txt or "").strip()
        if not text:
            continue
        try:
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
        except Exception:
            continue
        items.append(
            {
                "text": text,
                "x0": min(xs),
                "x1": max(xs),
                "y0": min(ys),
                "y1": max(ys),
                "y": sum(ys) / len(ys),
            }
        )
    return items


def join_reading_order(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Put handwriting that sits on the same row, to the right of the blank, onto that line."""
    ordered = sorted(items, key=lambda it: (it["y"], it["x0"]))
    rows: list[dict[str, Any]] = []
    for item in ordered:
        height = max(8.0, item["y1"] - item["y0"])
        if rows and abs(item["y"] - rows[-1]["y"]) <= height * 0.65:
            rows[-1]["parts"].append(item)
            rows[-1]["y"] = sum(part["y"] for part in rows[-1]["parts"]) / len(rows[-1]["parts"])
        else:
            rows.append({"y": item["y"], "parts": [item]})
    lines: list[dict[str, Any]] = []
    for row in rows:
        parts = sorted(row["parts"], key=lambda part: part["x0"])
        text = " ".join(part["text"] for part in parts if part["text"]).strip()
        if not text:
            continue
        lines.append(
            {
                "text": text,
                "x0": min(part["x0"] for part in parts),
                "x1": max(part["x1"] for part in parts),
                "y0": min(part["y0"] for part in parts),
                "y1": max(part["y1"] for part in parts),
                "y": row["y"],
            }
        )
    return lines


def _ocr_rapid(img: Image.Image) -> dict[str, Any]:
    lines = join_reading_order(_rapid_items(img))
    blob = "\n".join(line["text"] for line in lines)
    return {
        "text": blob,
        "lines": lines,
        "answers": parse_ocr_answers(blob),
        "engine": "rapidocr",
    }


def _question_spans(
    lines: list[dict[str, Any]],
    numbers: list[int],
) -> dict[int, list[dict[str, Any]]]:
    wanted = set(numbers)
    spans: dict[int, list[dict[str, Any]]] = {}
    cursor = 0
    for no in numbers:
        start = None
        for index in range(cursor, len(lines)):
            header = _header_no(lines[index]["text"])
            if header and header[0] == no:
                start = index
                break
        if start is None:
            continue
        end = len(lines)
        for index in range(start + 1, len(lines)):
            header = _header_no(lines[index]["text"])
            if header and header[0] in wanted and header[0] > no:
                end = index
                break
        spans[no] = lines[start:end]
        cursor = start + 1
    return spans


def _blank_crop(img: Image.Image, span: list[dict[str, Any]]) -> Image.Image | None:
    """Crop the end of the stem, where the parenthesis or the last blank sits."""
    target = None
    for line in span:
        if re.search(r"[为是=＝（(]", line["text"]):
            target = line
    if target is None:
        return None
    width = max(1.0, target["x1"] - target["x0"])
    height = max(12.0, target["y1"] - target["y0"])
    left = target["x0"] + width * 0.38
    box = (
        max(0, int(left)),
        max(0, int(target["y0"] - height * 0.45)),
        min(img.width, int(target["x1"] + width * 0.55)),
        min(img.height, int(target["y1"] + height * 1.4)),
    )
    if box[2] - box[0] < 12 or box[3] - box[1] < 12:
        return None
    crop = img.crop(box)
    scale = 220 / max(crop.height, 1)
    if scale > 1:
        crop = crop.resize(
            (max(1, int(crop.width * scale)), max(1, int(crop.height * scale))),
            Image.Resampling.LANCZOS,
        )
    return _pad_image(crop, 16)


def _vision_choice_text(crop: Image.Image) -> str:
    engine = _vision_engine()
    if not engine:
        return ""
    out = io.BytesIO()
    crop.save(out, format="JPEG", quality=90)
    try:
        page = _ocr_vision(out.getvalue(), "image/jpeg", engine, prompt=CHOICE_CROP_PROMPT)
    except Exception:
        return ""
    return str(page.get("text") or "").strip()


def _rapid_crop_text(crop: Image.Image) -> str:
    lines = join_reading_order(_rapid_items(crop, text_score=0.2))
    return " ".join(line["text"] for line in lines).strip()


def _merge_page_answers(
    ordered: dict[int, str],
    page_answers: dict[int, str],
    questions: list[dict[str, Any]],
) -> dict[int, str]:
    """Use the full-page reader for Chinese and formulas. Keep choice letters from the first pass."""
    kinds = {no: kind for no, kind in _question_outline(questions)}
    found = dict(ordered)
    for no, kind in kinds.items():
        alt = str(page_answers.get(no) or "").strip()
        if not alt or kind in CHOICE_TYPES:
            continue
        current = str(found.get(no) or "").strip()
        if not current or (
            kind == "fill_blank"
            and _looks_like_math_answer(alt)
            and not _looks_like_math_answer(current)
        ):
            found[no] = alt
    return found


def _recover_blank_answers(
    images: list[Image.Image],
    pages: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    answers: dict[int, str],
    deadline: float | None = None,
) -> dict[int, str]:
    """Re-read the blank itself when the full-page pass missed a choice or formula."""
    outline = _question_outline(questions)
    numbers = [no for no, _kind in outline]
    found = dict(answers)
    for img, page in zip(images, pages):
        spans = _question_spans(page.get("lines") or [], numbers)
        for no, kind in outline:
            if no not in spans or kind not in {"single_choice", "multi_choice", "fill_blank"}:
                continue
            if kind in CHOICE_TYPES and found.get(no):
                continue
            crop = _blank_crop(img, spans[no])
            if crop is None:
                continue
            if kind in CHOICE_TYPES:
                snippet = _vision_choice_text(crop) or _rapid_crop_text(crop)
                answer = answer_from_snippet(snippet, kind)
            else:
                remaining = 0.0 if deadline is None else deadline - time.perf_counter()
                formula = _bounded_call(lambda crop=crop: recognize_formula(crop), remaining) or ""
                answer = answer_from_snippet(formula, kind) if formula else ""
                if not answer and not found.get(no):
                    answer = answer_from_snippet(_rapid_crop_text(crop), kind)
            if answer:
                found[no] = answer
    return found


def _ocr_tesseract(img: Image.Image) -> dict[str, Any]:
    import pytesseract

    lang = os.environ.get("TESSDATA_LANG") or "chi_sim+eng"
    blob = pytesseract.image_to_string(img, lang=lang) or ""
    return {"text": blob, "answers": parse_ocr_answers(blob), "engine": "tesseract"}
