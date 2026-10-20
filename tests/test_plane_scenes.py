from pathlib import Path

from word_math_md import plane_scenes


def test_draft_reads_spaced_exam_latex_for_a_quadratic_inequality() -> None:
    scene = plane_scenes.draft_scene(
        "因为不等式 $ax ^ { 2 } +bx-3 &lt; 0$ 的解集是 $\\left ( { -\\infty ,1 } \\right )\\cup \\left ( { 3,+\\infty  } \\right )$。\n\n"
        "所以 $x=1$ 和 $x=3$ 是方程的根，即 $a=-1$，$b=4$。",
        title="第3题",
    )
    curve = scene["curves"][0]
    assert curve["preset"] == "quadratic"
    assert curve["quadratic"] == {"a": -1.0, "b": 4.0, "c": -3.0}
    step = scene["steps"][0]
    assert [item["name"] for item in step["markers"]] == ["1", "3"]
    assert [item["label"] for item in step["intervals"]] == ["(−∞, 1)", "(3, +∞)"]
    assert all(item["tone"] == "down" for item in step["intervals"])
    assert "ax² + bx − 3 < 0" in step["caption"]
    assert "(−∞, 1) ∪ (3, +∞)" in step["caption"]
    assert step["formula"][0] == "ax^{2}+bx-3<0"
    assert step["view"]["yMin"] <= -4
    titles = [item["title"] for item in scene["steps"]]
    assert titles[:4] == ["看清解集", "开口向下，a < 0", "两根是 1 和 3", "根与系数"]
    vieta = " ".join(next(item for item in scene["steps"] if item["id"] == "vieta")["formula"])
    assert r"1+3=-\dfrac{b}{a}" in vieta
    assert r"1\times 3=-\dfrac{3}{a}" in vieta
    vertex = next(item for item in scene["steps"] if item["id"] == "coefficient-b")
    assert vertex["markers"][0]["name"] == "顶点"
    assert vertex["markers"][0]["x"] == 2
    difference = next(item for item in scene["steps"] if item["id"] == "difference")["caption"]
    assert "b − a" in difference
    assert "= 5" in difference
    answer = next(item for item in scene["steps"] if item["id"] == "answer")
    assert "−(x − 1)(x − 3)" in answer["caption"]
    assert "-(x-1)(x-3)<0" in answer["formula"]
    assert "(x-1)(x-3)>0" in answer["formula"]


def test_draft_reads_a_point_reciprocal_and_monotonicity() -> None:
    scene = plane_scenes.draft_scene(
        "幂函数经过点 $\\left(\\sqrt{5},\\frac{\\sqrt{5}}{5}\\right)$。\n\n"
        "所以 $f(x)=\\dfrac{1}{x}$。\n\n"
        "令 $g(x)=x+\\dfrac{9}{x}$，在 $(0,3)$ 上递减。",
        stem="已知幂函数图像经过 $\\left(\\sqrt{5},\\frac{\\sqrt{5}}{5}\\right)$。",
        analysis="先求 $f(x)=\\dfrac{1}{x}$，再判断 $g(x)=x+\\dfrac{9}{x}$ 的单调性。",
        title="第16题",
    )
    presets = {item["preset"] for item in scene["curves"]}
    assert "reciprocal" in presets
    assert "linear-reciprocal" in presets
    assert scene["meta"] == "根据题干、分析、详解生成"
    point_step = scene["steps"][0]
    assert point_step["markers"]
    assert abs(point_step["markers"][0]["x"] - 5**0.5) < 1e-6
    decrease = scene["steps"][-1]
    assert decrease["intervals"]
    assert decrease["intervals"][0]["tone"] == "down"
    assert decrease["motion"]["tone"] == "down"
    linear = next(item for item in scene["curves"] if item["preset"] == "linear-reciprocal")
    assert linear["linearReciprocal"] == {"a": 1.0, "k": 9.0}
    assert linear["id"].startswith("g")


def test_draft_splits_a_piecewise_function_at_its_break() -> None:
    scene = plane_scenes.draft_scene(
        r"已知函数 $f\left ( { x } \right )=\left \{ \begin{array}{l} x ^ { 2 } -1,x\le 1, \\ \frac { 1 } { x-1 },x&gt;1, \end{array} \right.$则$f\left ( { f\left ( { 3 } \right ) } \right )=$（ ）"
    )
    by_preset = {item["preset"]: item for item in scene["curves"]}
    assert by_preset["quadratic"]["quadratic"] == {"a": 1.0, "b": 0.0, "c": -1.0}
    assert by_preset["quadratic"]["domain"]["to"] == 1
    assert by_preset["reciprocal"]["reciprocal"] == {"h": 1.0, "k": 1.0}
    assert by_preset["reciprocal"]["domain"]["from"] > 1
    assert set(scene["steps"][0]["curves"]) == {"q", "f"}
    caption = scene["steps"][0]["caption"]
    assert r"x²-1" in caption
    assert "1/(x-1)" in caption
    assert r"\²" not in caption
    assert "f(f(3))" in caption
    view = scene["steps"][0]["view"]
    assert -1.6 <= view["xMin"] <= -1.2
    assert 3.2 <= view["xMax"] <= 4.0
    assert -2.4 <= view["yMin"] <= -1.2
    assert 2.4 <= view["yMax"] <= 4.0
    assert view["yMax"] - view["yMin"] < 6


def test_draft_reads_the_fraction_exponential_in_the_stem() -> None:
    scene = plane_scenes.draft_scene(
        r"已知函数 $f\left ( { x } \right )=\frac { \pi ^ { x } -1 } { \pi ^ { x } +1 }$，且 $y=\pi ^ { x } +1$ 为增函数。"
    )
    fraction = next(item for item in scene["curves"] if item["preset"] == "fraction-exp")
    assert abs(fraction["base"] - 3.141592653589793) < 1e-5
    assert scene["steps"][0]["curves"] == [fraction["id"]]
    assert scene["steps"][0]["motion"]["tone"] == "up"


def test_save_roundtrip_registers_lesson(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(plane_scenes, "AUTHORED_DIR", tmp_path / "authored")
    monkeypatch.setattr(plane_scenes, "CATALOG_PATH", tmp_path / "plane-catalog.json")
    question_id = "fbd83a00-ed11-4ede-979d-d40caefa79df"
    scene = plane_scenes.draft_scene("先看定义域 $x\\ne 0$。\n\n再判断单调性。")
    lesson = plane_scenes.save_scene(question_id, scene, title="第16题草稿")
    loaded = plane_scenes.load_scene(question_id)
    assert loaded is not None
    assert loaded["steps"][0]["caption"]
    lessons = plane_scenes.load_lessons()
    assert lessons[question_id]["title"] == "第16题草稿"
    assert lesson["href"].endswith(f"/static/scenes/authored/{question_id}.json&embed=1")
    assert "4129cbd6-c865-4b57-8d48-3c1b6a0ab0c8" in lessons
