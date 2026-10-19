import json
from pathlib import Path

SCENE_PATH = (
    Path(__file__).resolve().parents[1]
    / "word_math_md"
    / "static"
    / "scenes"
    / "monotonicity-3.2.json"
)


def _scene() -> dict:
    return json.loads(SCENE_PATH.read_text(encoding="utf-8"))


def _f(x: float) -> float:
    assert _scene()["preset"] == "square"
    return x * x


def _holds(fn, pair: list[float], relation: str) -> bool:
    x1, x2 = pair
    assert x1 < x2
    y1, y2 = fn(x1), fn(x2)
    if relation == "down":
        return y1 > y2
    if relation == "up":
        return y1 < y2
    raise AssertionError(relation)


def _check_steps(scene: dict, fn) -> None:
    for step in scene["steps"]:
        check = step.get("check")
        if not check:
            continue
        if check["kind"] == "pairs":
            for pair, relation in check["pairs"]:
                assert _holds(fn, pair, relation)
        elif check["kind"] == "motion":
            motion = step["motion"]
            x = motion["x1From"]
            while x <= motion["x1To"] + 1e-9:
                assert _holds(fn, [x, x + motion["gap"]], check["relation"])
                x += 0.05
        else:
            raise AssertionError(check["kind"])


def test_monotonicity_scene_is_plane_lesson_for_3_2():
    scene = _scene()
    assert scene["version"] == 1
    assert scene["engine"] == "plane"
    assert scene["code"] == "3.2"
    assert scene["preset"] == "square"
    assert [step["id"] for step in scene["steps"]] == [
        "graph",
        "decrease-pair",
        "decrease-any",
        "increase-pair",
        "increase-any",
        "not-on-domain",
        "definition",
    ]


def test_marked_pairs_match_the_claimed_monotonicity():
    scene = _scene()
    _check_steps(scene, _f)


QUADRATIC_PATH = (
    Path(__file__).resolve().parents[1]
    / "word_math_md"
    / "static"
    / "scenes"
    / "monotonicity-quadratic-3.2.json"
)


def _quadratic_scene() -> dict:
    return json.loads(QUADRATIC_PATH.read_text(encoding="utf-8"))


def _quadratic(x: float) -> float:
    q = _quadratic_scene()["quadratic"]
    return q["a"] * x * x + q["b"] * x + q["c"]


def test_downward_quadratic_scene_uses_the_axis_of_symmetry():
    scene = _quadratic_scene()
    assert scene["preset"] == "quadratic"
    assert scene["quadratic"] == {"a": -1, "b": 2, "c": 3}
    assert [step["id"] for step in scene["steps"]] == [
        "graph",
        "axis",
        "increase-pair",
        "increase-any",
        "decrease-pair",
        "decrease-any",
        "split-by-axis",
    ]
    assert _quadratic(1) == 4
    assert abs(_quadratic(0.5) - (-(0.5 - 1) ** 2 + 4)) < 1e-9


def test_downward_quadratic_pairs_match_the_claimed_monotonicity():
    _check_steps(_quadratic_scene(), _quadratic)


def test_knowledge_point_3_2_lists_both_plane_lessons():
    from word_math_md.knowledge_page import page_html

    catalog_path = QUADRATIC_PATH.parent / "plane-lessons.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    lessons = catalog["3.2"]
    assert [item["id"] for item in lessons] == ["square", "quadratic"]
    root = QUADRATIC_PATH.parents[2]
    for item in lessons:
        assert (root / item["href"].lstrip("/")).is_file()
    html = page_html()
    assert "data-anim" in html
    assert "/static/scenes/plane-lessons.json" in html
    assert "knowledge-animations.js" in html


EXPONENTIAL_PATH = QUADRATIC_PATH.parent / "exponential-4.2.json"


def _exponential_scene() -> dict:
    return json.loads(EXPONENTIAL_PATH.read_text(encoding="utf-8"))


def _exp(base: float, x: float) -> float:
    return base**x


def test_exponential_scene_compares_bases_above_and_below_one():
    scene = _exponential_scene()
    assert scene["code"] == "4.2"
    assert scene["engine"] == "plane"
    by_id = {curve["id"]: curve for curve in scene["curves"]}
    assert by_id["growth"]["base"] == 2
    assert by_id["decay"]["base"] == 0.5
    assert [step["id"] for step in scene["steps"]] == [
        "through-origin-height",
        "increase-pair",
        "increase-any",
        "above-axis",
        "decay-pair",
        "decay-any",
        "compare",
    ]
    assert _exp(2, 0) == 1
    assert _exp(0.5, 0) == 1
    for x in (-2, -0.5, 0, 1, 2):
        assert abs(_exp(0.5, x) - _exp(2, -x)) < 1e-12


def test_exponential_steps_match_the_claimed_growth_or_decay():
    scene = _exponential_scene()
    curves = {curve["id"]: curve["base"] for curve in scene["curves"]}
    for step in scene["steps"]:
        check = step.get("check")
        if not check:
            continue
        fn = lambda x, base=curves[check["curve"]]: _exp(base, x)
        if check["kind"] == "pairs":
            for pair, relation in check["pairs"]:
                assert _holds(fn, pair, relation)
        elif check["kind"] == "motion":
            motion = step["motion"]
            x = motion["x1From"]
            while x <= motion["x1To"] + 1e-9:
                assert _holds(fn, [x, x + motion["gap"]], check["relation"])
                x += 0.05
        elif check["kind"] == "positive":
            for x in check["xs"]:
                assert fn(x) > 0
        else:
            raise AssertionError(check["kind"])


def test_knowledge_point_4_2_lists_the_exponential_lesson():
    catalog_path = EXPONENTIAL_PATH.parent / "plane-lessons.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    lessons = catalog["4.2"]
    assert [item["id"] for item in lessons] == ["exponential"]
    root = EXPONENTIAL_PATH.parents[2]
    assert (root / lessons[0]["href"].lstrip("/")).is_file()
