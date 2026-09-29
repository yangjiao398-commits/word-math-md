"""Parse OCR text from photographed answer sheets and score against the exam bank."""

from __future__ import annotations

import html
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
    r"(?<![（(\d])(?:第\s*)?(\d{1,2})\s*(?:题|[.．、:：])\s*"
    r"([A-Ga-g](?:\s*[,，、/]?\s*[A-Ga-g]){0,6}"
    r"|[^\n第]{1,80}?)"
    r"(?=(?:\s*(?<![（(\d])(?:第\s*)?\d{1,2}\s*(?:题|[.．、:：]))|$)"
)
_LINE_ITEM_RE = re.compile(
    r"^(?![（(])\s*(?:第\s*)?(\d{1,2})\s*(?:题|[.．、:：])\s+(.+?)\s*$"
)
_MAIN_HEADER_RE = re.compile(
    r"^(?:第\s*)?(?P<no>\d{1,2})\s*(?:题|[.．、])\s*(?P<rest>.*)$"
)
_SUB_HEADER_RE = re.compile(r"^[（(]\s*\d+\s*[）)]")
_BLANK_CHOICE_RE = re.compile(
    r"[（(][ \t]*[）)][ \t]*[（(]?[ \t]*"
    r"([A-Ga-g](?:[ \t]*[,，、/]?[ \t]*[A-Ga-g]){0,6})"
    r"(?![ \t]*[.．、])"
)
# 字母写在括号里面，或与括号重叠后只剩半边：为（D） / 是（C / 为（BD）
_INSIDE_CHOICE_RE = re.compile(
    r"(?:为|是|=|＝)\s*[（(][ \t]*"
    r"([A-Ga-g](?:[ \t]*[,，、/]?[ \t]*[A-Ga-g]){0,5})"
    r"[ \t]*[）)]?(?![ \t]*[.．、A-Za-z0-9])"
)
_SOLO_CHOICE_RE = re.compile(
    r"^([A-Ga-g](?:\s*[,，、/]?\s*[A-Ga-g]){0,6})$"
)
_OPTION_LINE_RE = re.compile(r"^[A-Da-d]\s*[.．、]")
_NOISE_LINE_RE = re.compile(
    r"127\.0\.0\.1|MathDoc|Converter|^\d{1,2}\s*/\s*\d{1,2}$|^\d{4}[/-]\d"
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
        found[no] = _prefer_answer(prev, answer)

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


def _is_choice_token(text: str) -> bool:
    compact = re.sub(r"[\s,，、/]", "", text or "")
    return bool(re.fullmatch(r"[A-Ga-g]{1,6}", compact))


def _prefer_answer(prev: str, new: str) -> str:
    """Keep a handwritten choice letter instead of a longer printed stem."""
    if not prev:
        return new
    if _is_choice_token(prev) and not _is_choice_token(new):
        return prev
    if _is_choice_token(new) and not _is_choice_token(prev):
        return new
    if len(new) >= len(prev):
        return new
    return prev


def _question_outline(questions: list[dict[str, Any]]) -> list[tuple[int, str]]:
    outline: list[tuple[int, str]] = []
    for row in questions or []:
        try:
            no = int(row.get("question_no") or 0)
        except (TypeError, ValueError):
            continue
        if no < 1:
            continue
        kind = str(row.get("type_code") or "solution")
        outline.append((no, kind))
    outline.sort(key=lambda item: item[0])
    return outline


def _header_no(line: str) -> tuple[int, str] | None:
    """Main question header such as ``1.`` / ``第2题``. Ignore ``（1）`` subparts."""
    text = line.strip()
    if not text or _SUB_HEADER_RE.match(text):
        return None
    match = _MAIN_HEADER_RE.match(text)
    if not match:
        return None
    return int(match.group("no")), (match.group("rest") or "").strip()


def _split_blocks_in_order(text: str, numbers: list[int]) -> dict[int, str]:
    """Cut OCR text into blocks following the paper's question order."""
    lines = [line.strip() for line in text.split("\n")]
    wanted = set(numbers)
    blocks: dict[int, str] = {}
    cursor = 0
    for no in numbers:
        start = None
        for index in range(cursor, len(lines)):
            header = _header_no(lines[index])
            if header and header[0] == no:
                start = index
                break
        if start is None:
            blocks[no] = ""
            continue
        end = len(lines)
        for index in range(start + 1, len(lines)):
            header = _header_no(lines[index])
            if header and header[0] in wanted and header[0] > no:
                end = index
                break
        chunk = [lines[start]]
        chunk.extend(
            line
            for line in lines[start + 1 : end]
            if line and not _NOISE_LINE_RE.search(line)
        )
        blocks[no] = "\n".join(chunk).strip()
        cursor = start + 1
    return blocks


def _choice_letters(raw: str, *, multi: bool) -> str:
    letters = normalize_choice(raw)
    if multi and letters:
        return letters
    if not multi and len(letters) == 1:
        return letters
    return ""


def _extract_choice(block: str, *, multi: bool) -> str:
    """Read the letter in or beside the answer blank, not the printed A/B/C/D options."""
    for pattern in (_BLANK_CHOICE_RE, _INSIDE_CHOICE_RE):
        for match in pattern.finditer(block or ""):
            letters = _choice_letters(match.group(1), multi=multi)
            if letters:
                return letters
    for line in (block or "").split("\n"):
        text = line.strip()
        if not text or _OPTION_LINE_RE.match(text) or _header_no(text):
            continue
        solo = _SOLO_CHOICE_RE.match(text)
        if not solo:
            continue
        letters = normalize_choice(solo.group(1))
        if multi and len(letters) >= 2:
            return letters
        if not multi and len(letters) == 1:
            return letters
    return ""


def _looks_like_math_answer(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or len(raw) > 40:
        return False
    if re.search(r"则|若|已知|函数|命题|求|下列|设|正确", raw):
        return False
    if len(re.findall(r"[\u4e00-\u9fff]", raw)) >= 2:
        return False
    return bool(re.search(r"\d|π|兀|Π|\\frac|[A-Za-z]", raw))


def _fill_tail(text: str) -> str:
    """Answer written in the last blank, including ink that sits inside （ ）."""
    marks = list(re.finditer(r"(?:=|＝|为)", text))
    if not marks:
        return ""
    tail = text[marks[-1].end() :].strip(" 。.;；,， \t")
    tail = re.sub(r"^[（(]\s*", "", tail)
    tail = re.sub(r"\s*[）)]\s*$", "", tail).strip()
    if tail and _looks_like_math_answer(tail) and not _OPTION_LINE_RE.match(tail):
        return _clean_extracted(tail)
    return ""


def _extract_fill(block: str) -> str:
    lines = []
    for line in (block or "").split("\n"):
        text = line.strip()
        if not text or _header_no(text) or _OPTION_LINE_RE.match(text):
            continue
        lines.append(text)
    # 只取题干里最后一个空。前面的「圆心为O」不是作答。
    last_tail = ""
    saw_blank = False
    for text in lines:
        if re.search(r"(?:=|＝|为)", text):
            saw_blank = True
            last_tail = _fill_tail(text)
    if last_tail:
        return last_tail
    if saw_blank:
        for text in lines:
            if len(text) <= 24 and _looks_like_math_answer(text) and not re.search(r"[为是=＝]", text):
                return _clean_extracted(text.strip("（）()"))
    return ""


def _extract_solution(block: str) -> str:
    work: list[str] = []
    seen_prompt = False
    for line in (block or "").split("\n"):
        text = line.strip()
        if not text or _header_no(text):
            continue
        if _SUB_HEADER_RE.match(text):
            seen_prompt = True
            continue
        if seen_prompt and not _OPTION_LINE_RE.match(text):
            work.append(text)
    if not work:
        return ""
    return _clean_extracted(" ".join(work))


def answer_from_snippet(text: str, type_code: str) -> str:
    """Read an answer from a close-up of one blank. The snippet may be only the handwriting."""
    raw = (text or "").strip()
    if not raw:
        return ""
    kind = (type_code or "").strip() or "solution"
    wrapped = f"1.\n{raw}"
    found = _extract_for_type(wrapped, kind)
    if found:
        return found
    if kind == "fill_blank":
        piece = raw.strip("（）() \t")
        if _looks_like_math_answer(piece):
            return _clean_extracted(piece)
    if kind in CHOICE_TYPES:
        bare = re.sub(r"[（）()\s]", "", raw)
        if not _is_choice_token(bare):
            return ""
        letters = normalize_choice(bare)
        if kind == "single_choice" and len(letters) == 1:
            return letters
        if kind == "multi_choice" and letters:
            return letters
    return ""


def _extract_for_type(block: str, type_code: str) -> str:
    kind = (type_code or "").strip() or "solution"
    if kind == "multi_choice":
        return _extract_choice(block, multi=True)
    if kind == "single_choice":
        return _extract_choice(block, multi=False)
    if kind == "fill_blank":
        return _extract_fill(block)
    return _extract_solution(block)


def parse_answers_in_order(
    ocr_text: str,
    questions: list[dict[str, Any]],
    *,
    max_no: int = 80,
) -> dict[int, str]:
    """Read student answers in the paper's question order, then ignore subparts like （1）."""
    outline = [(no, kind) for no, kind in _question_outline(questions) if no <= max_no]
    if not outline:
        return parse_ocr_answers(ocr_text, max_no=max_no)
    text = _nfkc(ocr_text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("：", ":").replace("．", ".")
    blocks = _split_blocks_in_order(text, [no for no, _kind in outline])
    found: dict[int, str] = {}
    for no, kind in outline:
        answer = _extract_for_type(blocks.get(no, ""), kind)
        if answer:
            found[no] = answer
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


def answer_alternatives(expected: str) -> list[str]:
    """Split ``latex##plain`` style equivalents stored on some fill-in answers."""
    text = html.unescape(expected or "").strip()
    parts = [part.strip() for part in text.split("##")]
    parts = [part for part in parts if part]
    return parts or [""]


def normalize_blank(answer: str) -> str:
    text = _nfkc(html.unescape(answer))
    text = text.replace("$$", "$")
    text = re.sub(r"\$+", "", text)
    text = _LATEX_FRAC_RE.sub(lambda m: f"{m.group(1)}/{m.group(2)}", text)
    text = re.sub(r"\\mathrm\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\operatorname\s*\{([^{}]*)\}", r"\1", text)
    text = text.replace("\\left", "").replace("\\right", "")
    text = text.replace("\\,", "").replace("\\;", "").replace("\\!", "")
    text = text.replace("\\pi", "pi").replace("π", "pi").replace("兀", "pi").replace("Π", "pi")
    text = _LATEX_CMD_RE.sub("", text)
    text = re.sub(r"\((\d+\s*/\s*\d+)\)", r"\1", text)
    text = re.sub(r"(\d+)pi/(\d+)", r"\1/\2pi", text)
    text = text.replace("{", "").replace("}", "")
    text = text.replace("×", "*").replace("·", "*").replace("÷", "/")
    text = text.replace("／", "/").replace("−", "-").replace("—", "-")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"^\((.*)\)$", r"\1", text)
    text = text.strip(" 。.;；,，=")
    return text.lower()


def _blank_equal(got: str, want: str) -> bool:
    if got == want and want:
        return True
    if want and (got in want or want in got) and min(len(got), len(want)) >= 1:
        return True
    return False


def answers_match(type_code: str, expected: str, student: str) -> tuple[bool, str]:
    """Return (is_correct, status). status is graded | missing | needs_review."""
    student = (student or "").strip()
    if not student:
        return False, "missing"
    alts = answer_alternatives(expected)
    kind = (type_code or "").strip() or "solution"
    if kind in CHOICE_TYPES:
        got = normalize_choice(student)
        if not got:
            return False, "needs_review"
        return any(got == normalize_choice(alt) and normalize_choice(alt) for alt in alts), "graded"
    if kind == "fill_blank":
        got = normalize_blank(student)
        if not got:
            return False, "missing"
        return any(_blank_equal(got, normalize_blank(alt)) for alt in alts), "graded"
    got = normalize_blank(student)
    saw_review = False
    for alt in alts:
        want = normalize_blank(alt)
        if got and want and got == want:
            return True, "graded"
        if got and want and SequenceMatcher(None, got, want).ratio() >= 0.86:
            return True, "graded"
        if got and want:
            saw_review = True
        elif got and not want:
            saw_review = True
    if saw_review:
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
