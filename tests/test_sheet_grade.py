from word_math_md.sheet_grade import (
    answers_match,
    grade_paper,
    normalize_blank,
    normalize_choice,
    parse_ocr_answers,
)
from word_math_md.sheet_ocr import _answers_from_vision_text


def test_parse_ocr_answers_choice_lines():
    text = """
    第1题 A
    2. B
    3、CD
    4. 3/2
    5. 选 D
    """
    got = parse_ocr_answers(text)
    assert got[1] == "A"
    assert got[2] == "B"
    assert got[3] == "CD"
    assert got[4] == "3/2"
    assert "D" in got[5]


def test_parse_ocr_answers_inline_row():
    got = parse_ocr_answers("1.A 2.C 3.B 4.ABD 5.1/2")
    assert got[1] == "A"
    assert got[2] == "C"
    assert got[4] == "ABD"
    assert got[5] == "1/2"


def test_normalize_choice_and_blank():
    assert normalize_choice("选 B、D") == "BD"
    assert normalize_choice("d b a") == "ABD"
    assert normalize_blank(r"$\dfrac{3}{2}$") == "3/2"
    assert normalize_blank(" ３／２ ") == "3/2"


def test_answers_match_types():
    assert answers_match("single_choice", "A", "选A")[0] is True
    assert answers_match("multi_choice", "B、D", "DB")[0] is True
    assert answers_match("multi_choice", "BD", "B")[0] is False
    assert answers_match("fill_blank", r"$\frac{1}{2}$", "1/2")[0] is True
    ok, status = answers_match("solution", "证明略", "完全不相干的一句话")
    assert ok is False
    assert status == "needs_review"
    ok, status = answers_match("single_choice", "A", "")
    assert status == "missing"


def test_grade_paper_totals():
    questions = [
        {"id": "q1", "question_no": 1, "type_code": "single_choice", "answer_md": "A", "score": 5},
        {"id": "q2", "question_no": 2, "type_code": "multi_choice", "answer_md": "AC", "score": 5},
        {"id": "q3", "question_no": 3, "type_code": "fill_blank", "answer_md": r"$\frac{3}{2}$", "score": 5},
        {"id": "q4", "question_no": 4, "type_code": "solution", "answer_md": "略", "score": 10},
    ]
    report = grade_paper(questions, {1: "A", 2: "CA", 3: "3/2"})
    assert report["correct_count"] == 3
    assert report["total_score"] == 15
    assert report["max_score"] == 25
    assert report["missing_count"] == 1
    assert report["items"][3]["status"] == "missing"


def test_vision_json_answers():
    text = '```json\n{"answers":[{"no":1,"answer":"B"},{"no":2,"answer":"1/2"}]}\n```'
    got = _answers_from_vision_text(text)
    assert got == {1: "B", 2: "1/2"}
