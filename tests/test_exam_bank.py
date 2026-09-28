import re

from word_math_md.exam_bank import (
    delete_paper,
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


def test_parse_scores_from_type_headers_and_item_notes():
    md = """# 模拟卷

一、选择题：本题共2小题，每小题5分，共10分.只有一个选项符合题目要求.

1. 已知 $a>0$
A. $1$
B. $2$
【答案】A

2. 下列正确的是
A. 甲
B. 乙
【答案】A

二、填空题：本题共1小题，每小题5分，共5分.

3. 空格填 ______ 。
【答案】$3$

三、解答题：本题共2小题，共20分.解答应写出文字说明.

4. （12分）证明：三角形内角和为 $180^\\circ$。
【详解】延长并作平行线。

5. 计算 $1+1$。
【详解】$2$
"""
    paper = parse_markdown_paper(md, filename="score.md")
    assert [q.score for q in paper.questions] == [5.0, 5.0, 5.0, 12.0, 8.0]


def test_parse_scores_from_numbered_range():
    md = """第1～2题每小题4分。第3题8分。

1. 题一
A. 1
B. 2
【答案】A

2. 题二
A. 1
B. 2
【答案】B

3. 证明本题。
【详解】略
"""
    paper = parse_markdown_paper(md, filename="range.md")
    assert [q.score for q in paper.questions] == [4.0, 4.0, 8.0]


def test_parse_keeps_exam_header_out_of_first_stem():
    md = """深圳实验学校高中部2023-2024学年度第一学期第二阶段考试

高一数学

时间：120分钟 满分：150分

考生注意：答题前请认真阅读。

一、选择题（本大题共1小题，每小题5分，共5分）

1. 已知 $a>0$（5分）
A. $1$
B. $2$
【答案】A
"""
    paper = parse_markdown_paper(md, filename="深圳实验.md")
    stem = paper.questions[0].stem_md
    assert "已知" in stem
    assert "深圳实验学校" not in stem
    assert "120分钟" not in stem
    assert "满分：150分" not in stem
    assert paper.questions[0].score == 5


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


class _FakeResult:
    def __init__(self, data=None):
        self.data = data or []


class _FakeStorage:
    def __init__(self):
        self.removed = []

    def from_(self, _bucket):
        return self

    def remove(self, keys):
        self.removed.extend(keys)
        return {"data": list(keys)}


class _FakeQuery:
    def __init__(self, client, name):
        self.client = client
        self.name = name
        self._eq = {}
        self._in = {}
        self._delete = False

    def select(self, *_a, **_k):
        return self

    def eq(self, key, value):
        self._eq[key] = value
        return self

    def in_(self, key, values):
        self._in[key] = list(values)
        return self

    def limit(self, _n):
        return self

    def delete(self):
        self._delete = True
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.name, [])
        if self._delete:
            if self._eq:
                key, value = next(iter(self._eq.items()))
                self.client.tables[self.name] = [row for row in rows if row.get(key) != value]
            elif self._in:
                key, values = next(iter(self._in.items()))
                keep = set(values)
                self.client.tables[self.name] = [row for row in rows if row.get(key) not in keep]
            else:
                self.client.tables[self.name] = []
            self.client.deletes.append(self.name)
            return _FakeResult([])
        filtered = rows
        for key, value in self._eq.items():
            filtered = [row for row in filtered if row.get(key) == value]
        return _FakeResult(list(filtered))


class _FakeClient:
    def __init__(self, tables):
        self.tables = tables
        self.deletes = []
        self.storage = _FakeStorage()

    def table(self, name):
        return _FakeQuery(self, name)


def test_delete_paper_removes_questions_and_paper(monkeypatch):
    paper_id = "11111111-1111-1111-1111-111111111111"
    q1 = "22222222-2222-2222-2222-222222222222"
    q2 = "33333333-3333-3333-3333-333333333333"
    client = _FakeClient(
        {
            "papers": [{"id": paper_id, "paper_code": "demo", "title": "测试卷"}],
            "questions": [
                {"id": q1, "paper_id": paper_id},
                {"id": q2, "paper_id": paper_id},
            ],
            "question_options": [{"question_id": q1, "label": "A"}],
            "question_knowledge_points": [{"question_id": q1, "knowledge_code": "1.1"}],
            "answer_sheets": [{"id": "s1", "paper_id": paper_id}],
            "answer_sheet_items": [{"question_id": q1, "sheet_id": "s1"}],
            "assets": [{"paper_id": paper_id, "storage_key": "demo/a.png"}],
        }
    )
    monkeypatch.setattr("word_math_md.exam_bank._client", lambda: client)
    out = delete_paper(paper_id)
    assert out["paper_id"] == paper_id
    assert out["title"] == "测试卷"
    assert out["question_count"] == 2
    assert out["asset_count"] == 1
    assert client.tables["papers"] == []
    assert client.tables["questions"] == []
    assert client.tables["question_options"] == []
    assert client.tables["question_knowledge_points"] == []
    assert client.tables["answer_sheets"] == []
    assert client.tables["answer_sheet_items"] == []
    assert client.tables["assets"] == []
    assert "demo/a.png" in client.storage.removed


def test_delete_paper_rejects_missing_and_invalid_ids(monkeypatch):
    client = _FakeClient({"papers": []})
    monkeypatch.setattr("word_math_md.exam_bank._client", lambda: client)
    try:
        delete_paper("not-a-uuid")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "无效" in str(exc)
    try:
        delete_paper("11111111-1111-1111-1111-111111111111")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "不存在" in str(exc)
