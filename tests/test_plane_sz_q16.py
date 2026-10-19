import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = ROOT / "word_math_md" / "static" / "scenes" / "sz-q16-power.json"
PAGE_PATH = ROOT / "word_math_md" / "static" / "plane-sz-q16.html"
CATALOG_PATH = ROOT / "word_math_md" / "static" / "question-plane.js"
ENGINE_PATH = ROOT / "word_math_md" / "static" / "plane-scene.js"
QUESTION_ID = "fbd83a00-ed11-4ede-979d-d40caefa79df"


def _scene() -> dict:
    import json

    return json.loads(SCENE_PATH.read_text(encoding="utf-8"))


def _g(x: float) -> float:
    return x + 9 / x


def test_power_point_gives_reciprocal() -> None:
    scene = _scene()
    right = next(item for item in scene["curves"] if item["id"] == "f-right")
    assert right["preset"] == "reciprocal"
    assert right["reciprocal"] == {"h": 0, "k": 1}
    point = next(step for step in scene["steps"] if step["id"] == "point")
    assert point["markers"][0]["x"] == math.sqrt(5)
    assert math.isclose((math.sqrt(5)) ** -1, math.sqrt(5) / 5)
    expression = " ".join(next(step for step in scene["steps"] if step["id"] == "expression")["formula"])
    assert "a=-1" in expression
    assert r"\dfrac{1}{x}" in expression


def test_oddness_and_decrease_follow_the_solution() -> None:
    right = next(item for item in _scene()["curves"] if item["id"] == "g-right")
    assert right["preset"] == "linear-reciprocal"
    assert right["linearReciprocal"] == {"a": 1, "k": 9}
    assert _g(-2) == -_g(2)
    x1, x2 = 1.0, 2.0
    diff = ((x1 - x2) * (x1 * x2 - 9)) / (x1 * x2)
    assert diff > 0
    assert math.isclose(diff, _g(x1) - _g(x2))
    assert _g(x1) > _g(x2)
    difference = " ".join(next(step for step in _scene()["steps"] if step["id"] == "difference")["formula"])
    assert r"\dfrac{(x_{1}-x_{2})(x_{1}x_{2}-9)}{x_{1}x_{2}}" in difference
    signs = " ".join(next(step for step in _scene()["steps"] if step["id"] == "signs")["formula"])
    assert "x_{1}-x_{2}<0" in signs
    assert "g(x_{1})-g(x_{2})>0" in signs
    decrease = next(step for step in _scene()["steps"] if step["id"] == "decrease")
    assert decrease["motion"]["tone"] == "down"
    assert decrease["check"]["relation"] == "down"
    assert "递减" in " ".join(decrease["formula"])
    ids = [step["id"] for step in _scene()["steps"]]
    assert ids == [
        "point",
        "expression",
        "build",
        "domain",
        "odd",
        "difference",
        "signs",
        "decrease",
    ]


def test_question_page_points_at_this_scene() -> None:
    page = PAGE_PATH.read_text(encoding="utf-8")
    catalog = CATALOG_PATH.read_text(encoding="utf-8")
    engine = ENGINE_PATH.read_text(encoding="utf-8")
    assert "/static/scenes/sz-q16-power.json" in page
    assert "plane-scene.js?v=11" in page
    assert QUESTION_ID in catalog
    assert "/static/plane-sz-q16.html?embed=1" in catalog
    assert 'preset === "linear-reciprocal"' in engine
