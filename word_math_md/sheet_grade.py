"""Parse OCR text from photographed answer sheets and score against the exam bank."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

CHOICE_TYPES = {"single_choice", "multi_choice"}
TYPE_LABELS = {
    "single_choice": "单选",
    "multi_choice": "多选",
    "fill_blank": "填空",
    "solution": "解答",
}

_INLINE_ITEM_RE = re.compile(
    r"(?:第\s*)?(\d{1,2})\s*(?:题|[.．、:：)）])\s*"
    r"([A-Ga-g](?:\s*[,，、/]?\s*[A-Ga-g]){0,6}"
    r"|[^\n第]{1,80}?)"
    r"(?=(?:\s*(?:第\s*)?\d{1,2}\s*(?:题|[.．、:：)）]))|$)"
)
_LINE_ITEM_RE = re.compile(
    r"^\s*(?:第\s*)?(\d{1,2})\s*(?:题|[.．、:：)）])?\s+(.+?)\s*$"
)
_LATEX_FRAC_RE = re.compile(r"\\(?:d?frac|cfrac)\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+\s*")


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def parse_ocr_answers(ocr_text: str, *, max_no: int = 80) -> dict[int, str]:
    """Pull {question_no: student_answer} from OCR / vision text."""
    text = _nfkc(ocr_text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("：", ":").replace("．", ".")
    found: dict[int, str] = {}

    def remember(no: int, raw: str) -> None:
        if no < 1 or no > max_no:
            return
        answer = _clean_extracted(raw)
        if not answer:
            return
        prev = found.get(no, "")
        if len(answer) >= len(prev):
            found[no] = answer

    for match in _INLINE_ITEM_RE.finditer(text.replace("\n", " ")):
        remember(int(match.group(1)), match.group(2))
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = _LINE_ITEM_RE.match(line)
        if match:
            remember(int(match.group(1)), match.group(2))
            continue
        compact = re.sub(r"\s+", "", line)
        for piece in _INLINE_ITEM_RE.finditer(compact):
            remember(int(piece.group(1)), piece.group(2))
    return dict(sorted(found.items()))


def _clean_extracted(raw: str) -> str:
    text = _nfkc(raw).strip()
    text = re.sub(r"^(?:答案|答|选|填写)[:：\s]*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" 。.;；,，")
    return text[:200]


def normalize_choice(answer: str) -> str:
    letters = [c.upper() for c in re.findall(r"[A-Ga-g]", _nfkc(answer))]
    seen: list[str] = []
    for letter in letters:
        if letter not in seen:
            seen.append(letter)
    return "".join(sorted(seen))


def normalize_blank(answer: str) -> str:
    text = _nfkc(answer)
    text = text.replace("$$", "$")
    text = re.sub(r"\$+", "", text)
    text = _LATEX_FRAC_RE.sub(lambda m: f"{m.group(1)}/{m.group(2)}", text)
    text = re.sub(r"\\mathrm\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\operatorname\s*\{([^{}]*)\}", r"\1", text)
    text = text.replace("\\left", "").replace("\\right", "")
    text = text.replace("\\,", "").replace("\\;", "").replace("\\!", "")
    text = _LATEX_CMD_RE.sub("", text)
    text = text.replace("{", "").replace("}", "")
    text = text.replace("×", "*").replace("·", "*").replace("÷", "/")
    text = text.replace("／", "/").replace("−", "-").replace("—", "-")
    text = re.sub(r"\s+", "", text)
    text = text.strip(" 。.;；,，=")
    return text.lower()


def answers_match(type_code: str, expected: str, student: str) -> tuple[bool, str]:
    """Return (is_correct, status). status is graded | missing | needs_review."""
    student = (student or "").strip()
    expected = (expected or "").strip()
    if not student:
        return False, "missing"
    kind = (type_code or "").strip() or "solution"
    if kind in CHOICE_TYPES:
        got = normalize_choice(student)
        want = normalize_choice(expected)
        if not got:
            return False, "needs_review"
        return got == want and bool(want), "graded"
    if kind == "fill_blank":
        got = normalize_blank(student)
        want = normalize_blank(expected)
        if not got:
            return False, "missing"
        if got == want and want:
            return True, "graded"
        if want and (got in want or want in got) and min(len(got), len(want)) >= 1:
            return True, "graded"
        return False, "graded"
    got = normalize_blank(student)
    want = normalize_blank(expected)
    if got and want and got == want:
        return True, "graded"
    if got and want:
        ratio = SequenceMatcher(None, got, want).ratio()
        if ratio >= 0.86:
            return True, "graded"
        return False, "needs_review"
    if got and not want:
        return False, "needs_review"
    return False, "missing"


def _question_score(row: dict[str, Any]) -> float:
    raw = row.get("score")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 0.0
    if value > 0:
        return value
    kind = (row.get("type_code") or "").strip()
    if kind == "solution":
        return 10.0
    if kind == "multi_choice":
        return 5.0
    return 5.0 if kind in CHOICE_TYPES or kind == "fill_blank" else 1.0


def grade_paper(
    questions: list[dict[str, Any]],
    student_answers: dict[int, str],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    total = 0.0
    max_score = 0.0
    correct = 0
    reviewed = 0
    missing = 0
    for row in questions:
        try:
            no = int(row.get("question_no") or 0)
        except (TypeError, ValueError):
            continue
        if no < 1:
            continue
        expected = str(row.get("answer_md") or "").strip()
        student = str(student_answers.get(no) or "").strip()
        kind = str(row.get("type_code") or "solution")
        max_item = _question_score(row)
        max_score += max_item
        ok, status = answers_match(kind, expected, student)
        earned = max_item if ok else 0.0
        total += earned
        if ok:
            correct += 1
        if status == "needs_review":
            reviewed += 1
        if status == "missing":
            missing += 1
        items.append(
            {
                "question_id": row.get("id"),
                "question_no": no,
                "type_code": kind,
                "type_label": TYPE_LABELS.get(kind, kind),
                "student_answer": student,
                "expected_answer": expected,
                "is_correct": ok,
                "status": status,
                "score": earned,
                "max_score": max_item,
            }
        )
    return {
        "items": items,
        "total_score": round(total, 2),
        "max_score": round(max_score, 2),
        "correct_count": correct,
        "question_count": len(items),
        "needs_review_count": reviewed,
        "missing_count": missing,
        "recognized_count": sum(1 for item in items if item["student_answer"]),
    }
