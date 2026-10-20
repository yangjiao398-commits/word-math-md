from word_math_md.question_rewrite import rewrite_question

Q1 = {
    "id": "ac94d186-2233-4a03-ae46-88e390073595",
    "stem_md": (
        "**深圳外国语学校2024-2025学年度高一第一学期第二次月考**\n\n"
        "**注意事项：**\n\n"
        "**1．答卷前，考生务必将自己的姓名、准考证号等填写在答题卡上.**\n\n"
        "命题$p$：“$\\forall x\\in \\left[ 0,2 \\right]$，$x ^ { 2 } +1\\ge 1$”，则$p$的否定是（ ）"
    ),
    "answer_md": "D",
    "options": [
        {"label": "A", "content_md": r"$\forall x\notin \left[ 0,2 \right]$，$x^{2}+1<1$"},
        {"label": "B", "content_md": r"$\forall x\subset \left[ 0,2 \right]$，$x^{2}+1<1$"},
        {"label": "C", "content_md": r"$\exists x\notin \left[ 0,2 \right]$，$x^{2}+1<1$"},
        {"label": "D", "content_md": r"$\exists x\in \left[ 0,2 \right]$，$x^{2}+1<1$"},
    ],
    "knowledge_points": [
        {
            "code": "1.5",
            "description": "全称量词与存在量词",
            "minor_category": "全称量词与存在量词",
        }
    ],
}


def _compact(tex: str) -> str:
    return tex.replace(" ", "").replace(r"\left", "").replace(r"\right", "")


def _flip(pred: str) -> str:
    if r"\ge" in pred:
        return pred.replace(r"\ge", "<", 1)
    if r"\le" in pred:
        return pred.replace(r"\le", ">", 1)
    raise AssertionError(pred)


def test_q1_rewrite_keeps_the_negation_rule_and_changes_the_answer() -> None:
    result = rewrite_question(Q1)

    assert result["supported"] is True
    assert result["point"] == "全称量词与存在量词"
    assert "∀" in result["essence"] and "∃" in result["essence"]
    assert "注意事项" not in result["stem_md"]
    assert r"\forall" in result["stem_md"]
    assert "x^{2}+1" not in _compact(result["stem_md"])
    assert "[0,2]" not in _compact(result["stem_md"])
    assert result["answer"] in "ABC"
    assert any(line.startswith("正确选项由 D 改为") for line in result["changes"])
    assert any(line.startswith("范围由 [0,2] 改为 ") and not line.endswith("[0,2]") for line in result["changes"])
    assert any(line.startswith("结论由 x²+1≥1 改为 ") for line in result["changes"])

    stem_pred = next(
        part
        for part in result["stem_md"].split("$")
        if r"\forall" not in part
        and r"\exists" not in part
        and (r"\ge" in part or r"\le" in part)
    )
    flipped = _compact(_flip(stem_pred))
    correct = next(item for item in result["options"] if item["label"] == result["answer"])
    correct_tex = _compact(correct["content_md"]).replace("$", "")
    assert r"\exists" in correct_tex
    assert r"\in" in correct_tex
    assert r"\notin" not in correct_tex
    assert r"\subset" not in correct_tex
    assert flipped in correct_tex
    assert f"故选：{result['answer']}" in result["solution_md"]
    assert "范围不变" in result["analysis_md"]


def test_q1_rewrite_is_stable_and_uses_each_trap_once() -> None:
    first = rewrite_question(Q1)
    second = rewrite_question(Q1)
    assert first == second

    bodies = [_compact(item["content_md"]).replace("$", "") for item in first["options"]]
    assert len(set(bodies)) == 4
    assert sum(r"\subset" in body for body in bodies) == 1
    assert sum(r"\notin" in body for body in bodies) == 2
    assert sum(body.startswith(r"\exists") and r"\notin" not in body for body in bodies) == 1


def test_existential_proposition_flips_back_to_a_universal() -> None:
    row = {
        "id": "exists-sample",
        "stem_md": r"命题$p$：“$\exists x\in \left(0,1\right]$，$x+1>1$”，写出$p$的否定.",
        "answer_md": "A",
        "knowledge_points": [],
    }
    result = rewrite_question(row)
    assert result["supported"] is True
    assert r"\exists" in result["stem_md"]
    correct = next(item for item in result["options"] if item["label"] == result["answer"])
    assert r"\forall" in correct["content_md"]
    assert r"\in" in correct["content_md"]
    assert result["answer"] != "A"


def test_other_questions_are_left_unchanged() -> None:
    result = rewrite_question(
        {
            "id": "quadratic",
            "stem_md": r"若 $x^{2}-1<0$，则 $x$ 的取值范围是（ ）",
            "answer_md": "B",
            "knowledge_points": [{"minor_category": "二次不等式"}],
        }
    )
    assert result["supported"] is False
    assert "二次不等式" in result["message"]
    assert "stem_md" not in result
