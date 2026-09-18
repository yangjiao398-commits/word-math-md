"""OCR photographed exam answer sheets (vision API, RapidOCR, or Tesseract)."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from word_math_md.sheet_grade import parse_ocr_answers

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

MAX_IMAGE_PX = 1600
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
只提取学生写下或涂选的答案，不要把印刷题干、选项内容或解析当成答案。
用 JSON 返回，不要 markdown：
{"answers":[{"no":1,"answer":"A"},{"no":2,"answer":"BD"},{"no":3,"answer":"3/2"}]}
规则：
- no 是题号（整数）
- 选择题 answer 只用 A-G 字母，多选多个字母连写，如 ABD
- 填空/解答尽量保留学生原文，分数写成 a/b
- 看不清的题不要编造，直接省略
"""


def ocr_configured() -> dict[str, Any]:
    engines = available_engines()
    return {"configured": bool(engines), "engines": engines}


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
    out = io.BytesIO()
    fmt = kind or "JPEG"
    if fmt == "PNG":
        sharp.save(out, format="PNG", optimize=True)
        mime_out = "image/png"
    else:
        sharp.save(out, format="JPEG", quality=85)
        mime_out = "image/jpeg"
    return sharp, out.getvalue(), mime_out


def ocr_images(images: list[tuple[bytes, str]], *, engine: str = "auto") -> dict[str, Any]:
    """OCR one or more photos. images is [(bytes, mime), ...]."""
    if not images:
        raise ValueError("请至少上传一张答卷照片。")
    if len(images) > 12:
        raise ValueError("一次最多上传 12 张照片。")
    name = _preferred_engine(engine)
    pages: list[dict[str, Any]] = []
    merged_text: list[str] = []
    answers: dict[int, str] = {}
    for idx, (raw, mime) in enumerate(images, start=1):
        img, blob, out_mime = prepare_image(raw, mime)
        page = _ocr_one(img, blob, out_mime, name)
        page["page"] = idx
        pages.append(page)
        merged_text.append(page.get("text") or "")
        for no, ans in (page.get("answers") or {}).items():
            answers[int(no)] = ans
    blob = "\n".join(merged_text)
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


def _ocr_one(img: Image.Image, blob: bytes, mime: str, engine: str) -> dict[str, Any]:
    if engine in {"dashscope", "openai"}:
        return _ocr_vision(blob, mime, engine)
    if engine == "rapidocr":
        return _ocr_rapid(img)
    return _ocr_tesseract(img)


def _ocr_vision(blob: bytes, mime: str, engine: str) -> dict[str, Any]:
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
                    {"type": "text", "text": VISION_PROMPT},
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


def _ocr_rapid(img: Image.Image) -> dict[str, Any]:
    global _RAPID
    import numpy as np

    if _RAPID is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            from rapidocr import RapidOCR
        _RAPID = RapidOCR()
    result, _elapse = _RAPID(np.array(img))
    lines: list[str] = []
    boxes: list[tuple[float, str]] = []
    for item in result or []:
        if not item:
            continue
        if len(item) >= 2:
            box, txt = item[0], item[1]
        else:
            continue
        text = str(txt or "").strip()
        if not text:
            continue
        try:
            ys = [p[1] for p in box]
            y = float(sum(ys) / len(ys)) if ys else 0.0
        except Exception:
            y = float(len(boxes))
        boxes.append((y, text))
    boxes.sort(key=lambda pair: pair[0])
    lines = [t for _, t in boxes]
    blob = "\n".join(lines)
    return {"text": blob, "answers": parse_ocr_answers(blob), "engine": "rapidocr"}


def _ocr_tesseract(img: Image.Image) -> dict[str, Any]:
    import pytesseract

    lang = os.environ.get("TESSDATA_LANG") or "chi_sim+eng"
    blob = pytesseract.image_to_string(img, lang=lang) or ""
    return {"text": blob, "answers": parse_ocr_answers(blob), "engine": "tesseract"}
