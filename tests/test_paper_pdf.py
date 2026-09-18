from word_math_md.paper_pdf import paper_stem_html, pdf_filename


def test_stem_html_omits_answers_and_analysis():
    html = paper_stem_html(
        {
            "paper": {"title": "期末卷", "semester": "高三", "exam_type": "期末"},
            "questions": [
                {
                    "index": 1,
                    "stemHtml": "<p>题干A</p>",
                    "answerHtml": "<p>不该出现的答案</p>",
                    "analysisHtml": "<p>不该出现的分析</p>",
                    "detailHtml": "<p>不该出现的详解</p>",
                }
            ],
        }
    )
    assert "题干A" in html
    assert "期末卷" in html
    assert "不该出现的答案" not in html
    assert "不该出现的分析" not in html
    assert "不该出现的详解" not in html
    assert "【答案】" not in html


def test_pdf_filename_strips_unsafe_chars():
    assert pdf_filename('高三/期末:卷').endswith(".pdf")
    assert "/" not in pdf_filename('高三/期末:卷')
    assert ":" not in pdf_filename('高三/期末:卷')
