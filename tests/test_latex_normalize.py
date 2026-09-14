"""Word/MathType set-builder LaTeX should render via KaTeX."""

from pathlib import Path

from word_math_md.gaokao_docx_convert import _run_tsx, parse_markdown_like_gaokao

ROOT = Path(__file__).resolve().parent.parent


def test_word_set_builder_renders_with_katex():
    _run_tsx(ROOT / "tests" / "test_latex_normalize.mts")


def test_parse_broken_set_builder_markdown():
    data = parse_markdown_like_gaokao(
        ROOT / "tests" / "fixtures" / "set_builder_broken.md"
    )
    assert data["questions"], data.get("warnings")
    html = data["questions"][0]["stemHtml"]
    assert "katex" in html
    assert "katex-error" not in html
    assert "已知集合$" not in html


def test_adjacent_dollars_do_not_swallow_later_questions():
    data = parse_markdown_like_gaokao(
        ROOT / "tests" / "fixtures" / "q11_swallowed_answers.md"
    )
    by_no = {q["index"]: q for q in data["questions"]}
    assert 11 in by_no and 12 in by_no and 13 in by_no
    ans = by_no[11]["answerHtml"]
    assert "BD" in ans
    assert "[0,1]" not in ans
    assert "7+4" not in ans
