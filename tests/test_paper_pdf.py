from word_math_md.paper_pdf import paper_stem_html, pdf_filename


def test_stem_html_omits_answers_and_analysis():
    html = paper_stem_html(
        {
            "paper": {"title": "期末卷", "semester": "高三", "exam_type": "期末"},
            "questions": [
                {
                    "index": 1,
                    "score": 5,
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
    assert "（5分）" in html
    assert "不该出现的答案" not in html
    assert "不该出现的分析" not in html
    assert "不该出现的详解" not in html
    assert "【答案】" not in html


def test_stem_html_puts_exam_header_above_questions():
    html = paper_stem_html(
        {
            "paper": {"title": "入库试卷标题", "semester": "高一上学期"},
            "headerHtml": (
                "<p>深圳实验学校高中部2023-2024学年度第一学期第二阶段考试</p>"
                "<p>高一数学</p>"
                "<p>时间：120分钟 满分：150分</p>"
            ),
            "questions": [
                {
                    "index": 1,
                    "score": 5,
                    "stemHtml": "<p>已知集合</p>",
                }
            ],
        }
    )
    title_at = html.find("入库试卷标题")
    header_at = html.find("深圳实验学校高中部")
    stem_at = html.find("已知集合")
    assert 0 <= title_at < header_at < stem_at
    assert "paper-masthead" in html
    assert html.count("深圳实验学校高中部") == 1


def test_stem_html_groups_questions_by_type_section():
    html = paper_stem_html(
        {
            "paper": {"title": "阶段考"},
            "sections": [
                {
                    "title": "一、单项选择题：本题共1小题，每小题5分，共5分.",
                    "titleHtml": "<p>一、单项选择题：本题共1小题，每小题5分，共5分.</p>",
                    "questionIndexes": [1],
                },
                {
                    "title": "四、解答题:本题共1小题，共10分.",
                    "titleHtml": "<p>四、解答题:本题共1小题，共10分.</p>",
                    "questionIndexes": [2],
                },
            ],
            "questions": [
                {"index": 1, "score": 5, "stemHtml": "<p>单选题干</p>", "type_code": "single_choice"},
                {"index": 2, "score": 10, "stemHtml": "<p>解答题干</p>", "type_code": "solution"},
            ],
        }
    )
    choice_at = html.find("一、单项选择题")
    q1_at = html.find("单选题干")
    solution_at = html.find("四、解答题")
    q2_at = html.find("解答题干")
    assert 0 <= choice_at < q1_at < solution_at < q2_at
    assert "paper-section" in html


def test_pdf_filename_strips_unsafe_chars():
    assert pdf_filename('高三/期末:卷').endswith(".pdf")
    assert "/" not in pdf_filename('高三/期末:卷')
    assert ":" not in pdf_filename('高三/期末:卷')
