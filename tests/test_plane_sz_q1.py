import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = ROOT / "word_math_md" / "static" / "scenes" / "sz-q1-negation.json"
PAGE_PATH = ROOT / "word_math_md" / "static" / "plane-sz-q1.html"
CATALOG_PATH = ROOT / "word_math_md" / "static" / "question-plane.js"
QUESTION_ID = "ac94d186-2233-4a03-ae46-88e390073595"


def _scene() -> dict:
    return json.loads(SCENE_PATH.read_text(encoding="utf-8"))


def _f(x: float) -> float:
    q = _scene()["quadratic"]
    return q["a"] * x * x + q["b"] * x + q["c"]


def test_curve_matches_the_predicate() -> None:
    scene = _scene()
    assert scene["preset"] == "quadratic"
    assert scene["quadratic"] == {"a": 1, "b": 0, "c": 1}
    assert _f(0) == 1
    assert _f(2) == 5
    for i in range(0, 21):
        x = 2 * i / 20
        assert _f(x) >= 1


def test_negation_keeps_the_interval_and_flips_the_inequality() -> None:
    scene = _scene()
    predicate = next(step for step in scene["steps"] if step["id"] == "predicate")
    joined = " ".join(predicate["formula"])
    assert r"\exists x\in[0,2]" in joined
    assert "x^{2}+1<1" in joined
    assert predicate["intervals"] == [{"from": 0, "to": 2, "tone": "up", "label": "[0, 2]"}]
    assert predicate["guides"][0]["y"] == 1
    below = next(step for step in scene["steps"] if step["id"] == "below")
    assert "故选 D" in " ".join(below["formula"])
    assert below["vertex"]["x"] == 0


def test_question_page_points_at_this_scene() -> None:
    page = PAGE_PATH.read_text(encoding="utf-8")
    catalog = CATALOG_PATH.read_text(encoding="utf-8")
    server = (ROOT / "word_math_md" / "server.py").read_text(encoding="utf-8")
    assert "/static/scenes/sz-q1-negation.json" in page
    assert QUESTION_ID in catalog
    assert "/static/plane-sz-q1.html?embed=1" in catalog
    assert "data-plane-q" in server
    assert "question-plane.js" in server
