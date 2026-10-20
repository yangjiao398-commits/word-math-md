import json

from word_math_md.question_variant import VARIANT_SYSTEM, infer_point, variant_question

Q1 = {
    "id": "ac94d186-2233-4a03-ae46-88e390073595",
    "stem_md": (
        "**注意事项：**\n\n答卷前填写答题卡。\n\n"
        r"命题$p$：“$\forall x\in \left[ 0,2 \right]$，$x^{2}+1\ge 1$”，则$p$的否定是（ ）"
    ),
    "answer_md": "D",
    "options": [],
    "knowledge_points": [{"minor_category": "全称量词与存在量词"}],
}

Q3 = {
    "id": "d793894c-ce81-4d98-9f85-a98f435c1ea4",
    "type_code": "single_choice",
    "stem_md": r"不等式$ax ^ { 2 } +bx-3 < 0$的解集是$\left ( { -\infty ,1 } \right )\cup \left ( { 3,+\infty  } \right )$，则$b-a$的值是（ ）",
    "answer_md": "D",
    "options": [
        {"label": "A", "content_md": "$-3$"},
        {"label": "B", "content_md": "$3$"},
        {"label": "C", "content_md": "$-5$"},
        {"label": "D", "content_md": "$5$"},
    ],
}

Q2 = {
    "id": "piecewise-q2",
    "stem_md": r"已知函数$f\left ( { x } \right )=\left \{ \begin{array}{l} x ^ { 2 } -1,x\le 1, \\ \frac { 1 } { x-1 },x>1, \end{array} \right.$则$f\left ( { f\left ( { 3 } \right ) } \right )=$（ ）",
    "answer_md": "B",
}

Q7 = {
    "id": "fraction-q7",
    "stem_md": r"已知函数$f\left ( { x } \right )=\frac { \pi ^ { x } -1 } { \pi ^ { x } +1 }$，若对任意的正数$a$，$b$，满足$f\left ( { a } \right )+f\left ( { 2b-1 } \right )=0$，则$\frac { 2 } { a }+\frac { 1 } { b }$的最小值为（ ）",
    "answer_md": "D",
}

Q12 = {
    "id": "value-q12",
    "stem_md": r"求值：$8 ^ { \frac { 1 } { 3 } } +lg100+2 ^ { 1+\log_{{2}}  3 } =$__________.",
    "answer_md": "10",
}

Q4 = {
    "id": "98b36f23-686b-4865-9dcf-ccf4f5ddc3c8",
    "stem_md": (
        r"角$\alpha $的终边经过点$P\left ( { { \rm{ s } }{ \rm{ i } }{ \rm{ n } }\frac { 5\pi } { 3 },"
        r"{ \rm{ c } }{ \rm{ o } }{ \rm{ s } }\frac { 5\pi } { 3 } } \right )$，"
        r"则${ \rm{ s } }{ \rm{ i } }{ \rm{ n } }\left ( { \pi+\alpha  } \right )=$（ ）"
    ),
    "answer_md": "B",
    "analysis_md": "利用诱导公式及三角函数定义计算即得.",
}

Q13 = {
    "id": "sector-q13",
    "stem_md": r"已知扇形的圆心角$\alpha =\frac { 2 } { 3 }\pi$，所对的弦长为$2\sqrt{ 3 }$，则弧长等于__________．（结果用弧度制表示）",
    "answer_md": r"\frac{4\pi}{3}",
}


def _compact(text: str) -> str:
    return text.replace(" ", "").replace(r"\left", "").replace(r"\right", "").replace(r"\dfrac", r"\frac")


def test_prompt_varies_the_base_instead_of_inventing_a_new_item() -> None:
    assert "真题底本" in VARIANT_SYSTEM
    assert "数据" in VARIANT_SYSTEM and "背景" in VARIANT_SYSTEM and "问法" in VARIANT_SYSTEM
    assert "重新计算" in VARIANT_SYSTEM
    assert "不要" in VARIANT_SYSTEM and "誊抄" in VARIANT_SYSTEM


def test_local_shape_does_not_call_the_model() -> None:
    def complete(system: str, user: str) -> str:
        raise AssertionError("local shape must not call the model")

    result = variant_question(Q3, complete=complete)
    assert result["supported"] is True
    assert result["source"] == "local"
    assert "bx-3" not in _compact(result["stem_md"])


def test_model_variant_is_rejected_when_it_copies_the_base() -> None:
    row = {
        "id": "conic-copy",
        "stem_md": "已知椭圆 $C:\\dfrac{x^{2}}{4}+y^{2}=1$，求证某条弦的斜率为定值。",
        "answer_md": "1",
        "analysis_md": "圆锥曲线定值",
        "solution_md": "联立后韦达。",
    }

    def complete(system: str, user: str) -> str:
        assert "真题底本" in system
        assert "椭圆" in user
        return json.dumps(
            {
                "point": "圆锥曲线中的定值问题",
                "essence": "同一考点",
                "axis": "数据",
                "changes": ["没有真正修改"],
                "stem_md": row["stem_md"],
                "options": [],
                "answer": "1",
                "analysis_md": "同底本",
                "solution_md": "联立后韦达。",
            },
            ensure_ascii=False,
        )

    result = variant_question(row, complete=complete)
    assert result["supported"] is False
    assert result["rejected"] is True
    assert "过于接近" in result["message"]


def test_model_variant_is_used_when_it_really_changes_the_base() -> None:
    def complete(system: str, user: str) -> str:
        return json.dumps(
            {
                "point": "利用导数求单调区间",
                "essence": "仍用导数判断单调性，但函数和区间都换了。",
                "axis": "数据、问法",
                "changes": ["f(x)=x^3-3x 改为 f(x)=x^3-12x", "求单调递增区间改为求单调递减区间"],
                "stem_md": r"求函数 $f(x)=x^{3}-12x$ 的单调递减区间。",
                "options": [],
                "answer": r"(-\infty,-2]\cup[2,+\infty)",
                "analysis_md": "求导后看 f'(x) 的符号。",
                "solution_md": r"$f'(x)=3x^{2}-12=3(x-2)(x+2)$。单调递减区间是 $(-\infty,-2]\cup[2,+\infty)$。",
            },
            ensure_ascii=False,
        )

    row = {
        "id": "derivative",
        "stem_md": r"求函数 $f(x)=x^{3}-3x$ 的单调递增区间。",
        "answer_md": r"(-\infty,-1],[1,+\infty)",
        "analysis_md": "求导。",
        "solution_md": "f'(x)=3x^2-3。",
    }
    result = variant_question(row, complete=complete)
    assert result["supported"] is True
    assert result["source"] == "model"
    assert result["point"] == "利用导数求单调区间"
    assert "12x" in result["stem_md"]
    assert "x^{3}-3x" not in result["stem_md"]
    assert "递减" in result["solution_md"]


def test_model_retries_when_the_solution_contradicts_the_choices() -> None:
    calls = {"n": 0}

    def complete(system: str, user: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(
                {
                    "point": "集合关系",
                    "essence": "同一考点",
                    "axis": "数据",
                    "changes": ["改了数字"],
                    "stem_md": r"已知集合 $M=\{(x,y)\mid x+y=4\}$，则 $M\cap N=$（ ）",
                    "options": [{"label": "A", "content_md": r"$(1,3)$"}, {"label": "B", "content_md": r"$(2,2)$"}],
                    "answer": "A",
                    "analysis_md": "联立。",
                    "solution_md": "算出的交点不在选项中，需重新核对。",
                },
                ensure_ascii=False,
            )
        assert "上一次结果不能用" in user
        return json.dumps(
            {
                "point": "集合关系",
                "essence": "仍由两组交点反推直线参数。",
                "axis": "数据",
                "changes": ["常数改为 4"],
                "stem_md": r"已知集合 $P=\{(x,y)\mid x+y=4\}$，求 $P$ 与直线 $x-y=0$ 的交集。",
                "options": [{"label": "A", "content_md": r"$(2,2)$"}, {"label": "B", "content_md": r"$(1,3)$"}],
                "answer": "A",
                "analysis_md": "联立两个方程。",
                "solution_md": r"由 $x+y=4$ 与 $x-y=0$ 得 $x=2,y=2$，所以交集为 $(2,2)$，故选 A。",
            },
            ensure_ascii=False,
        )

    result = variant_question(
        {
            "id": "set-retry",
            "stem_md": r"已知集合 $M=\{(x,y)\mid ax-by=1\}$，求交集。",
            "answer_md": "A",
            "analysis_md": "集合",
            "solution_md": "联立。",
        },
        complete=complete,
    )
    assert calls["n"] == 2
    assert result["supported"] is True
    assert result["source"] == "model"
    assert "(2,2)" in result["solution_md"]


def test_q1_variant_keeps_the_negation_rule_and_drops_the_paper_header() -> None:
    result = variant_question(Q1)
    assert result["source"] == "local"
    assert result["point"] == "全称量词与存在量词"
    assert "数据" in result["axis"]
    assert "注意事项" not in result["stem_md"]
    assert "答题卡" not in result["stem_md"]
    assert r"\forall" in result["stem_md"]
    assert "x^{2}+1" not in _compact(result["stem_md"])
    correct = next(item for item in result["options"] if item["label"] == result["answer"])
    assert r"\exists" in correct["content_md"]
    assert r"\in" in correct["content_md"]
    assert result["answer"] != "D"


def test_q3_variant_recomputes_b_minus_a() -> None:
    result = variant_question(Q3)
    assert result["supported"] is True
    assert "根与系数" in result["essence"]
    stem = _compact(result["stem_md"])
    assert "bx-3" not in stem
    assert r"(-\infty,1)\cup(3,+\infty)" not in stem
    answer = next(item["content_md"] for item in result["options"] if item["label"] == result["answer"])
    assert answer.strip("$") in result["solution_md"]
    assert result["answer"] != "D"
    assert "深圳" not in result["solution_md"]


def test_q4_terminal_side_variant_recomputes_the_sine() -> None:
    result = variant_question(Q4)
    assert result["supported"] is True
    assert result["source"] == "local"
    assert result["point"] == "三角函数定义与诱导公式"
    assert "数据" in result["axis"]
    stem = _compact(result["stem_md"])
    assert r"\frac{11\pi}{6}" in stem
    assert r"\frac{5\pi}{3}" not in stem
    assert result["answer"] != "B"
    correct = next(item["content_md"] for item in result["options"] if item["label"] == result["answer"])
    assert r"-\frac{\sqrt{3}}{2}" in _compact(correct)
    assert r"-\frac{\sqrt{3}}{2}" in _compact(result["solution_md"])
    assert r"\frac{y}{r}" in result["solution_md"] or "y}{r}" in result["solution_md"]
    assert f"故选：{result['answer']}" in result["solution_md"]
    assert "DASHSCOPE_API_KEY" not in result.get("message", "")


def test_other_local_shapes_change_numbers_and_recompute() -> None:
    piecewise = variant_question(Q2)
    assert r"-\dfrac{35}{4}" in piecewise["solution_md"] or r"-\frac{35}{4}" in piecewise["solution_md"]
    assert "f(f(3))" not in _compact(piecewise["stem_md"])

    minimum = variant_question(Q7)
    assert "12" in minimum["solution_md"]
    assert r"3^{x}" in minimum["stem_md"]
    assert r"\pi" not in minimum["stem_md"]

    value = variant_question(Q12)
    assert value["answer"] == "12"
    assert "求值" not in value["stem_md"]
    assert "27" in value["stem_md"]

    sector = variant_question(Q13)
    assert sector["answer"] == r"\pi"
    assert "扇形窗" in sector["stem_md"]
    assert r"2\sqrt{3}" not in sector["stem_md"] and r"2\sqrt{ 3 }" not in sector["stem_md"]


def test_unrecognized_question_names_the_point_and_asks_for_a_model() -> None:
    result = variant_question(
        {
            "id": "conic",
            "stem_md": "已知椭圆 $C:\\dfrac{x^{2}}{4}+y^{2}=1$，求证某条弦的斜率为定值。",
            "answer_md": "1",
            "analysis_md": "圆锥曲线定值",
            "solution_md": "联立后韦达。",
        }
    )
    assert result["supported"] is False
    assert "定值" in result["point"]
    assert "DEEPSEEK_API_KEY" in result["message"]
    assert infer_point("求函数的导数并判断单调区间") == "利用导数求单调区间"
