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
    assert "\\\\frac" in VARIANT_SYSTEM


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


def test_changed_numbers_are_not_treated_as_a_copy_of_the_skeleton() -> None:
    base_stem = (
        r"已知集合 $A=\{x\mid m-1\le x\le 2m\}$，函数 $f(x)=\sqrt{-x^{2}+2x+8}$ 的定义域为 $B$。"
        "（1）求 $B$；（2）若集合 $A$ 是集合 $B$ 的子集，求实数 $m$ 的取值范围。"
    )
    stem = (
        r"已知集合 $A=\{x\mid 2m-3\le x\le m+1\}$，函数 $g(x)=\sqrt{-x^2+4x+12}$ 的定义域为 $B$。"
        "（1）求 $B$；（2）若 $A\\subseteq B$，求 $m$ 的取值集合。"
    )

    def complete(system: str, user: str) -> str:
        return json.dumps(
            {
                "point": "定义域与集合的包含关系",
                "essence": "先求根式定义域，再讨论参数区间是否含于该定义域。",
                "axis": "数据",
                "changes": ["更换二次式和区间端点"],
                "stem_md": stem,
                "options": [],
                "answer": r"$\left[\frac12,+\infty\right)$",
                "analysis_md": "分空集和非空集。",
                "solution_md": r"合并后得 $m\ge \frac12$，即 $\left[\frac12,+\infty\right)$。答案：$\left[\frac12,+\infty\right)$",
            },
            ensure_ascii=False,
        )

    result = variant_question(
        {
            "id": "sz-q15-skeleton",
            "type_code": "solution",
            "stem_md": base_stem,
            "answer_md": r"$(-\infty,2]$",
            "analysis_md": "定义域与子集。",
            "solution_md": "",
        },
        complete=complete,
    )
    assert result["supported"] is True
    assert result["source"] == "model"
    assert "4x+12" in result["stem_md"]


def test_twelve_consecutive_hanzi_still_counts_as_a_copy() -> None:
    phrase = "先写出定义域再讨论子集关系"

    def complete(system: str, user: str) -> str:
        return json.dumps(
            {
                "point": "集合关系",
                "essence": "同一句话搬过来。",
                "axis": "数据",
                "changes": ["数字改了但句子没改"],
                "stem_md": f"计算 $x+3$。{phrase}。",
                "options": [],
                "answer": "5",
                "analysis_md": "相加。",
                "solution_md": f"{phrase}。$2+3=5$。",
            },
            ensure_ascii=False,
        )

    result = variant_question(
        {
            "id": "hanzi-copy",
            "stem_md": f"计算 $x+1$。{phrase}。",
            "answer_md": "3",
            "analysis_md": "相加。",
            "solution_md": "2+1=3。",
        },
        complete=complete,
    )
    assert result["supported"] is False
    assert result["rejected"] is True


def test_copied_variant_is_resent_with_the_overlapping_phrase() -> None:
    phrase = "上的单调性并用定义加以证明"
    calls = {"n": 0}

    def complete(system: str, user: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(
                {
                    "point": "函数的单调性",
                    "essence": "原句没改。",
                    "axis": "数据",
                    "changes": ["只换了数字"],
                    "stem_md": f"已知幂函数 $y=x^{{a}}$。{phrase}。",
                    "options": [],
                    "answer": r"$\dfrac{1}{x}$",
                    "analysis_md": "代入点。",
                    "solution_md": r"解得指数为 $-1$，所以 $\dfrac{1}{x}$。答案：$\dfrac{1}{x}$",
                },
                ensure_ascii=False,
            )
        assert "上一次结果不能用" in user
        assert phrase[:12] in user
        return json.dumps(
            {
                "point": "函数的单调性",
                "essence": "仍由幂函数上的点求指数，再用定义讨论增减。",
                "axis": "数据、问法",
                "changes": ["点改为 (2,1/2)", "问法改为说明增减，不再照抄原句"],
                "stem_md": r"幂函数 $y=x^{a}$ 的图象过点 $\left(2,\dfrac{1}{2}\right)$。求出解析式，并说明它在 $(0,4)$ 上的增减情况。",
                "options": [],
                "answer": r"$\dfrac{1}{x}$",
                "analysis_md": "由点确定指数。",
                "solution_md": r"$2^{a}=\dfrac{1}{2}$，所以 $a=-1$，$y=\dfrac{1}{x}$。答案：$\dfrac{1}{x}$",
            },
            ensure_ascii=False,
        )

    result = variant_question(
        {
            "id": "q16-copy",
            "stem_md": f"判断函数在区间上的{phrase}。",
            "answer_md": r"$\dfrac{1}{x}$",
            "analysis_md": "幂函数。",
            "solution_md": "代入。",
        },
        complete=complete,
    )
    assert calls["n"] == 2
    assert result["supported"] is True
    assert result["source"] == "model"
    assert phrase not in result["stem_md"]
    assert r"\dfrac{1}{2}" in result["stem_md"]


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


def test_model_repairs_a_solution_that_contradicts_the_choices() -> None:
    calls = {"n": 0}
    stem = r"已知集合 $M=\{(x,y)\mid x+y=4\}$，则 $M\cap N=$（ ）"

    def complete(system: str, user: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(
                {
                    "point": "集合关系",
                    "essence": "同一考点",
                    "axis": "数据",
                    "changes": ["改了数字"],
                    "stem_md": stem,
                    "options": [{"label": "A", "content_md": r"$(1,3)$"}, {"label": "B", "content_md": r"$(2,2)$"}],
                    "answer": "A",
                    "analysis_md": "联立。",
                    "solution_md": "算出的交点不在选项中，需重新核对。",
                },
                ensure_ascii=False,
            )
        assert "不要另出一题" in system
        assert stem in user
        assert "上一次结果不能用" not in user
        return json.dumps(
            {
                "stem_md": "另一道题",
                "options": [{"label": "A", "content_md": r"$(1,3)$"}, {"label": "B", "content_md": r"$(2,2)$"}],
                "answer": "A",
                "analysis_md": "按题干联立。",
                "solution_md": r"由题干得交集为 $(1,3)$。答案：A",
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
    assert result["stem_md"] == stem
    assert "(1,3)" in result["solution_md"]
    assert "不在选项" not in result["solution_md"]


def test_model_asks_for_a_new_variant_when_repair_stays_inconsistent() -> None:
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
                    "stem_md": r"求集合 $P=\{x\mid x>3\}$ 的一个真子集。",
                    "options": [{"label": "A", "content_md": r"$\{4\}$"}, {"label": "B", "content_md": r"$\{1\}$"}],
                    "answer": "A",
                    "analysis_md": "列举。",
                    "solution_md": "结果与选项不符，需调整题设数据。",
                },
                ensure_ascii=False,
            )
        if calls["n"] == 2:
            assert "不要另出一题" in system
            return json.dumps(
                {
                    "stem_md": "被忽略的题干",
                    "options": [{"label": "A", "content_md": r"$\{4\}$"}],
                    "answer": "A",
                    "analysis_md": "仍未对齐。",
                    "solution_md": "算出的元素不在选项中。",
                },
                ensure_ascii=False,
            )
        assert "上一次结果不能用" in user
        return json.dumps(
            {
                "point": "集合关系",
                "essence": "仍判断一个集合是否为真子集。",
                "axis": "数据",
                "changes": ["把下界改为 5"],
                "stem_md": r"求集合 $Q=\{x\mid x>5\}$ 的一个真子集。",
                "options": [{"label": "A", "content_md": r"$\{6\}$"}, {"label": "B", "content_md": r"$\{5\}$"}],
                "answer": "A",
                "analysis_md": "真子集取一个比下界大的元素。",
                "solution_md": r"$6>5$，所以 $\{6\}$ 是真子集。答案：A",
            },
            ensure_ascii=False,
        )

    result = variant_question(
        {
            "id": "set-second",
            "stem_md": r"求集合 $M=\{x\mid x>1\}$ 的一个真子集。",
            "answer_md": "A",
            "analysis_md": "集合",
            "solution_md": "列举。",
        },
        complete=complete,
    )
    assert calls["n"] == 3
    assert result["supported"] is True
    assert r"\{6\}" in result["solution_md"] or "{6}" in result["solution_md"]


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


def test_split_answer_parts_are_consistent_without_another_call() -> None:
    calls = {"n": 0}
    stem = r"设 $g(x)=\sqrt{-x^{2}+6x+7}$ 的定义域为 $D$。（1）写出 $D$；（2）求参数范围。"

    def complete(system: str, user: str) -> str:
        calls["n"] += 1
        return json.dumps(
            {
                "point": "定义域与集合的包含关系",
                "essence": "先求根式定义域，再求参数区间含于该定义域的范围。",
                "axis": "数据",
                "changes": ["更换了二次式和参数区间"],
                "stem_md": stem,
                "options": [],
                "answer": r"（1）$D=\{x\mid -1\le x\le 7\}$；（2）$(-\infty,-2)\cup\left[1,\dfrac{7}{2}\right]$",
                "analysis_md": "分空集和非空集讨论。",
                "solution_md": (
                    r"所以 $D=\{x\mid -1\le x\le 7\}$。"
                    "\n\n"
                    r"因此参数范围是 $(-\infty,-2)\cup\left[1,\dfrac{7}{2}\right]$。"
                ),
            },
            ensure_ascii=False,
        )

    result = variant_question(
        {
            "id": "sz-q15-consistent",
            "type_code": "solution",
            "stem_md": r"已知函数 $f(x)=\sqrt{-x^{2}+2x+8}$ 的定义域为 $B$，求参数范围。",
            "answer_md": r"（1）$B=[-2,4]$（2）$(-\infty,2]$",
            "analysis_md": "先求定义域，再讨论子集。",
            "solution_md": "",
        },
        complete=complete,
    )
    assert calls["n"] == 1
    assert result["supported"] is True
    assert result["source"] == "model"


def test_q15_model_repairs_an_answer_missing_from_the_solution() -> None:
    calls = {"n": 0}
    stem = r"设 $g(x)=\sqrt{-x^{2}+6x+7}$ 的定义域为 $D$。（1）写出 $D$；（2）求参数范围。"

    def complete(system: str, user: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(
                {
                    "point": "定义域与集合的包含关系",
                    "essence": "先求根式定义域，再求参数区间含于该定义域的范围。",
                    "axis": "数据",
                    "changes": ["更换了二次式和参数区间"],
                    "stem_md": stem,
                    "options": [],
                    "answer": r"（1）$D=\{x\mid -1\le x\le 7\}$；（2）$(-\infty,-2)\cup\left[1,\dfrac{7}{2}\right]$",
                    "analysis_md": "发现和题干不一致，需重新核对。",
                    "solution_md": r"算出定义域是 $[-2,4]$，参数范围是 $(-\infty,2]$。",
                },
                ensure_ascii=False,
            )
        assert "不要另出一题" in system
        assert stem in user
        return json.dumps(
            {
                "stem_md": "不要采用这道新题",
                "options": [],
                "answer": r"（1）$D=\{x\mid -1\le x\le 7\}$；（2）$(-\infty,-2)\cup\left[1,\dfrac{7}{2}\right]$",
                "analysis_md": "按题干重算。",
                "solution_md": (
                    r"$D=\{x\mid -1\le x\le 7\}$。"
                    "\n\n"
                    r"参数范围是 $(-\infty,-2)\cup\left[1,\dfrac{7}{2}\right]$。"
                    "\n\n"
                    r"答案：（1）$D=\{x\mid -1\le x\le 7\}$；（2）$(-\infty,-2)\cup\left[1,\dfrac{7}{2}\right]$"
                ),
            },
            ensure_ascii=False,
        )

    result = variant_question(
        {
            "id": "sz-q15",
            "type_code": "solution",
            "stem_md": (
                r"已知集合$A=\left \{ \begin{array}{l} x\left | { m-1\le x\le 2m } \right . \end{array} \right \}$，"
                r"函数$f\left ( { x } \right )=\sqrt{ -x ^ { 2 } +2x+8 }$的定义域为$B$．"
                "（1）求$B$；（2）若集合$A$是集合$B$的子集，求实数$m$的取值范围．"
            ),
            "answer_md": r"（1）$B=[-2,4]$（2）$(-\infty,2]$",
            "analysis_md": "先求定义域，再分空集与非空集讨论子集。",
            "solution_md": "",
        },
        complete=complete,
    )
    assert calls["n"] == 2
    assert result["supported"] is True
    assert result["source"] == "model"
    assert result["stem_md"] == stem
    assert result["options"] == []
    solution = _compact(result["solution_md"])
    assert r"-1\lex\le7" in solution
    assert r"\frac{7}{2}" in solution
    assert "需重新" not in result["analysis_md"]
    assert "深圳" not in result["stem_md"]


_ELLIPSE = {
    "id": "conic-variant",
    "stem_md": "已知椭圆的焦点在 x 轴上，求离心率。",
    "answer_md": "1/2",
    "analysis_md": "圆锥曲线",
    "solution_md": "联立。",
}


def test_unescaped_latex_json_is_accepted() -> None:
    calls = {"n": 0}

    def complete(system: str, user: str) -> str:
        calls["n"] += 1
        return (
            r'{"point":"函数最值","essence":"换了一个二次函数再求最小值。","axis":"数据",'
            r'"changes":["把一次项系数从 1 改成 3"],'
            r'"stem_md":"求函数 $f(x)=\frac{1}{2}x^{2}+3x+\alpha$ 在 $\left[0,1\right]$ 上的最小值。",'
            r'"options":[],"answer":"$0$","analysis_md":"配方后看区间端点。",'
            r'"solution_md":"配方得最小值是 $0$。答案：$0$"}'
        )

    result = variant_question(_ELLIPSE, complete=complete)
    assert calls["n"] == 1
    assert result["supported"] is True
    assert r"\frac{1}{2}" in result["stem_md"]
    assert r"\alpha" in result["stem_md"]
    assert r"\left" in result["stem_md"]
    assert "\x0c" not in result["stem_md"]
    assert "\x08" not in result["stem_md"]


def test_truncated_variant_json_is_closed_and_accepted() -> None:
    def complete(system: str, user: str) -> str:
        return (
            '{"point":"函数最值","essence":"换了函数","axis":"数据","changes":["改系数"],'
            '"stem_md":"求函数 $g(x)=x^{2}+5x$ 的最小值。","options":[],"answer":"$-4$",'
            '"analysis_md":"配方。","solution_md":"最小值为 $-4$。答案：$-4$"'
        )

    result = variant_question(_ELLIPSE, complete=complete)
    assert result["supported"] is True
    assert "5x" in result["stem_md"]
    assert "-4" in result["solution_md"]


def test_unparseable_model_output_is_sent_back_for_json() -> None:
    calls = {"n": 0}

    def complete(system: str, user: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "这道题可以改数字，但这段话不是 JSON。"
        assert "上一次结果不能用" in user
        assert "只输出一个 JSON" in user
        return json.dumps(
            {
                "point": "函数最值",
                "essence": "换了一个函数再求最小值。",
                "axis": "数据",
                "changes": ["改了二次项"],
                "stem_md": r"求函数 $h(x)=2x^{2}-8x$ 的最小值。",
                "options": [],
                "answer": "$-8$",
                "analysis_md": "配方。",
                "solution_md": r"最小值为 $-8$。答案：$-8$",
            },
            ensure_ascii=False,
        )

    result = variant_question(_ELLIPSE, complete=complete)
    assert calls["n"] == 2
    assert result["supported"] is True
    assert "2x^{2}-8x" in result["stem_md"]


def test_unrecognized_question_names_the_point_and_asks_for_a_model(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
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
