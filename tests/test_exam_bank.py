from word_math_md.exam_bank import extract_options, guess_type, parse_markdown_paper


SAMPLE = """# 测试卷

1. 已知 $a>0$（5分）
A. $1$
B. $2$
C. $3$
D. $4$
【答案】A
【分析】比较大小即可。
【详解】选 A。

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


def test_extract_options_keeps_stem():
    stem, options = extract_options("已知函数\nA. 1\nB. 2\nC. 3\nD. 4\n")
    assert stem == "已知函数"
    assert [o.content_md for o in options] == ["1", "2", "3", "4"]


def test_guess_type_multi():
    _, options = extract_options("题\nA. 1\nB. 2\nC. 3\nD. 4\n")
    assert guess_type("题", "BD", options) == "multi_choice"
