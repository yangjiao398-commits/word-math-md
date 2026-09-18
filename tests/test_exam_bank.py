import re

from word_math_md.exam_bank import (
    PAPER_EXAM_TYPES,
    PAPER_GAOKAO_PAPERS,
    PAPER_PROVINCES,
    PAPER_SEMESTERS,
    _storage_prefix,
    extract_options,
    guess_type,
    normalize_gaokao_paper,
    normalize_paper_exam_type,
    normalize_paper_province,
    normalize_paper_semester,
    parse_knowledge_points,
    parse_markdown_paper,
    questions_to_markdown,
)


SAMPLE = """# 测试卷

1. 已知 $a>0$（5分）
A. $1$
B. $2$
C. $3$
D. $4$
【答案】A
【分析】比较大小即可。
【详解】选 A。
【知识点】1.1 集合的含义；1.2 集合间的基本关系

2. 下列正确的是（多选）
A. 甲
B. 乙
C. 丙
D. 丁
【答案】A、C
【详解】甲和丙正确。

3. 空格填 ______ 。
【答案】$3$

4. 证明：三角形内角和为 $180^\\circ$。
【详解】延长并作平行线。
"""


def test_paper_meta_allowed_values():
    assert normalize_paper_semester("高二下学期") == "高二下学期"
    assert normalize_paper_semester("  ") == ""
    assert normalize_paper_exam_type("期中") == "期中"
    assert normalize_paper_exam_type("") == ""
    try:
        normalize_paper_semester("高四")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    try:
        normalize_paper_exam_type("周测")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert len(PAPER_SEMESTERS) == 6
    assert PAPER_EXAM_TYPES == ("月考", "期中", "期末")
    assert normalize_paper_province("广东省") == "广东"
    assert normalize_paper_province("内蒙古自治区") == "内蒙古"
    assert normalize_paper_province("") == ""
    assert normalize_gaokao_paper("全国甲卷") == "全国A卷"
    assert normalize_gaokao_paper("乙卷") == "全国B卷"
    assert normalize_gaokao_paper("  ") == ""
    try:
        normalize_paper_province("加州")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    try:
        normalize_gaokao_paper("新高考I卷")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert len(PAPER_PROVINCES) == 31
    assert PAPER_GAOKAO_PAPERS == ("全国A卷", "全国B卷")


def test_parse_questions_in_order():
    paper = parse_markdown_paper(SAMPLE, filename="测试卷.md", paper_code="T-01")
    assert paper.paper_code == "T-01"
    assert [q.question_no for q in paper.questions] == [1, 2, 3, 4]
    assert paper.questions[0].type_code == "single_choice"
    assert paper.questions[0].score == 5
    assert [o.label for o in paper.questions[0].options] == ["A", "B", "C", "D"]
    assert paper.questions[1].type_code == "multi_choice"
    assert paper.questions[2].type_code == "fill_blank"
    assert paper.questions[3].type_code == "solution"
    assert "比较大小" in paper.questions[0].analysis_md
    assert "选 A" in paper.questions[0].solution_md
    assert [kp.code for kp in paper.questions[0].knowledge_points] == ["1.1", "1.2"]
    assert paper.questions[0].knowledge_points[0].description == "集合的含义"
    assert paper.questions[1].knowledge_points == []


def test_parse_knowledge_points_codes_only():
    items = parse_knowledge_points("2.1、2.3，3.1")
    assert [kp.code for kp in items] == ["2.1", "2.3", "3.1"]
    assert all(kp.description == "" for kp in items)


def test_extract_options_keeps_stem():
    stem, options = extract_options("已知函数\nA. 1\nB. 2\nC. 3\nD. 4\n")
    assert stem == "已知函数"
    assert [o.content_md for o in options] == ["1", "2", "3", "4"]


def test_guess_type_multi():
    _, options = extract_options("题\nA. 1\nB. 2\nC. 3\nD. 4\n")
    assert guess_type("题", "BD", options) == "multi_choice"


def test_storage_prefix_is_ascii():
    key = _storage_prefix("精品解析-广东省深圳联盟校2023-2024学年高一上学期期中数学试题-解析版-ole-latex-preprocessed")
    assert key.isascii()
    assert "/" not in key
    assert re.fullmatch(r"[A-Za-z0-9._-]+", key)
    assert key == _storage_prefix("精品解析-广东省深圳联盟校2023-2024学年高一上学期期中数学试题-解析版-ole-latex-preprocessed")


def test_guess_type_fill_blank_escaped_underscores():
    stem = r"则 $f(2)=$\_\_\_\_\_\_\_\_\_\_\_."
    assert guess_type(stem, r"$\frac{3}{2}$", []) == "fill_blank"


def test_normalize_knowledge_codes():
    from word_math_md.exam_bank import normalize_knowledge_codes

    assert normalize_knowledge_codes(["1.1", "1.1", " 2.3 ", "", "bad code"]) == [
        "1.1",
        "2.3",
    ]
    assert normalize_knowledge_codes(None) == []
    assert len(normalize_knowledge_codes([f"1.{i}" for i in range(50)], limit=5)) == 5


def test_questions_to_markdown_roundtrip_markers():
    md = questions_to_markdown(
        [
            {
                "question_no": 1,
                "stem_md": "已知 $a>0$",
                "options": [
                    {"label": "A", "content_md": "$1$"},
                    {"label": "B", "content_md": "$2$"},
                ],
                "answer_md": "A",
                "analysis_md": "比较即可",
                "solution_md": "选 A",
                "knowledge_points": [{"code": "1.1", "description": "集合"}],
            }
        ]
    )
    assert md.startswith("1. 已知")
    assert "A. $1$" in md
    assert "【答案】A" in md
    assert "【分析】比较即可" in md
    assert "【详解】选 A" in md
    assert "【知识点】1.1 集合" in md
