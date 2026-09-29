from word_math_md.sheet_grade import (
    answers_match,
    grade_paper,
    normalize_blank,
    normalize_choice,
    parse_answers_in_order,
    parse_ocr_answers,
)
from word_math_md.sheet_ocr import _answers_from_vision_text, join_reading_order


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
    assert answers_match("fill_blank", r"$\frac { 3 } { 10 }$##0.3", "0.3")[0] is True
    assert answers_match("fill_blank", r"$\frac { 3 } { 10 }$##0.3", "3/10")[0] is True
    assert answers_match("fill_blank", r"$2$", "2")[0] is True
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


def test_parse_answers_follow_question_order_not_subparts():
    text = """
1.
函数定义域为
A. [2, +00]
B. [2, 3]
C. (3, +00]
D. [2, 3)
2.
已知sinα= ，则cos2α =（)（C
A. 1
B. 0
D. -1
10.
已知都是正数，则下面结论正确的是（）BD
A. 最小值为2
11.
ABD
下列命题正确的是（）
A. 命题
15.
设集合A
(1) 若a = 1 求AnB和AUB;
(2）AUB=A，求实数α的取值范围.
若 a=1 则交集为某区间
"""
    questions = [
        {"question_no": 1, "type_code": "single_choice"},
        {"question_no": 2, "type_code": "single_choice"},
        {"question_no": 10, "type_code": "multi_choice"},
        {"question_no": 11, "type_code": "multi_choice"},
        {"question_no": 15, "type_code": "solution"},
    ]
    got = parse_answers_in_order(text, questions)
    assert 1 not in got
    assert "若a" not in got.get(1, "")
    assert got[2] == "C"
    assert got[10] == "BD"
    assert got[11] == "ABD"
    assert "求AnB" not in got.get(15, "")
    assert "交集" in got[15]


def test_choice_written_inside_parentheses():
    text = """
1.
函数(a)=x的定义域为（D）
A. [2, +00]
B. [2, 3]
2.
则cos2α =（C）
A. 1
5.
最小值是（A
A.8
B. 6
8.
m的取值范围为（BD）
A. 范围
"""
    questions = [
        {"question_no": 1, "type_code": "single_choice"},
        {"question_no": 2, "type_code": "single_choice"},
        {"question_no": 5, "type_code": "single_choice"},
        {"question_no": 8, "type_code": "multi_choice"},
    ]
    got = parse_answers_in_order(text, questions)
    assert got[1] == "D"
    assert got[2] == "C"
    assert got[5] == "A"
    assert got[8] == "BD"


def test_fill_answer_overlapping_blank():
    text = """
12.
若幂函数为偶函数，则m=
2
14.
圆心为O
外接圆的半径是2，则该图形的面积为（2π/3+2）
"""
    questions = [
        {"question_no": 12, "type_code": "fill_blank", "answer_md": "$2$", "score": 5},
        {
            "question_no": 14,
            "type_code": "fill_blank",
            "answer_md": r"$\frac { 2 } { 3 }\pi+2$",
            "score": 5,
        },
    ]
    got = parse_answers_in_order(text, questions)
    assert got[12] == "2"
    assert "π" in got[14] or "2" in got[14]
    report = grade_paper(questions, got)
    assert report["items"][0]["is_correct"] is True
    assert report["items"][1]["is_correct"] is True
    assert normalize_blank(r"2π/3+2") == normalize_blank(r"$\frac { 2 } { 3 }\pi+2$")


def test_same_row_handwriting_joins_the_blank():
    lines = join_reading_order(
        [
            {"text": "面积为", "x0": 10, "x1": 80, "y0": 40, "y1": 60, "y": 50},
            {"text": "2π/3+2", "x0": 90, "x1": 180, "y0": 42, "y1": 62, "y": 52},
            {"text": "15.", "x0": 10, "x1": 40, "y0": 100, "y1": 120, "y": 110},
        ]
    )
    assert lines[0]["text"] == "面积为 2π/3+2"
    assert lines[1]["text"] == "15."


def test_snippet_reads_formula_and_letter():
    from word_math_md.sheet_grade import answer_from_snippet

    assert answer_from_snippet("（2π/3+2）", "fill_blank")
    assert answers_match(
        "fill_blank",
        r"$\frac { 2 } { 3 }\pi+2$",
        answer_from_snippet("2π/3+2", "fill_blank"),
    )[0]
    assert answer_from_snippet("（D）", "single_choice") == "D"


def test_page_reader_fills_formula_without_replacing_choice_letters():
    from word_math_md.sheet_ocr import _merge_page_answers

    questions = [
        {"question_no": 2, "type_code": "single_choice"},
        {"question_no": 14, "type_code": "fill_blank"},
    ]
    ordered = {2: "C", 14: "圆心"}
    page = {2: "A", 14: r"\frac{2}{3}\pi+2"}
    got = _merge_page_answers(ordered, page, questions)
    assert got[2] == "C"
    assert got[14].startswith("\\frac")


def test_formula_choice_prefers_chinese_model_unless_it_is_not_math():
    from word_math_md.formula_ocr import choose_formula

    assert choose_formula(r"\frac{2}{3}\pi+2", r"\frac{2}{3}\pi+2").startswith("\\frac")
    assert choose_formula("圆心为O", r"\frac{2}{3}\pi+2") == r"\frac{2}{3}\pi+2"
    assert choose_formula(r"\frac{2}{3}\pi+2", "2\\pi/3+2").startswith("\\frac")


def test_vision_json_answers():
    text = '```json\n{"answers":[{"no":1,"answer":"B"},{"no":2,"answer":"1/2"}]}\n```'
    got = _answers_from_vision_text(text)
    assert got == {1: "B", 2: "1/2"}
